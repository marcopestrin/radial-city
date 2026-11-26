# Analisi di proporzioni e distanze della città, dai JSON del censimento. Stampa le cifre del report.
#
#   python3 tools/analisi_citta.py
#
# Serve per controllare se la città è proporzionata: quante imprese e addetti per settore, quanti servizi per abitante e a che
# distanza stanno dalle case (a piedi), dove mangiano gli addetti, quanto sono vicine le fabbriche alle abitazioni.
# Le distanze sono in linea d'aria, in metri, tra i centri degli edifici e dei lotti (coordinate della mappa).
import json, math, os, re, sys, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lavoratori import footprint

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'public', 'data')


def carica(nome):
    return json.load(open(os.path.join(DATA, nome), encoding='utf-8'))


def centro_path(path):
    """Baricentro del sottotracciato più grande di un contorno."""
    best = None
    for sub in re.split(r'[MZ]', path):
        n = list(map(float, re.findall(r'-?\d+\.?\d*', sub)))
        p = list(zip(n[0::2], n[1::2]))
        if len(p) < 3:
            continue
        a = cx = cy = 0.0
        for i in range(len(p)):
            x0, y0 = p[i]
            x1, y1 = p[(i + 1) % len(p)]
            c = x0 * y1 - x1 * y0
            a += c
            cx += (x0 + x1) * c
            cy += (y0 + y1) * c
        if abs(a) < 1e-6:
            res, area = (sum(x for x, _ in p) / len(p), sum(y for _, y in p) / len(p)), 0
        else:
            res, area = (cx / (3 * a), cy / (3 * a)), abs(a)
        if best is None or area > best[1]:
            best = (res, area)
    return best[0]


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


# ------------------------------------------------------------------ macro-settori
FOOD = {'bar e caffetteria', 'pub, birreria ed enoteca', 'pizzeria', 'ristorante', 'trattoria e osteria', 'fast food e paninoteca',
        'gelateria e pasticceria', 'mensa', 'ristorazione', 'panetteria e panificio'}
ALIMENTARI = {'grande distribuzione alimentare', 'minimarket', 'alimentari e prodotti freschi', 'fruttivendolo', 'macelleria', 'pescheria',
              'salumeria e gastronomia', 'formaggi e latticini', 'negozio di prodotti biologici', 'pasta fresca'}
SANITA = re.compile(r'(sanità|ospedale|poliambulatorio|odontoiatria|farmacia|clinica|diagnostica|fisioterapia|studi medici|chirurgia)', re.I)
ISTRUZIONE = re.compile(r'(istruzione|università|scuola|liceo|formazione aziendale)', re.I)
PUBBLICO = re.compile(r'(servizio pubblico|uffici comunali|servizi postali|sicurezza e controllo|culto|associazioni e sindacati|'
                      r'fiere e congressi|cultura e intrattenimento|ordine professionale)', re.I)
SAN_NOME = re.compile(r'^(Ospedale|Pronto soccorso|Poliambulatorio|Casa della salute|Casa di riposo|Laboratorio analisi|Centro analisi|Day hospital)')
IST_NOME = re.compile(r'^(Scuola|Liceo|Istituto|Polo scolastico|Università|Facoltà|Dipartimento|Laboratori universitari|Biblioteca universitaria|Asilo)')


def macro(ramo, uso, nome):
    r = ramo or ''
    if SAN_NOME.search(nome) or SANITA.search(r):
        return 'sanità'
    if IST_NOME.search(nome) or ISTRUZIONE.search(r):
        return 'istruzione e ricerca'
    if r in FOOD:
        return 'commercio e ristorazione'
    if uso == 'ricettivo' or r.startswith('hotel'):
        return 'alberghi e ricettivo'
    if uso == 'agricolo' or (uso == 'deposito' and r.startswith(('stoccaggio', 'deposito e lavorazione', 'rimessaggio'))):
        return 'agricoltura'
    if uso == 'impianto' or 'energia' in r:
        return 'energia e impianti'
    if uso == 'servizio pubblico' or PUBBLICO.search(r):
        return 'amministrazione e servizi pubblici'
    if uso == 'negozio':
        return 'commercio e ristorazione'
    if uso == 'fabbrica':
        return 'industria e artigianato'
    if uso in ('deposito', 'ferroviario', 'parcheggio') or 'logistic' in r or 'trasport' in r:
        return 'logistica e trasporti'
    if uso in ('ufficio', 'misto', 'residenziale'):
        return 'terziario avanzato (uffici e professioni)'
    return 'altro'


