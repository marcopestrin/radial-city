# Censimento del resto della mappa: tutti i luoghi di places.json che il censimento di Centro, La Cerchia e delle tre
# strade non ha ancora (silos, stalle, serre, capannoni, fabbriche, supermercati, scalo merci, uffici, parchi, campi...),
# i palazzi residenziali senza contorno e le villette (che vanno in un file a parte).
#
# Lo usa tools/censimento.py (python3 tools/censimento.py scrive tutto).
#
# Ogni luogo diventa un record con gli stessi campi degli altri edifici (piani, abitanti, posti di lavoro, aziende);
# gli spazi senza edificio (parchi, piazze, campi coltivati, piste, cave) vanno tra gli spazi aperti. Posti di lavoro e
# piani sono le stime di tools/lavoratori.py (dal tipo di edificio), il tipo di attività quello di tools/strade.py.
import json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import centro
import strade
from centro import E
from lavoratori import assign_all, footprint

DATA = centro.DATA
ID_BASE = 20000                    # id degli edifici senza contorno (palazzi residenziali): non vanno in places.json
SOGLIA_PALAZZO = 30                # abitanti per casa: sopra, i "palazzi residenziali"; sotto, le villette
QUARTIERI_COMPLETI = ('Centro', 'La Cerchia')
GRANDE = 100000                    # m²: un contorno così grande è una zona, non un edificio

# spazi senza edificio: non hanno piani, ma hanno comunque un'identità (e qualche addetto di manutenzione)
APERTO = re.compile(r'^(Parco|Giardino|Piazza|Piazzetta|Campo|Campi|Dehors|Chiostro|Sagrato|Pista|Skatepark|Orti|Vigneti|'
                    r'Frutteto|Uliveto|Anfiteatro|Palestra all.aperto|Parcheggio(?! multipiano)|Area di|Lago|Cava|Piazzale)', re.I)
TIPO_SPAZIO = [
    (r'^(Campi coltivati|Campi della cascina|Orti|Vigneti|Frutteto|Uliveto|Area di allevamento)', 'coltivazione o pascolo'),
    (r'^(Parco|Giardino)', 'verde'),
    (r'^(Piazza|Piazzetta|Piazzale|Sagrato|Chiostro|Dehors)', 'piazza'),
    (r'^(Campo|Campi|Pista|Skatepark|Palestra all.aperto|Anfiteatro)', 'sport e tempo libero'),
    (r'^Parcheggio', 'parcheggio a raso'),
    (r'^(Cava|Lago)', "cava o specchio d'acqua"),
]
_TIPO_SPAZIO = [(re.compile(rx, re.I), t) for rx, t in TIPO_SPAZIO]

# cosa fa l'azienda: dal nome (la prima regola che corrisponde), altrimenti dalla categoria della mappa
RAMO = [
    (r'^(Stalla|Ricovero per il bestiame|Sala di mungitura|Azienda zootecnica)', 'allevamento di bestiame'),
    (r'^Serr', 'orticoltura in serra'),
    (r'^(Silo|Deposito (sementi|foraggi))', 'stoccaggio di cereali e mangimi'),
    (r'^(Fienile|Fienili|Essiccatoio)', 'deposito e lavorazione dei foraggi'),
    (r'^(Rimessa|Ricovero attrezzi|Magazzino agricolo)', 'rimessaggio di macchine e attrezzi agricoli'),
    (r'^(Cascina|Azienda agricola)', 'azienda agricola'),
    (r'^(Caseificio|Salumificio|Cantina|Barricaia|Vasche di fermentazione)', 'trasformazione alimentare'),
    (r'^(Agriturismo|Sala degustazione)', 'ospitalità e ristorazione agricola'),
    (r'ferroviari|^Scalo merci|^Pensilina binari|^Stazione ferroviaria', 'trasporto ferroviario'),
    (r'^(Logistica|Spedizion|Corriere|Smistamento|Centro distribuzione|Magazzino|Deposito|Cargo|Container)', 'logistica e magazzino'),
    (r'^(Centrale elettrica|Condensatori|Pannelli fotovoltaici)', 'produzione di energia'),
    (r'^(Data center)', 'servizi informatici'),
    (r'^(Officina|Carrozzeria|Elettrauto)', 'riparazione veicoli e macchinari'),
    (r'^(Supermercato|Discount|Ipermercato)', 'grande distribuzione alimentare'),
    (r'^(Bar|Ristorante|Pizzeria|Trattoria|Osteria|Gelateria|Pasticceria|Caff|Chiosco|Mensa|Panetteria)', 'ristorazione'),
    (r'^(Distributore|Stazione di servizio)', 'distribuzione di carburante'),
    (r'^(Studio|Uffici|Palazzo per uffici|Palazzina uffici|Torre per uffici|Coworking|Software|Agenzia|Banca|Assicurazioni)',
     'servizi alle imprese e terziario'),
    (r'^(Scuola|Istituto|Liceo|Università)', 'istruzione'),
    (r'^(Poliambulatorio|Centro analisi|Ospedale|Farmacia)', 'sanità'),
    (r'^(Laboratori|Botteghe|Falegnameria|Tappezzeria|Tornitura|Serramentista)', 'artigianato'),
]
_RAMO = [(re.compile(rx, re.I), r) for rx, r in RAMO]
RAMO_CAT = {'agr': 'agricoltura', 'ind': 'industria', 'art': 'artigianato', 'com': 'commercio', 'uff': 'servizi e uffici',
            'pub': 'servizio pubblico', 'res': 'residenziale'}

