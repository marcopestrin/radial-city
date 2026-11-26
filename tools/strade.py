# Censimento degli edifici sul fronte di Viale Roma, Corso Nazionale e Corso Garibaldi (fuori da Centro e La Cerchia, che
# hanno il loro programma): gli edifici restano come sono sulla mappa e nel satellite, qui si stimano piani, destinazione
# di ogni piano, abitanti, imprese e posti liberi con le regole di tools/centro.py.
#
#   python3 tools/strade.py   stampa i totali strada per strada (il censimento li legge con tools/censimento.py)
#
# Edifici sul fronte: gli edifici con una funzione (luoghi di places.json) a meno di FRONTE metri dalla strada, nei lotti
# che toccano la strada; e i palazzi residenziali di quei lotti, che sulla mappa non hanno un contorno: tanti quante le
# case del lotto in proporzione alla parte del lotto sul fronte (almeno uno), con gli abitanti del lotto divisi in parti
# uguali. Piani e posti di lavoro degli edifici con una funzione sono quelli di tools/lavoratori.py (dal tipo di
# edificio); gli uffici in affitto si dividono in aziende come nel Centro.
import json, os, re, sys

from shapely.geometry import LineString
from shapely.ops import unary_union

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import centro
from centro import E, poligono
from lavoratori import assign_all

DATA = centro.DATA
FRONTE = 45.0                     # profondità del fronte strada (m)
# le strade: tratti (asse della carreggiata), distanza massima del lotto dall'asse, sigla del codice
STRADE = {
    'Viale Roma': dict(tratti=[[(1330, -1500), (1330, 780)], [(1330, 812), (1330, 5500)]], tolleranza=20, sigla='VR'),
    'Corso Nazionale': dict(tratti=[[(1720, -1500), (1720, 5280)]], tolleranza=20, sigla='CN'),
    'Corso Garibaldi': dict(tratti=[[(-1000, 800), (1320, 800)]], tolleranza=13, sigla='CG'),
}
ESCLUSI = ('Centro', 'La Cerchia')   # hanno il loro programma (tools/centro.py, tools/cerchia.py)
ID_BASE = 5000                     # id dei palazzi residenziali senza contorno (non vanno in places.json)

# spazi aperti, coltivazioni e strutture senza piani: non sono edifici
APERTO = re.compile(r'^(Parco|Giardino|Piazza|Piazzetta|Pensilina|Campo|Campi|Tribuna\b|Dehors|Chiostro|Sagrato|Pista|'
                    r'Skatepark|Orti|Vigneti|Frutteto|Uliveto|Anfiteatro|Palestra all.aperto|Parcheggio(?! multipiano)|'
                    r'Area di|Silo|Serbatoio|Vasca|Lago|Cava|Piazzale|Tettoia|Fienil|Distributore|Stazione di servizio)', re.I)
# il tipo di attività (chiave di centro.ATTIVITA) dal nome e dalla categoria: la prima regola che corrisponde
TIPI = [
    (r'^(Uffici\b(?! comunali)|Palazzina uffici|Torre per uffici|Grattacielo)', None, 'uffici'),
    (r'^(Coworking|Incubatore)', None, 'coworking'),
    (r'^(Hotel|Albergo|Ostello|Residence|Agriturismo)', None, 'hotel'),
    (r'^Parcheggio multipiano', None, 'parcheggio'),
    (r'^(Cinema|Multisala|Sala bowling|Teatro)', None, 'cinema'),
    (r'^(Bar|Ristorante|Pizzeria|Trattoria|Osteria|Gelateria|Pasticceria|Caff|Chiosco|Fast food|Sushi|Wine bar|Pub|'
     r'Tavola calda|Piadineria|Enoteca|Mensa|Bistrot)', None, 'ristorante'),
    (r'^(Supermercato|Discount|Ipermercato|Centro commerciale|Galleria commerciale|Grande magazzino|Bricolage|Mobili|'
     r'Elettrodomestici|Giardinaggio|Abbigliamento outlet)', None, 'grande_magazzino'),
    (r'^(Concessionaria|Showroom)', None, 'showroom'),
    (r'^(Scuola|Liceo|Istituto|Asilo|Università|Facoltà|Dipartimento|Polo scolastico|Accademia|Conservatorio)', None, 'scuola'),
    (r'^(Ospedale|Pronto soccorso|Poliambulatorio|Casa della salute|Laboratorio analisi|Studio (pediatrico|medico)|'
     r'Centro (cardiologico|oculistico|diagnostico)|Casa di riposo|Sede ASL|Clinica)', None, 'sanita'),
    (r'^(Questura|Polizia|Commissariato|Caserma|Vigili del fuoco|Carabinieri|Guardia di Finanza)', None, 'sicurezza'),
    (r'^(Museo|Biblioteca|Galleria d.arte|Planetario|Fondazione|Centro culturale|Palestra|Palazzetto|Stadio|Piscina|'
     r'Centro (giovanile|sportivo|civico))', None, 'cultura'),
    (r'^(Chiesa|Duomo|Cappella|Oratorio|Canonica|Casa parrocchiale|Moschea|Sinagoga)', None, 'culto'),
    (r'^(Municipio|Palazzo comunale|Uffici comunali|Anagrafe|Prefettura|Tribunale|INPS|Agenzia delle entrate|Catasto|'
     r'Ufficio postale|Centro per l.impiego|Ispettorato|Stazione|Biglietteria|Terminal)', None, 'sportelli'),
    (None, 'uff', 'sede'), (None, 'com', 'negozi'), (None, 'pub', 'sportelli'),
    (None, 'ind', 'laboratorio'), (None, 'art', 'laboratorio'), (None, 'agr', 'agricolo'),
]
_TIPI = [(re.compile(rx, re.I) if rx else None, cat, t) for rx, cat, t in TIPI]