def per_macro(edifici, spazi):
    imprese, addetti = collections.Counter(), collections.Counter()
    for e in edifici:
        ramo = {a['azienda']: a['ramo'] for a in e['aziende']}
        for f in e['piani']:
            voci = f.get('aziende') or []
            for fa in voci:
                m = macro(ramo.get(fa['azienda']), f['destinazione_uso'], e['nome'])
                imprese[m] += 1
                addetti[m] += fa['dipendenti']
            resto = f['posti_di_lavoro'] - sum(fa['dipendenti'] for fa in voci)
            if resto > 0:
                m = macro(None, f['destinazione_uso'], e['nome'])
                addetti[m] += resto
                imprese[m] += f.get('imprese', 0) if not voci else 0
    addetti['manutenzione di spazi aperti'] += sum(s['posti_di_lavoro'] for s in spazi)
    return imprese, addetti


def conteggi(edifici, spazi):
    """Quanti servizi ci sono, per categoria, e quanti addetti."""
    def n(rx, campo='nome'):
        return sum(1 for e in edifici if re.search(rx, e[campo], re.I))
    ramo = collections.Counter(a['ramo'] for e in edifici for a in e['aziende'])
    out = {
        'scuole (infanzia, primaria, media, superiori)': n(r'^(Scuola dell.infanzia|Scuola primaria|Scuola media|Liceo|Istituto (tecnico|professionale)|Polo scolastico)'),
        'asili nido': n(r'Asilo nido'),
        'università (edifici di facoltà e dipartimenti)': n(r'^(Università|Facoltà|Dipartimento)'),
        'ospedali': n(r'^Ospedale'), 'pronto soccorso': n(r'^Pronto soccorso'),
        'poliambulatori e cliniche': n(r'^(Poliambulatorio|Casa della salute)') + sum(v for k, v in ramo.items() if k and re.search('clinica|diagnostic|fisioterapia|studi medici|chirurgia|odontoiatria', k)),
        'farmacie': sum(1 for e in edifici for a in e['aziende'] if a['ramo'] == 'farmacia' or a['azienda'].startswith('Farmacia')), 'case di riposo': n(r'^Casa di riposo'),
        'supermercati, discount e minimarket': ramo['grande distribuzione alimentare'] + ramo['minimarket'],
        'bar, ristoranti, pizzerie e simili': sum(v for k, v in ramo.items() if k in FOOD and k not in ('mensa', 'panetteria e panificio')),
        'filiali bancarie': ramo['filiale bancaria'], 'uffici postali': ramo['servizi postali'],
        'chiese e luoghi di culto': n(r'^(Chiesa|Cappella|Monastero)'),
        'biblioteche': n(r'Biblioteca'), 'musei, teatri, cinema': n(r'^(Museo|Teatro|Cinema|Planetario|Galleria d)'),
        'palestre e impianti sportivi': n(r'^(Palestra|Stadio|Palazzetto|Piscine|Bocciodromo)'),
    }
    verde = sum(s['superficie_m2'] for s in spazi if s['tipo'] == 'verde')
    return out, verde


