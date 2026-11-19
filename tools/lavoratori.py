# Stima dei lavoratori di ogni edificio (i dati della mappa non hanno il numero di addetti).
#
#   lavoratori = superficie di pavimento / metri quadri per addetto
#   superficie di pavimento = impronta dell'edificio (dal contorno) x numero di piani
#
# Piani e metri quadri per addetto dipendono dal tipo di edificio, riconosciuto dal nome; alcuni edifici
# hanno un numero fisso (un silo non ha addetti, uno stadio ne ha qualche decina tutti i giorni).
# Le regole sono in ordine: vale la prima che corrisponde. Sono valori medi da manuale, da tarare a piacere.
# Usato da tools/export_obsidian.py.
import math, re

CENTRE = {'Centro', 'La Cerchia'}       # nel centro gli edifici generici hanno più piani

# (espressione sul nome, categoria o None, piani, m² per addetto, addetti fissi, settore)
#   piani: numero, oppure 'h' = altezza scritta nel nome / 3,5 m
#   settore: privato | pubblico (dipendenti statali o di enti pubblici)
RULES = [
    # ---------------------------------------------------------------- niente addetti fissi
    (r'^(Silo|Serbatoio|Tettoia|Pensilina|Vasca|Condensatori|Fienile|Fienili|Rimessa|Ricovero attrezzi|Essiccatoio|'
     r'Deposito (sementi|foraggi)|Campo|Campi |Tribuna|Spogliatoi|Skatepark|Pista|Piazza|Piazzetta|Sagrato|Campanile|'
     r'Cappella|Lago di cava|Orti|Vigneti|Campi della cascina|Area di allevamento|Palestra all.aperto|Parcheggio (autobetoniere|autocisterne|mezzi pesanti)|'
     r'Piazzale|Dehors|Giardino pensile|Chiostro)', None, 1, None, 0, '—'),
    # ---------------------------------------------------------------- sanità (pubblica)
    (r'^(Ospedale|Pronto soccorso|Day hospital|Neurologia|Oncologia|Ematologia|Neonatologia|Ortopedia|Cardiologia|'
     r'Centro cardiologico|Amministrazione ospedale|Accesso ambulanze)', 'pub', 4, 30, None, 'pubblico'),
    (r'^(Poliambulatorio|Laboratorio analisi|Studio pediatrico|Centro oculistico|Centro analisi)', None, 2, 40, None, 'pubblico'),
    (r'^Casa di riposo', None, 3, 60, None, 'pubblico'),
    # ---------------------------------------------------------------- istruzione (pubblica)
    (r'^(Università|Facoltà|Dipartimento|Laboratori universitari|Biblioteca universitaria)', None, 3, 60, None, 'pubblico'),
    (r'^(Scuola|Liceo|Istituto (tecnico|professionale)|Polo scolastico)', 'pub', 2, 80, None, 'pubblico'),
    # ---------------------------------------------------------------- amministrazione, sicurezza, dogana (pubblica)
    (r'^(Prefettura|Questura|Tribunale|INPS|Agenzia delle entrate|Catasto|Anagrafe|Municipio|Palazzo (comunale|della Regione)|'
     r'Uffici (regionali|comunali|statali|doganali|ENAC|della Motorizzazione)|Centro per l.impiego|Polizia|Commissariato|'
     r'Caserma|Guardia di Finanza|Ispettorato|Ufficio postale|Sede ASL)', None, 3, 20, None, 'pubblico'),
    (r'^Vigili del fuoco', None, 1, None, 45, 'pubblico'),
    (r'^Castello di manovra', None, 1, None, 0, 'pubblico'),
    # ---------------------------------------------------------------- trasporti
    (r'^Terminal passeggeri', None, 2, 25, None, 'privato'),
    (r'^(Stazione ferroviaria)', None, 2, 40, None, 'pubblico'),
    (r'^Stazione autobus', None, 1, None, 20, 'pubblico'),
    (r'^(Torre di controllo|Uffici aeroportuali)', None, 3, 20, None, 'pubblico'),
    # ---------------------------------------------------------------- impianti
    (r'^Data center', None, 1, 250, None, 'privato'),
    (r'^Centrale elettrica', None, 1, None, 6, 'privato'),
    (r'^(Depuratore|Acquedotto)', None, 1, None, 8, 'pubblico'),
    (r'^Discarica', None, 1, None, 12, 'pubblico'),
    (r'^Serbatoio acqua', None, 1, None, 0, 'pubblico'),
    # ---------------------------------------------------------------- uffici con l'altezza nel nome
    (r'(Torre per uffici|Grattacielo|^Uffici) .*?(\d+) m', None, 'h', 15, None, 'privato'),
    (r'^Hotel.*?(\d+) m', None, 'h', 150, None, 'privato'),
    (r'^(Cava|Piazzale dei laterizi)', None, 1, None, 25, 'privato'),
    # ---------------------------------------------------------------- commercio
    (r'^(Distributore|Stazione di servizio)', None, 1, None, 2, 'privato'),
    (r'^Parcheggio multipiano', None, 5, None, 3, 'privato'),
    (r'^Parcheggio', None, 1, None, 2, 'privato'),
    (r'^(Grande magazzino|Galleria commerciale|Centro commerciale)', None, 4, 40, None, 'privato'),
    (r'^Cinema multisala', None, 2, 120, None, 'privato'),
    (r'^(Supermercato|Discount|Bricolage|Mobili|Concessionaria|Abbigliamento outlet|Ipermercato|Giardinaggio|Elettrodomestici)', 'com', 1, 60, None, 'privato'),
    (r'^(Padiglione fieristico|Fiera)', None, 1, 200, None, 'privato'),
    (r'^(Cinema|Sala bowling|Parco acquatico)', None, 1, 120, None, 'privato'),
    (r'^(Bar|Ristorante|Pizzeria|Trattoria|Osteria|Gelateria|Pasticceria|Caff|Chiosco|Fast food|Sushi|Wine bar|Pub|Tavola calda|Piadineria|Enoteca)', 'com', 1, 25, None, 'privato'),
    (r'^Agriturismo', None, 1, None, 8, 'privato'),
    (r'^Hotel', None, 3, 150, None, 'privato'),
    # ---------------------------------------------------------------- servizi pubblici vari
    (r'^Stadio', None, 1, None, 60, 'pubblico'),
    (r'^Palazzetto', None, 1, None, 25, 'pubblico'),
    (r'^(Museo|Biblioteca|Teatro|Planetario|Galleria|Fondazione|Anfiteatro)', None, 1, 120, None, 'pubblico'),
    (r'^(Chiesa|Canonica|Oratorio|Casa parrocchiale)', None, 1, None, 2, 'privato'),
    (r'^Cimitero', None, 1, None, 6, 'pubblico'),
    (r'^(Parco|Giardino)', None, 1, None, 2, 'pubblico'),
    (r'^Palestra', None, 1, 150, None, 'privato'),
    # ---------------------------------------------------------------- agricoltura
    (r'^(Stalla|Ricovero per il bestiame|Sala di mungitura)', 'agr', 1, 1500, None, 'privato'),
    (r'^Serr', 'agr', 1, 2500, None, 'privato'),
    (r'^(Cascina|Azienda)', 'agr', 1, None, 6, 'privato'),
    (r'^(Caseificio|Salumificio)', 'agr', 1, None, 8, 'privato'),
    (r'^(Cantina|Barricaia|Spaccio|Magazzino agricolo|Deposito)', 'agr', 1, None, 2, 'privato'),
    # ---------------------------------------------------------------- industria
    (r'(Logistica|Spedizion|Corriere|Smistamento|Centro distribuzione|Magazzino|Deposito|Cargo|Scalo|Container)', 'ind', 1, 120, None, 'privato'),
]
COMPILED = [(re.compile(rx, re.I), cat, fl, m2, fixed, sec) for rx, cat, fl, m2, fixed, sec in RULES]

