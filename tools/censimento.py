# Censimento degli edifici di Centro, La Cerchia e del fronte di Viale Roma, Corso Nazionale e Corso Garibaldi: una matrice (un record per edificio, tutti con gli stessi campi, e un
# record per ogni piano) da usare per le analisi urbanistiche. Scrive public/data/censimento.json.
#
#   python3 tools/censimento.py
#
# Fonti: i programmi piano per piano di tools/centro.py (Centro, 40 edifici) e tools/cerchia.py (La Cerchia, 100
# edifici) e tools/strade.py (gli edifici sul fronte delle tre strade, stimati com'è oggi); per gli spazi aperti e le strutture che restano come sono, public/data/places.json e le stime di
# tools/lavoratori.py. Le ipotesi sono tutte in PARAMETRI e vengono scritte anche nel file, così ogni numero si può
# ricostruire.
import json, os, re, sys, collections

sys.path.insert(0, os.path.dirname(__file__))
from lavoratori import assign_all, footprint
import centro
import cerchia
import strade
import mappa_completa as mappa
import diversifica
import perimetri

ROOT = os.path.join(os.path.dirname(__file__), '..')
DATA = os.path.join(ROOT, 'public', 'data')
OUT = os.path.join(DATA, 'censimento.json')
OUT_VILLETTE = os.path.join(DATA, 'censimento_villette.json')
QUARTERS = ('Centro', 'La Cerchia')
STRADE = tuple(strade.STRADE)
ZONE = QUARTERS + STRADE           # le schede del censimento: i due quartieri e le tre strade
PREFIX = {'Centro': 'CE', 'La Cerchia': 'LC', **{k: v['sigla'] for k, v in strade.STRADE.items()}}
PROGRAMMI = {'Centro': (centro.edifici, centro.RESTANO), 'La Cerchia': (cerchia.edifici, cerchia.RESTANO)}

PARAMETRI = {
    'casa': centro.CASA,
    'm2_per_addetto': {k: v['m2'] for k, v in centro.ATTIVITA.items()},
    'occupazione': {k: v['occupazione'] for k, v in centro.ATTIVITA.items() if v['occupazione'] < 1},
    'm2_per_camera': centro.M2_PER_CAMERA,
    'm2_per_studente': centro.M2_PER_STUDENTE,
    'aziende': {'classi_dipendenti': [[a, b] for a, b, _ in centro.AZIENDE_PICCOLE],
                'probabilita_azienda_grande': centro.AZIENDA_GRANDE},
    'altezza_piano_m': centro.ALTEZZA_PIANO,
}
CAT_LABEL = {c['id']: c['label'] for c in json.load(open(os.path.join(DATA, 'categories.json'), encoding='utf-8'))}
CAT_USO = {'res': 'residenziale', 'uff': 'ufficio', 'pub': 'servizio pubblico', 'com': 'ricettivo'}
STRUTTURA = re.compile(r'^(Pensilina|Tribuna\b|Padiglioni|Biglietteria|Cittadella|Torre)', re.I)


# Fattore sui posti di lavoro dei piani di negozi, uffici e fabbriche (le stime di partenza erano troppo alte).
RIDUZIONE_LAVORO = 0.5
USI_RIDOTTI = {'negozio', 'ufficio', 'fabbrica'}


def _meta(n):
    """n x RIDUZIONE_LAVORO arrotondato, ma un posto che c'e' resta almeno uno."""
    return max(1, int(n * RIDUZIONE_LAVORO + 0.5)) if n > 0 else 0