# destinazione d'uso, dal nome, per i tipi che la tabella delle attività di tools/centro.py chiama in altro modo
USO = [
    (r'^(Silo|Serbatoio|Fienile|Fienili|Rimessa|Ricovero attrezzi|Essiccatoio|Deposito|Magazzino|Tettoia|Vasche|Vasca|'
     r'Pensilina)', 'deposito'),
    (r'^(Stalla|Ricovero per il bestiame|Sala di mungitura|Azienda zootecnica|Serr|Cascina|Azienda agricola|Caseificio|'
     r'Salumificio|Cantina|Barricaia)', 'agricolo'),
    (r'(ferroviar|^Scalo merci|^Stazione ferroviaria)', 'ferroviario'),
    (r'^(Centrale elettrica|Condensatori|Pannelli fotovoltaici|Depuratore|Acquedotto|Discarica|Data center)', 'impianto'),
]
_USO = [(re.compile(rx, re.I), u) for rx, u in USO]


def ramo(nome, cat):
    for rx, r in _RAMO:
        if rx.search(nome):
            return r
    return RAMO_CAT.get(cat, 'attività')


def uso(nome, predefinito):
    for rx, u in _USO:
        if rx.search(nome):
            return u
    return predefinito


def tipo_spazio(nome):
    for rx, t in _TIPO_SPAZIO:
        if rx.search(nome):
            return t
    return 'spazio aperto'


def sigle(quartieri):
    """Un prefisso di codice unico per quartiere: le iniziali delle parole che contano (CAE = Campagna Est), allungate se
    serve; Centro e La Cerchia hanno CE e LC, le strade le loro sigle."""
    out = {'Centro': 'CE', 'La Cerchia': 'LC'}
    usate = set(out.values()) | {v['sigla'] for v in strade.STRADE.values()}
    articoli = {'di', 'del', 'della', 'dei', 'delle', 'degli', 'la', 'le', 'il', 'i', 'gli', 'lo', 'dell', 'da'}
    for q in quartieri:
        if q in out:
            continue
        parole = [w for w in re.split(r"[\s']+", q) if w]
        buone = [w for w in parole if w.lower() not in articoli] or parole
        cand = None
        for n in (2, 3, 4, 5):
            c = (''.join(w[0] for w in buone) + ''.join(buone)[1:]).upper()[:n]
            if c not in usate:
                cand = c
                break
        out[q] = cand
        usate.add(cand)
    return out