def tipo(p):
    for rx, cat, t in _TIPI:
        if (rx is None or rx.search(p['name'])) and (cat is None or cat == p['category']):
            return t
    return 'negozi'


def _asse(via):
    return unary_union([LineString(t) for t in STRADE[via]['tratti']])


def lotti():
    """I lotti che toccano una delle tre strade (fuori da Centro e La Cerchia): {numero: (lotto, poligono, strada)}."""
    out = {}
    for l in json.load(open(os.path.join(DATA, 'lots.json'), encoding='utf-8')):
        if l['quarter'] in ESCLUSI:
            continue
        g = poligono(l['path'])
        for via, s in STRADE.items():
            if g.distance(_asse(via)) < s['tolleranza']:
                out.setdefault(l['number'], (l, g, via))
                break
    return out


def programma():
    """Gli edifici sul fronte delle tre strade, come programma di tools/centro.py: forma 'esistente' per quelli con un
    contorno sulla mappa, 'stimato' per i palazzi residenziali."""
    places = json.load(open(os.path.join(DATA, 'places.json'), encoding='utf-8'))
    W = assign_all(places)
    ls = lotti()
    per_lotto = {}
    for p in places:
        if p['lot'] in ls:
            per_lotto.setdefault(p['lot'], []).append(p)
    out = []
    for n, (l, g, via) in sorted(ls.items()):
        asse = _asse(via)
        fronte = FRONTE + STRADE[via]['tolleranza']
        k = 0
        for p in sorted(per_lotto.get(n, []), key=lambda p: p['id']):
            pg = poligono(p['path'])
            if APERTO.search(p['name']) or pg.area < 25 or pg.distance(asse) > fronte:
                continue
            t = tipo(p)
            fl = W[p['id']][1]
            k += 1
            cat = p['category'] if p['category'] in ('res', 'uff', 'pub', 'com') else 'com'
            out.append(dict(E(n, k, p['name'], cat, 'esistente', [(max(1, min(15, fl)), t, p['name'])], luogo=p['id']),
                            strada=via, quartiere_vero=p['quarter']))
        if l['homes'] > 0 and l['population'] > 0:
            quota = g.intersection(asse.buffer(fronte)).area / g.area
            ab = l['population'] / l['homes']
            villette = ab < 30
            alloggi = ab / centro.CASA['abitanti_per_alloggio'] / (1 - centro.CASA['alloggi_sfitti'])
            sup = alloggi * centro.CASA['m2_per_alloggio']
            fl = 2 if villette else max(3, min(10, int(l.get('floors') or round(sup / 450))))
            for _ in range(max(1, round(l['homes'] * quota))):
                k += 1
                out.append(dict(E(n, k, 'Villetta' if villette else 'Palazzo residenziale', 'res', 'stimato',
                                  [(fl, 'casa', 'Abitazioni')]), strada=via, quartiere_vero=l['quarter'], impronta=sup / fl))
    return out


def edifici():
    """Gli edifici delle tre strade, con piani, abitanti e imprese (tools/centro.py); `zona` è la strada."""
    prog = programma()
    # i posti di lavoro degli edifici con un'impresa sola: la stima per tipo di edificio di tools/lavoratori.py (tiene
    # conto dei complessi con piazzali, cortili e prati, come la Fiera o il cimitero)
    W = assign_all(json.load(open(os.path.join(DATA, 'places.json'), encoding='utf-8')))
    out = []
    for e in prog:
        x = centro.edifici([e], e['quartiere_vero'], ID_BASE + len(out), set())[0]
        x['zona'] = e['strada']
        a = centro.ATTIVITA.get(e['piani'][0][1], {})
        if e['forma'] == 'esistente' and a.get('per_impresa') not in (0, 'aziende'):
            # un'impresa sola, quella del luogo, occupa tutto l'edificio
            fl = x['piani_dettaglio']
            tot = W[e['luogo']][0]
            for f in fl:
                f['posti_di_lavoro'] = tot // len(fl) + (1 if f['piano'] < tot % len(fl) else 0)
                f['imprese'] = 1 if f['piano'] == 0 else 0
                f['aziende'] = [{'azienda': e['nome'], 'dipendenti': f['posti_di_lavoro']}]
                f['posti_liberi'] = 0
            x['aziende'] = [{'azienda': e['nome'], 'ramo': None, 'dipendenti': sum(f['posti_di_lavoro'] for f in fl),
                             'piani': [f['piano'] for f in fl]}]
        out.append(x)
    return out


if __name__ == '__main__':
    es = edifici()
    for via in STRADE:
        sub = [e for e in es if e['zona'] == via]
        print(f"{via}: {len(sub)} edifici ({sum(1 for e in sub if e['forma'] == 'esistente')} con una funzione) · "
              f"abitanti {sum(p['abitanti'] for e in sub for p in e['piani_dettaglio'])} · "
              f"posti di lavoro {sum(p['posti_di_lavoro'] for e in sub for p in e['piani_dettaglio'])} · "
              f"posti liberi {sum(p.get('posti_liberi', 0) for e in sub for p in e['piani_dettaglio'])}")