def main():
    d = carica('censimento.json')
    E, S = d['edifici'], d['spazi_aperti']
    lots = {l['number']: l for l in carica('lots.json')}
    places = {p['id']: p for p in carica('places.json')}
    places.update({p['id']: p for p in carica('perimetri.json') if p['kind'] == 'footprint'})   # i contorni dei nuovi edifici
    bus = carica('bus.json')
    ab_tot = d['riepilogo']['Totale']['abitanti']
    posti = d['riepilogo']['Totale']['posti_di_lavoro']
    print(f'abitanti {ab_tot} · posti di lavoro {posti} · posti liberi {d["riepilogo"]["Totale"]["posti_liberi"]}')

    # ---------------------------------------------------------- 1. settori
    imprese, addetti = per_macro(E, S)
    tot = sum(addetti.values())
    print('\n## settori (addetti, quota, imprese)')
    for m, v in addetti.most_common():
        print(f'{m:48s} {v:6d} {100 * v / tot:5.1f}% {imprese[m]:5d}')
    print('totale addetti', tot)

    # ---------------------------------------------------------- 2. servizi per abitante
    cont, verde = conteggi(E, S)
    print('\n## servizi (numero, ogni 10.000 abitanti)')
    for k, v in cont.items():
        print(f'{k:50s} {v:4d} {10000 * v / ab_tot:6.1f}')
    print(f'verde pubblico (spazi "verde") {verde / 10000:.1f} ha = {verde / ab_tot:.1f} m² per abitante')

    # ---------------------------------------------------------- 3. punti: edifici e lotti
    def punto(e):
        for x in e['luoghi']:
            if x in places:
                b = places[x]['bbox']
                return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        l = lots.get(e['lotto'])
        return centro_path(l['path']) if l else None
    pt = {e['codice']: punto(e) for e in E}
    lotto_c = {n: centro_path(l['path']) for n, l in lots.items()}
    case = [(n, lotto_c[n], l['population'], l['quarter']) for n, l in lots.items() if l['population'] > 0]
    tot_ab = sum(p for _, _, p, _ in case)

    def con_ramo(pred):
        out = []
        for e in E:
            if pt[e['codice']] and any(pred(a['ramo'] or '') or pred(e['nome']) for a in e['aziende']) :
                out.append(pt[e['codice']])
        return out

    servizi = {
        'bar o ristorante': [pt[e['codice']] for e in E if pt[e['codice']] and any((a['ramo'] in FOOD and a['ramo'] != 'mensa') for a in e['aziende'])],
        'supermercato o alimentari': [pt[e['codice']] for e in E if pt[e['codice']] and any(a['ramo'] in ALIMENTARI for a in e['aziende'])],
        'farmacia': [pt[e['codice']] for e in E if pt[e['codice']] and any(a['ramo'] == 'farmacia' or a['azienda'].startswith('Farmacia') for a in e['aziende'])],
        'scuola primaria o infanzia': [pt[e['codice']] for e in E if pt[e['codice']] and re.search(r'^(Scuola primaria|Scuola dell.infanzia)', e['nome'])],
        'medico (poliambulatorio, casa della salute, ospedale)': [pt[e['codice']] for e in E if pt[e['codice']] and re.search(r'^(Poliambulatorio|Casa della salute|Ospedale|Centro analisi)', e['nome'])],
        'ospedale': [pt[e['codice']] for e in E if pt[e['codice']] and re.search(r'^Ospedale', e['nome'])],
        'parco o giardino': [centro_path(places[s['luogo']]['path']) for s in S if s['tipo'] == 'verde' and s['luogo'] in places],
        'fermata dell\'autobus': [(s['x'], s['y']) for s in bus['stops']],
    }
    print('\n## distanze dalle case al servizio più vicino (pesate per abitante)')
    print(f"{'servizio':52s} {'n':>4s} {'mediana':>8s} {'p90':>7s} {'≤400m':>7s} {'≤800m':>7s} {'≤1,5km':>7s}")
    ris = {}
    for nome, pts in servizi.items():
        ds = sorted((min(dist(c, p) for p in pts), pop) for _, c, pop, _ in case)
        def perc(q):
            acc = 0
            for dd, pop in ds:
                acc += pop
                if acc >= q * tot_ab:
                    return dd
        def entro(m):
            return 100 * sum(pop for dd, pop in ds if dd <= m) / tot_ab
        ris[nome] = ds
        print(f'{nome:52s} {len(pts):4d} {perc(0.5):8.0f} {perc(0.9):7.0f} {entro(400):6.0f}% {entro(800):6.0f}% {entro(1500):6.0f}%')

    print('\n## per quartiere: abitanti, bar/ristoranti entro 800 m, distanza mediana da bar/ristorante, da supermercato, da farmacia, da fermata')
    per_q = collections.defaultdict(list)
    for n, c, pop, q in case:
        per_q[q].append((c, pop))
    righe = []
    for q, v in per_q.items():
        popq = sum(p for _, p in v)
        row = [q, popq]
        for nome in ('bar o ristorante', 'supermercato o alimentari', 'farmacia', 'fermata dell\'autobus', 'scuola primaria o infanzia'):
            pts = servizi[nome]
            ds = sorted((min(dist(c, p) for p in pts), pop) for c, pop in v)
            acc, med = 0, 0
            for dd, pop in ds:
                acc += pop
                if acc >= 0.5 * popq:
                    med = dd
                    break
            row.append(round(med))
        righe.append(row)
    print(f"{'quartiere':24s} {'abitanti':>8s} {'bar/rist':>9s} {'super':>7s} {'farm':>6s} {'bus':>6s} {'scuola':>7s}   (distanza mediana in metri)")
    for r in sorted(righe, key=lambda r: -r[1]):
        print(f'{r[0]:24s} {r[1]:8d} {r[2]:9d} {r[3]:7d} {r[4]:6d} {r[5]:6d} {r[6]:7d}')

    # ---------------------------------------------------------- 4. addetti e pranzo
    print('\n## addetti: distanza dal locale più vicino (bar, ristorante, mensa) per zona')
    cibo = servizi['bar o ristorante'] + [pt[e['codice']] for e in E if pt[e['codice']] and any(a['ramo'] == 'mensa' for a in e['aziende'])]
    zona_add = collections.defaultdict(list)
    for e in E:
        if e['posti_di_lavoro'] and pt[e['codice']] and e['destinazione_uso'] not in ('residenziale',):
            zona_add[e['zona'] if e['zona'] in ('Centro', 'La Cerchia', 'Corso Garibaldi', 'Corso Nazionale', 'Viale Roma') else e['quartiere']].append((pt[e['codice']], e['posti_di_lavoro'], e))
    righe = []
    for z, v in zona_add.items():
        n = sum(w for _, w, _ in v)
        ds = [(min(dist(p, c) for c in cibo), w) for p, w, _ in v]
        entro = lambda m: 100 * sum(w for dd, w in ds if dd <= m) / n
        med = sorted(ds)
        acc = 0
        for dd, w in med:
            acc += w
            if acc >= n / 2:
                break
        locali_300 = sum(1 for p, _, _ in v for c in [p] if False)
        righe.append((z, n, round(dd), entro(300), entro(600)))
    print(f"{'zona':26s} {'addetti':>8s} {'mediana':>8s} {'≤300m':>7s} {'≤600m':>7s}")
    for r in sorted(righe, key=lambda r: -r[1])[:22]:
        print(f'{r[0]:26s} {r[1]:8d} {r[2]:8d} {r[3]:6.0f}% {r[4]:6.0f}%')
    tutti = [(min(dist(p, c) for c in cibo), w) for v in zona_add.values() for p, w, _ in v]
    n = sum(w for _, w in tutti)
    print(f'tutti gli addetti: entro 300 m {100 * sum(w for dd, w in tutti if dd <= 300) / n:.0f}% · entro 600 m {100 * sum(w for dd, w in tutti if dd <= 600) / n:.0f}% · oltre 1 km {100 * sum(w for dd, w in tutti if dd > 1000) / n:.0f}%')
    print('locali di ristoro (bar, ristoranti, mense):', len(cibo), '· addetti per locale', round(n / len(cibo)))

    # ---------------------------------------------------------- 5. lavoro e residenza per quartiere
    print('\n## quartieri: abitanti, posti di lavoro, rapporto, posti liberi')
    q_ab = collections.Counter({q: sum(p for _, p in v) for q, v in per_q.items()})
    q_job = collections.Counter()
    for e in E:
        q_job[e['quartiere']] += e['posti_di_lavoro']
    for q in sorted(set(q_ab) | set(q_job), key=lambda q: -(q_ab[q] + q_job[q]))[:28]:
        print(f'{q:24s} abitanti {q_ab[q]:6d} · lavoro {q_job[q]:6d} · rapporto {q_job[q] / q_ab[q] if q_ab[q] else float("inf"):5.2f}')

    # ---------------------------------------------------------- 6. fabbriche e impianti vicino alle case
    print('\n## impianti e fabbriche vicino alle case (distanza dal lotto abitato più vicino, ≤ 400 m)')
    molesti = re.compile(r'(Depuratore|Discarica|Cementeria|Fornace|Impianto di calcestruzzo|Impianto inerti|Centrale elettrica|Stampaggio|Carpenteria|Lavorazione alluminio|Fonderia|Cava)', re.I)
    visti = {}
    for e in E:
        if (e['destinazione_uso'] in ('fabbrica', 'impianto') or molesti.search(e['nome'])) and pt[e['codice']] and e['posti_di_lavoro'] + (0 if molesti.search(e['nome']) else 0) > 0:
            dd, qq = min((dist(pt[e['codice']], c), (q, pop)) for _, c, pop, q in case)
            # solo lotti abitati diversi da quello dell'edificio
            cand = [(dist(pt[e['codice']], c), q, pop, n) for n, c, pop, q in case if n != e['lotto'] and pop >= 20]
            dmin, q, pop, n = min(cand)
            if dmin <= 400 and (molesti.search(e['nome']) or e['posti_di_lavoro'] >= 50):
                visti[(e['quartiere'], e['nome'])] = min(visti.get((e['quartiere'], e['nome']), (9999,))[0], dmin), n, pop, q
    for (q0, nome), (dm, n, pop, q) in sorted(visti.items(), key=lambda kv: kv[1][0])[:25]:
        print(f'{nome[:34]:34s} {q0:22s} → lotto {n} ({q}, {pop} ab.) a {dm:.0f} m')
    print('totale edifici molesti/industriali a meno di 400 m da un lotto abitato:', len(visti))

    # ---------------------------------------------------------- 7. cluster e distanze tra i poli
    print('\n## distanze (km, in linea d\'aria) tra i poli di lavoro')
    poli = {}
    gruppi = collections.defaultdict(list)
    for e in E:
        if e['posti_di_lavoro'] and pt[e['codice']]:
            gruppi[e['quartiere']].append((pt[e['codice']], e['posti_di_lavoro']))
    for q in ('Centro', 'La Cerchia', 'Stazione', 'Aeroporto', 'Polo Logistico', 'Zona Industriale Sud', 'Città degli Studi', 'San Luca', 'Tecnopolo', 'Le Officine', 'Zona Artigianale', 'Porta Sud', 'Borgo Fiera'):
        v = gruppi.get(q)
        if v:
            w = sum(x for _, x in v)
            poli[q] = (sum(p[0] * x for p, x in v) / w, sum(p[1] * x for p, x in v) / w, w)
    nomi = list(poli)
    print(' ' * 22 + ''.join(f'{n[:8]:>9s}' for n in nomi))
    for a in nomi:
        print(f'{a[:20]:22s}' + ''.join(f'{dist(poli[a][:2], poli[b][:2]) / 1000:9.1f}' for b in nomi) + f'   ({poli[a][2]} addetti)')
    cc = (sum(p[0] * p[2] for p in poli.values()) / sum(p[2] for p in poli.values()), sum(p[1] * p[2] for p in poli.values()) / sum(p[2] for p in poli.values()))
    dd = sorted((dist(c, cc), pop) for _, c, pop, _ in case)
    acc = 0
    for x, pop in dd:
        acc += pop
        if acc >= tot_ab / 2:
            print(f'\nbaricentro dei posti di lavoro ({cc[0]:.0f}, {cc[1]:.0f}); distanza mediana dei residenti: {x / 1000:.1f} km')
            break
    print('residenti oltre 3 km dal baricentro del lavoro: %.0f%%' % (100 * sum(pop for x, pop in dd if x > 3000) / tot_ab))

    # ---------------------------------------------------------- 8. servizi sanitari
    print('\n## ospedale: residenti entro 2 / 4 km dall\'ospedale più vicino')
    ds = ris['ospedale']
    for km in (2000, 4000):
        print(f'  entro {km / 1000:.0f} km: {100 * sum(pop for dd, pop in ds if dd <= km) / tot_ab:.0f}%')

    # ---------------------------------------------------------- 9. fermate
    print('\n## autobus: linee e fermate; residenti entro 400 m da una fermata:', f"{100 * sum(pop for dd, pop in ris[chr(102)+'ermata dell' + chr(39) + 'autobus'] if dd <= 400) / tot_ab:.0f}%")
    # fermate vicino ai poli di lavoro
    for q, (x, y, w) in poli.items():
        dmin = min(dist((x, y), (s['x'], s['y'])) for s in bus['stops'])
        print(f'  polo {q:22s} fermata più vicina al baricentro: {dmin:.0f} m')


if __name__ == '__main__':
    main()