def riduci_lavoro(fl, aziende):
    """Dimezza i posti (occupati e liberi) e i dipendenti dei piani negozio, ufficio e fabbrica; i totali delle aziende
    si ricalcolano dai loro piani."""
    sel = {f['piano'] for f in fl if f['destinazione_uso'] in USI_RIDOTTI}
    for f in fl:
        if f['piano'] not in sel:
            continue
        f['posti_di_lavoro'] = _meta(f['posti_di_lavoro'])
        if f.get('posti_liberi'):
            f['posti_liberi'] = _meta(f['posti_liberi'])
        for a in f.get('aziende', []):
            a['dipendenti'] = _meta(a['dipendenti'])
        if f.get('aziende'):                       # il piano è la somma delle sue imprese
            f['posti_di_lavoro'] = sum(x['dipendenti'] for x in f['aziende'])
    per_piano = {(a['azienda'], f['piano']): a['dipendenti'] for f in fl for a in f.get('aziende', [])}
    for a in aziende:
        if sel.intersection(a['piani']):
            if all((a['azienda'], pi) in per_piano for pi in a['piani']):
                a['dipendenti'] = sum(per_piano[(a['azienda'], pi)] for pi in a['piani'])
            else:
                a['dipendenti'] = _meta(a['dipendenti'])


def record(e, codice):
    """Il record di un edificio: i totali e i suoi piani."""
    fl = e['piani_dettaglio']
    riduci_lavoro(fl, e['aziende'])
    usi = {f['destinazione_uso'] for f in fl}
    if usi == {'residenziale', 'negozio'}:
        uso = 'misto'
    elif len(usi) == 1:
        uso = next(iter(usi))
    else:                                        # la destinazione dei piani più numerosi (a pari piani, quella della mappa)
        cnt = collections.Counter(f['destinazione_uso'] for f in fl)
        uso = max(cnt, key=lambda u: (cnt[u], u == CAT_USO.get(e['cat'])))
    jobs = sum(f['posti_di_lavoro'] for f in fl)
    tot = len(fl)
    lorda = sum(f['superficie_m2'] for f in fl)
    return {
        'codice': codice, 'nome': e['nome'], 'quartiere': e['quartiere'], 'zona': e.get('zona', e['quartiere']),
        'lotto': e['lotto'],
        'luoghi': [] if e['forma'] == 'stimato' else [e['luogo'] if e['forma'] == 'esistente' else e['id']],
        'destinazione_uso': uso,
        'categoria': CAT_LABEL[e['cat']] + (' con negozi al piano terra' if uso == 'misto' else ''),
        'superficie_impronta_m2': e['impronta_m2'], 'piani_totali': tot,
        'superficie_lorda_m2': round(lorda),
        'altezza_m': e['altezza_m'],
        'abitanti': sum(f['abitanti'] for f in fl),
        'alloggi': sum(f['alloggi'] for f in fl), 'attivita': sum(f.get('imprese', 0) for f in fl),
        'posti_di_lavoro': jobs, 'posti_liberi': sum(f.get('posti_liberi', 0) for f in fl), 'unita': [],
        'piani': fl, 'aziende': e['aziende']}


def riallinea(e, target):
    """Porta a `target` gli abitanti di un palazzo residenziale, ripartiti sui piani in proporzione alla superficie."""
    fl = [f for f in e['piani'] if f['abitanti'] > 0]
    peso = sum(f['superficie_m2'] for f in fl)
    if not fl or not peso:
        return
    parti = [target * f['superficie_m2'] / peso for f in fl]
    base = [int(x) for x in parti]
    for i in sorted(range(len(fl)), key=lambda i: parti[i] - base[i], reverse=True)[:target - sum(base)]:
        base[i] += 1
    for f, a in zip(fl, base):
        f['abitanti'] = a
        f['alloggi'] = round(a / centro.CASA['abitanti_per_alloggio'] / (1 - centro.CASA['alloggi_sfitti'])) if a else 0
    e['abitanti'] = sum(f['abitanti'] for f in e['piani'])
    e['alloggi'] = sum(f['alloggi'] for f in e['piani'])