def ripartisci(tot, n):
    """`tot` diviso in `n` parti intere quasi uguali."""
    return [tot // n + (1 if i < tot % n else 0) for i in range(n)] if n else []


def edifici_resto(coperti):
    """Gli edifici e gli spazi aperti di tutti i luoghi di places.json non ancora censiti (`coperti` = i loro id).
    Restituisce (edifici, spazi): gli edifici come quelli di tools/strade.py (con `zona` = il quartiere), gli spazi come
    le voci di spazi_aperti del censimento."""
    places = json.load(open(os.path.join(DATA, 'places.json'), encoding='utf-8'))
    W = assign_all(places)
    prog, spazi = [], []
    per_lotto = {}
    for p in sorted(places, key=lambda p: (p['quarter'], p['lot'] or 0, p['id'])):
        if p['id'] in coperti:
            continue
        area = footprint(p['path'])
        if p['category'] != 'res' and (APERTO.search(p['name']) or area < 25):
            spazi.append(dict(quartiere=p['quarter'], lotto=p['lot'], luogo=p['id'], nome=p['name'],
                              tipo=tipo_spazio(p['name']) if APERTO.search(p['name']) else 'struttura',
                              superficie_m2=round(area), posti_di_lavoro=W[p['id']][0], abitanti=0))
            continue
        k = per_lotto[p['lot'] or 0] = per_lotto.get(p['lot'] or 0, 0) + 1
        if p['category'] == 'res':
            t, fl, cosa = 'casa', max(3, min(10, W[p['id']][1])), 'Abitazioni'
        else:
            t, fl, cosa = strade.tipo(p), max(1, min(15, W[p['id']][1])), p['name']
        posti = W[p['id']][0]
        if area > GRANDE and p['category'] in ('art', 'ind'):     # il contorno di un'intera zona: costruito circa un quarto
            posti = round(posti * 0.25)
        prog.append(dict(E(p['lot'] or 0, k, p['name'], p['category'], 'esistente', [(fl, t, cosa)], luogo=p['id']),
                         quartiere_vero=p['quarter'], posti=posti))
    out = []
    for e in prog:
        x = centro.edifici([e], e['quartiere_vero'], ID_BASE + len(out), set())[0]
        x['zona'] = e['quartiere_vero']
        t = e['piani'][0][1]
        a = centro.ATTIVITA.get(t, {})
        if t not in ('casa', 'uffici'):
            # un'impresa sola (o un ente), quella del luogo, occupa tutto l'edificio
            fl = x['piani_dettaglio']
            tot = e['posti']
            for f in fl:
                f['posti_di_lavoro'] = tot // len(fl) + (1 if f['piano'] < tot % len(fl) else 0)
                f['imprese'] = 0 if tot == 0 else (1 if f['piano'] == 0 else 0)
                f['aziende'] = [{'azienda': e['nome'], 'dipendenti': f['posti_di_lavoro']}] if f['posti_di_lavoro'] else []
                f['posti_liberi'] = 0
                f['destinazione_uso'] = uso(e['nome'], f['destinazione_uso'])
            r = ramo(e['nome'], e['cat'])
            x['aziende'] = [{'azienda': e['nome'], 'ramo': r,
                             'dipendenti': tot, 'piani': [f['piano'] for f in fl]}] if tot else []
        out.append(x)
    return out, spazi


def residenziale(coperti_lotti):
    """Palazzi residenziali senza contorno (case con SOGLIA_PALAZZO abitanti o più ciascuna) e villette (le altre) di tutti
    i lotti fuori da Centro e La Cerchia. `coperti_lotti` = {numero lotto: quante case sono già censite come edifici}.
    Restituisce (palazzi, villette): i palazzi come edifici di tools/centro.py, le villette come record piatti."""
    lots = json.load(open(os.path.join(DATA, 'lots.json'), encoding='utf-8'))
    places = json.load(open(os.path.join(DATA, 'places.json'), encoding='utf-8'))
    res_places = {}
    for p in places:
        if p['category'] == 'res':
            res_places[p['lot']] = res_places.get(p['lot'], 0) + 1
    prog, villette = [], []
    for l in sorted(lots, key=lambda l: l['number']):
        if l['quarter'] in QUARTIERI_COMPLETI or l['homes'] <= 0 or l['population'] <= 0:
            continue
        ab = l['population'] / l['homes']
        if ab >= SOGLIA_PALAZZO:
            n = l['homes'] - res_places.get(l['number'], 0) - coperti_lotti.get(l['number'], 0)
            alloggi = ab / centro.CASA['abitanti_per_alloggio'] / (1 - centro.CASA['alloggi_sfitti'])
            sup = alloggi * centro.CASA['m2_per_alloggio']
            fl = max(3, min(10, int(l.get('floors') or round(sup / 450))))
            for k in range(max(0, n)):
                prog.append(dict(E(l['number'], 50 + k, 'Palazzo residenziale', 'res', 'stimato', [(fl, 'casa', 'Abitazioni')]),
                                 quartiere_vero=l['quarter'], impronta=sup / fl))
        else:
            q, r = divmod(l['population'], l['homes'])
            for k in range(l['homes']):
                a = q + (1 if k < r else 0)
                allo = max(1, round(a / centro.CASA['abitanti_per_alloggio'] / (1 - centro.CASA['alloggi_sfitti']))) if a else 1
                lorda = allo * centro.CASA['m2_per_alloggio']
                villette.append({'quartiere': l['quarter'], 'lotto': l['number'], 'n': k + 1, 'abitanti': a,
                                 'alloggi': allo, 'piani': 2, 'superficie_lorda_m2': lorda,
                                 'superficie_impronta_m2': round(lorda / 2)})
    palazzi = []
    for e in prog:
        x = centro.edifici([e], e['quartiere_vero'], ID_BASE + 5000 + len(palazzi), set())[0]
        x['zona'] = e['quartiere_vero']
        palazzi.append(x)
    return palazzi, villette