# valori per categoria quando nessuna regola corrisponde: (piani, m² per addetto)
DEFAULTS = {'uff': (2, 18), 'com': (1, 40), 'ind': (1, 70), 'art': (1, 50), 'pub': (1, 60), 'agr': (1, 3000)}


def footprint(path):
    total = 0.0
    for sub in re.split(r'[MZ]', path):
        n = list(map(float, re.findall(r'-?\d+\.?\d*', sub)))
        p = list(zip(n[0::2], n[1::2]))
        if len(p) >= 3:
            total += abs(sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1] for i in range(len(p)))) / 2
    return total


def estimate(name, category, quarter, area_m2, floors=None):
    """Restituisce (lavoratori, piani, settore). `floors` forza il numero di piani."""
    if category == 'res':
        return 0, floors or 4, '—'
    for rx, cat, fl, m2, fixed, sector in COMPILED:
        if cat and cat != category:
            continue
        m = rx.search(name)
        if not m:
            continue
        if fl == 'h':
            height = float(m.groups()[-1])
            fl = max(1, round(height / (3.2 if name.startswith('Hotel') else 3.5)))
        fl = floors or fl
        if fixed is not None:
            return fixed, fl, sector
        return max(1, round(area_m2 * fl / m2)), fl, sector
    fl, m2 = DEFAULTS[category]
    if category == 'uff' and quarter in CENTRE:
        fl += 2                                  # negozi e bar del centro: piano terra; i piani sopra sono case
    fl = floors or fl
    if category == 'agr':
        return max(0, round(area_m2 / m2)), fl, 'privato'
    return max(1, round(area_m2 * fl / m2)), fl, 'privato'