def main():
    places = json.load(open(os.path.join(DATA, 'places.json'), encoding='utf-8'))
    lots = json.load(open(os.path.join(DATA, 'lots.json'), encoding='utf-8'))
    W = assign_all(places)
    qlots = sorted((l for l in lots if l['quarter'] in QUARTERS), key=lambda l: (QUARTERS.index(l['quarter']), l['number']))

    edifici, spazi = [], []
    for q in QUARTERS:
        fn, restano = PROGRAMMI[q]
        es = sorted(fn(), key=lambda e: (e['lotto'], e['parte']))
        tenuti = {e['luogo'] for e in es if e['forma'] == 'esistente'}
        ns = 0
        for i, e in enumerate(es):
            edifici.append(record(e, f'{PREFIX[q]}-{i + 1:03d}'))
        # spazi aperti e strutture che restano come sono, poi quelli sui tetti o accanto agli edifici
        for p in sorted((p for p in places if p['id'] in restano and p['id'] not in tenuti), key=lambda p: (p['lot'], p['id'])):
            ns += 1
            spazi.append({'codice': f'{PREFIX[q]}-S{ns:03d}', 'nome': p['name'], 'quartiere': q, 'lotto': p['lot'],
                          'luogo': p['id'], 'tipo': 'struttura' if STRUTTURA.search(p['name']) else 'spazio aperto',
                          'superficie_m2': round(footprint(p['path'])), 'posti_di_lavoro': W[p['id']][0], 'abitanti': 0})
        for e in es:
            if e['spazio_tetto']:
                ns += 1
                giardino = e['spazio_tetto'].startswith('Giardino')
                spazi.append({'codice': f'{PREFIX[q]}-S{ns:03d}', 'nome': e['spazio_tetto'], 'quartiere': q,
                              'lotto': e['lotto'], 'luogo': e['id'], 'tipo': 'giardino pensile' if giardino else 'struttura',
                              'superficie_m2': round(e['impronta_m2'] * 0.8) if giardino else 64, 'posti_di_lavoro': 0, 'abitanti': 0})

    # le tre strade: gli edifici sul fronte (tools/strade.py); le villette stanno in censimento_villette.json
    lotti_strade = strade.lotti()
    for via in STRADE:
        es = sorted((e for e in strade.edifici() if e['zona'] == via), key=lambda e: (e['lotto'], e['parte']))
        for i, e in enumerate(es):
            if e['nome'] != 'Villetta':
                edifici.append(record(e, f'{PREFIX[via]}-{i + 1:03d}'))

    # il resto della mappa (tools/mappa_completa.py): ogni luogo di places.json non ancora censito, i palazzi residenziali
    # senza contorno e, a parte, le villette
    coperti = {x for e in edifici for x in e['luoghi']} | {s['luogo'] for s in spazi}
    nuovi, nuovi_spazi = mappa.edifici_resto(coperti)
    fronte = collections.Counter(e['lotto'] for e in edifici if e['nome'] == 'Palazzo residenziale' and not e['luoghi']
                                 and e['zona'] in STRADE and e['quartiere'] not in QUARTERS)
    palazzi, ville = mappa.residenziale(fronte)
    nuovi += palazzi
    quartieri = sorted({l['quarter'] for l in lots})
    sigla = mappa.sigle(quartieri)
    PREFIX.update(sigla)
    contatore = collections.Counter()
    for e in sorted(nuovi, key=lambda e: (e['zona'], e['lotto'] or 0, e['id'])):
        contatore[e['zona']] += 1
        r = record(e, f"{sigla[e['zona']]}-{contatore[e['zona']]:03d}")
        r['lotto'] = r['lotto'] or None
        edifici.append(r)
    ns = collections.Counter()
    for s in sorted(nuovi_spazi, key=lambda s: (s['quartiere'], s['lotto'] or 0, s['luogo'])):
        ns[s['quartiere']] += 1
        spazi.append({'codice': f"{sigla[s['quartiere']]}-S{ns[s['quartiere']]:03d}", **s, 'lotto': s['lotto'] or None})
    spazi = [{k: s[k] for k in ('codice', 'nome', 'quartiere', 'lotto', 'luogo', 'tipo', 'superficie_m2', 'posti_di_lavoro',
                                'abitanti')} for s in spazi]

    # villette: un record ciascuna, in un file a parte
    via_del_lotto = {n: v for n, (_, _, v) in lotti_strade.items()}
    nv = collections.Counter()
    villette = []
    for v in ville:
        nv[v['lotto']] += 1
        villette.append({'codice': f"VL-{v['lotto']:03d}-{v['n']:02d}", 'quartiere': v['quartiere'],
                         'zona': v['quartiere'], 'strada': via_del_lotto.get(v['lotto']), 'lotto': v['lotto'],
                         'destinazione_uso': 'residenziale', 'categoria': 'Residenziale',
                         'superficie_impronta_m2': v['superficie_impronta_m2'], 'piani_totali': v['piani'],
                         'superficie_lorda_m2': v['superficie_lorda_m2'], 'altezza_m': v['piani'] * centro.ALTEZZA_PIANO,
                         'abitanti': v['abitanti'], 'alloggi': v['alloggi'],
                         'attivita': 0, 'posti_di_lavoro': 0})

    # gli abitanti dei palazzi residenziali senza contorno tornano al totale del lotto (divisi in parti uguali)
    for l in lots:
        if l['quarter'] in QUARTERS or l['homes'] <= 0 or l['population'] / l['homes'] < mappa.SOGLIA_PALAZZO:
            continue
        pal = [e for e in edifici if e['lotto'] == l['number'] and e['destinazione_uso'] == 'residenziale']
        if len(pal) != l['homes']:
            print(f"  attenzione: lotto {l['number']} ha {l['homes']} case e {len(pal)} palazzi")
        for e, target in zip(pal, mappa.ripartisci(l['population'], len(pal))):
            riallinea(e, target)

    # imprese più varie e specifiche, bar e cliniche, aziende agricole (tools/diversifica.py); dopo il riallineamento degli abitanti
    riassunto = diversifica.applica(edifici, lots, CAT_LABEL, sigla, riallinea)
    # un perimetro sulla mappa per ogni attività (tools/perimetri.py scrive public/data/perimetri.json)
    perimetri_riassunto = perimetri.applica(edifici, places, lots)

    # riepilogo per zona, con gli indicatori urbanistici di base. Centro, La Cerchia e le tre strade come prima (le strade
    # si sovrappongono ai quartieri che attraversano); poi ogni altro quartiere, con tutti gli edifici dei suoi lotti
    altri = tuple(q for q in quartieri if q not in QUARTERS)
    zlots = {q: [l for l in qlots if l['quarter'] == q] for q in QUARTERS}
    for via in STRADE:
        zlots[via] = [l for l, _, v in lotti_strade.values() if v == via]
    for q in altri:
        zlots[q] = [l for l in lots if l['quarter'] == q]
    riepilogo = {}
    for q in ZONE + altri + ('Totale',):
        if q == 'Totale':
            es, vs, ls = edifici, villette, lots
        elif q in STRADE:                  # le strade: solo gli edifici sul fronte; le villette dei lotti contano solo per i lotti
            es, vs, ls = [e for e in edifici if e['zona'] == q], [], zlots[q]
        elif q in ZONE:
            es, vs, ls = [e for e in edifici if e['zona'] == q], [v for v in villette if v['zona'] == q], zlots[q]
        else:
            es, vs, ls = [e for e in edifici if e['quartiere'] == q], [v for v in villette if v['quartiere'] == q], zlots[q]
        ha = sum(footprint(l['path']) for l in ls) / 10000
        ab_vil = sum(v['abitanti'] for v in vs)
        ab = sum(e['abitanti'] for e in es) + ab_vil
        jobs = sum(e['posti_di_lavoro'] for e in es) + sum(s['posti_di_lavoro'] for s in spazi if q in ('Totale', s['quartiere']))
        slp = sum(e['superficie_lorda_m2'] for e in es) + sum(v['superficie_lorda_m2'] for v in vs)
        con_case = {e['lotto'] for e in es} | {v['lotto'] for v in villette if q == 'Totale' or v['quartiere'] == q or v['strada'] == q}
        per_uso = collections.defaultdict(lambda: {'edifici': 0, 'superficie_lorda_m2': 0, 'posti_di_lavoro': 0, 'attivita': 0})
        for e in es:
            u = per_uso[e['destinazione_uso']]
            u['edifici'] += 1
            u['superficie_lorda_m2'] += e['superficie_lorda_m2']
            u['posti_di_lavoro'] += e['posti_di_lavoro']
            u['attivita'] += e['attivita']
        riepilogo[q] = {
            'lotti': len(ls), 'lotti_senza_edifici': sum(1 for l in ls if l['number'] not in con_case),
            'superficie_territoriale_ha': round(ha, 1), 'edifici': len(es), 'villette': len(vs),
            'spazi_aperti': sum(1 for s in spazi if q in ('Totale', s['quartiere'])),
            'abitanti': ab, 'abitanti_in_villette': ab_vil,
            'alloggi': sum(e['alloggi'] for e in es) + sum(v['alloggi'] for v in vs),
            'attivita': sum(e['attivita'] for e in es), 'posti_di_lavoro': jobs,
            'posti_liberi': sum(e['posti_liberi'] for e in es),
            'superficie_lorda_m2': slp,
            'per_destinazione_uso': {k: v for k, v in sorted(per_uso.items())}}

    out = {
        'meta': {
            'titolo': 'Censimento di tutti gli edifici e gli spazi della mappa (le villette sono in censimento_villette.json)',
            'quartieri': list(ZONE + altri),
            'generato_da': 'tools/censimento.py',
            'fonti': ['tools/centro.py', 'tools/cerchia.py', 'tools/strade.py', 'tools/mappa_completa.py',
                      'public/data/places.json', 'public/data/lots.json', 'tools/lavoratori.py', 'tools/perimetri.py'],
            'unita_di_misura': 'metri e metri quadri (coordinate della mappa)',
            'parametri': {**PARAMETRI, 'abitanti_per_casa_oltre_cui_palazzo': mappa.SOGLIA_PALAZZO},
            'campi': {
                'codice': 'CE-nnn (Centro), LC-nnn (La Cerchia), VR/CN/CG-nnn (le tre strade) o la sigla del quartiere '
                          '(per esempio CEA = Campagna Est), in ordine di lotto, poi gli edifici senza contorno aggiunti '
                          '(locali, aziende agricole); gli spazi aperti hanno una S: CE-Snnn',
                'lotto': 'il lotto in cui sta l\'edificio: ogni edificio è censito come parte di un lotto '
                         '(null per i pochi luoghi fuori da ogni lotto, come i ponti e le pensiline sui binari)',
                'zona': 'la scheda del censimento: il quartiere, o la strada sul cui fronte sta l\'edificio (Viale Roma, '
                        'Corso Nazionale, Corso Garibaldi)',
                'quartiere': 'il quartiere del lotto',
                'luoghi': 'id del luogo di places.json che è l\'edificio (vuoto per i palazzi residenziali senza contorno '
                          'sulla mappa)',
                'destinazione_uso': 'residenziale | misto (case con negozi al piano terra) | ufficio | negozio | fabbrica '
                                    '(industria e artigianato) | servizio pubblico | ricettivo | parcheggio | deposito '
                                    '(silos, magazzini, fienili, tettoie) | agricolo (stalle, serre, cascine, cantine) | '
                                    'ferroviario | impianto (energia, depuratori, data center)',
                'piani_totali': 'piani fuori terra',
                'attivita': 'imprese ed enti nell\'edificio',
                'abitanti': 'persone che vivono nell\'edificio (0 se non ci abita nessuno)',
                'posti_di_lavoro': 'addetti delle imprese e degli enti nell\'edificio (le persone che ci lavorano)',
                'posti_liberi': 'posti di lavoro che restano liberi: spazio non occupato da nessuna impresa',
                'altezza_m': 'piani × 3,5 m',
                'piani': 'un record per piano, dal piano terra (0) in su, con destinazione d\'uso, attività, superficie, '
                         'abitanti, alloggi, posti di lavoro, imprese, camere negli alberghi, le imprese che '
                         'lo occupano (aziende) e i posti liberi',
                'aziende': 'le imprese dell\'edificio, ognuna con il suo nome, cosa fa (ramo specifico), i dipendenti e i '
                           'piani; negli edifici con un\'impresa sola è l\'impresa che porta il nome dell\'edificio',
                'spazi_aperti': 'parchi, piazze, campi coltivati, piste, cave e strutture minute: codice, nome, '
                                'quartiere, lotto, luogo, tipo, superficie, posti_di_lavoro (manutenzione) e abitanti',
            },
        },
        'riepilogo': riepilogo,
        'edifici': edifici,
        'spazi_aperti': spazi,
    }
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(json.dumps(out, indent=1, ensure_ascii=False))

    per_q = {}
    for q in ['Totale'] + quartieri:
        vs = [v for v in villette if q == 'Totale' or v['quartiere'] == q]
        per_q[q] = {'villette': len(vs), 'abitanti': sum(v['abitanti'] for v in vs),
                    'alloggi': sum(v['alloggi'] for v in vs), 'superficie_lorda_m2': sum(v['superficie_lorda_m2'] for v in vs)}
    vill = {
        'meta': {
            'titolo': 'Censimento delle villette residenziali (due piani, uno o due alloggi) di tutta la mappa',
            'generato_da': 'tools/censimento.py',
            'fonti': ['public/data/lots.json'],
            'nota': 'Le villette non hanno un contorno sulla mappa: sono le case dei lotti (lots.json, campo homes) in cui '
                    f'ogni casa ha meno di {mappa.SOGLIA_PALAZZO} abitanti. Gli abitanti del lotto sono divisi tra le sue '
                    'case; alloggi e superfici seguono dai parametri della casa. Gli edifici con più abitanti '
                    'per casa (Le Corti, Città degli Studi, Porta Sud) sono palazzi e stanno nel censimento principale.',
            'parametri': {'casa': centro.CASA, 'piani': 2},
            'campi': {'codice': 'VL-lotto-numero della villetta nel lotto', 'zona': 'il quartiere, o la strada sul cui '
                      'fronte sta il lotto', 'abitanti': 'persone che ci vivono',
                      'alloggi': 'alloggi (compresi i pochi sfitti)'},
        },
        'riepilogo': per_q,
        'villette': villette,
    }
    with open(OUT_VILLETTE, 'w', encoding='utf-8') as f:
        f.write(json.dumps(vill, indent=1, ensure_ascii=False))

    pop = sum(q['population'] for q in json.load(open(os.path.join(DATA, 'quarters.json'), encoding='utf-8')))
    for q in ZONE + altri + ('Totale',):
        t = riepilogo[q]
        print(f"{q}: edifici {t['edifici']} · villette {t['villette']} · abitanti {t['abitanti']} · attività {t['attivita']} · "
              f"posti di lavoro {t['posti_di_lavoro']} · posti liberi {t['posti_liberi']}")
    print(f"spazi aperti {len(spazi)} → {os.path.relpath(OUT, ROOT)}; villette {len(villette)} → {os.path.relpath(OUT_VILLETTE, ROOT)}")
    print(f"abitanti censiti {riepilogo['Totale']['abitanti']} · abitanti nei quartieri (quarters.json) {pop}")
    print('diversificazione:', riassunto)
    print('perimetri:', perimetri_riassunto)
    mancano = {p['id'] for p in places} - {x for e in edifici for x in e['luoghi']} - {s['luogo'] for s in spazi}
    print(f"luoghi di places.json senza scheda: {len(mancano)}")


if __name__ == '__main__':
    main()