def place_workers(place, covered=0.0):
    """`covered` = superficie degli edifici contenuti in questo luogo (vedi assign_all), che non va contata due volte."""
    return estimate(place['name'], place['category'], place['quarter'], max(0.0, footprint(place['path']) - covered))


def assign_all(places):
    """Lavoratori di tutti i luoghi: {id: (lavoratori, piani, settore)}.
    Alcuni luoghi sono il contorno di un complesso (campus, ospedale, fiera) che contiene altri edifici con un nome:
    al complesso si conta solo la parte non occupata da quegli edifici."""
    by_lot = {}
    for p in places:
        by_lot.setdefault(p['lot'], []).append(p)
    out = {}
    for p in places:
        b = p['bbox']
        area = footprint(p['path'])
        covered, inside = 0.0, 0
        for q in by_lot.get(p['lot'], []):
            c = q['bbox']
            if q is not p and c[0] >= b[0] and c[1] >= b[1] and c[2] <= b[2] and c[3] <= b[3]:
                qa = footprint(q['path'])
                if qa < area * 0.5:
                    covered += qa
                    inside += 1
        if inside >= 2:
            # un complesso: il suo contorno è soprattutto cortili, viali e prati; costruito circa un quarto del resto
            out[p['id']] = estimate(p['name'], p['category'], p['quarter'], max(0.0, area - covered) * 0.25)
        else:
            out[p['id']] = place_workers(p, covered)
    return out


# ------------------------------------------------------------------ piani stimati in Centro e La Cerchia
M2_PER_RESIDENT = 35        # superficie di casa per abitante
COVERAGE = 0.45             # parte del lotto coperta da edifici, nei lotti del centro
_HEIGHT = re.compile(r'(\d+) m\b')


def centre_floors(lots, places, workers):
    """Piani stimati: {numero lotto: piani dei palazzi abitati} e {id luogo: piani dell'edificio} per Centro e La Cerchia.
    I palazzi abitati: abitanti × 35 m² ÷ superficie costruibile (45% del lotto meno metà degli edifici con funzione), da 3 a 40.
    I negozi a un piano stanno al piano terra di un palazzo abitato: hanno i piani delle case del loro lotto."""
    built = {}
    for p in places:
        built[p['lot']] = built.get(p['lot'], 0) + footprint(p['path'])
    lot_floors = {}
    for l in lots:
        if l['quarter'] in CENTRE and l['population'] > 0:
            a = footprint(l['path'])
            free = max(a * COVERAGE - built.get(l['number'], 0) * 0.5, a * 0.15)
            lot_floors[l['number']] = int(min(40, max(3, round(l['population'] * M2_PER_RESIDENT / free))))
    place_floors = {}
    for p in places:
        if p['quarter'] in CENTRE:
            fl = workers[p['id']][1]
            if p['category'] == 'com' and fl == 1 and p['lot'] in lot_floors and not _HEIGHT.search(p['name']):
                fl = lot_floors[p['lot']]
            place_floors[p['id']] = fl
    return lot_floors, place_floors
