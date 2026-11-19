# Linee degli autobus: scrive public/data/bus.json (percorsi, fermate, stazioni di smistamento).
#
# Le strade sono lo spazio libero tra i lotti. Lo script le disegna su una griglia da 2,5 m e cerca il percorso
# più breve tra punti di passaggio scelti a mano, preferendo il centro della carreggiata. Il fiume è anch'esso
# spazio libero: lo si riconosce (largo e collegato alle scritte "Fiume Lento") e lo si penalizza, così gli
# autobus lo attraversano solo sui ponti.
#
# Servono numpy, scipy, scikit-image e Pillow.  Si lancia dalla radice del progetto:
#   python3 tools/linee_autobus.py
import json, math, re
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from skimage.graph import MCP_Geometric

DATA = 'public/data/'
RES = 2.5                      # metri per cella
X0, Y0, N = -1000.0, -1500.0, 2800

lots = json.load(open(DATA + 'lots.json', encoding='utf-8'))
places = json.load(open(DATA + 'places.json', encoding='utf-8'))
streets = json.load(open(DATA + 'streets.json', encoding='utf-8'))

# ------------------------------------------------------------------ stazione, smistamenti e linee
# Le 8 linee partono dalla stazione centrale, passano per i punti indicati e tornano in stazione (anelli).
# Non ci sono stazioni di smistamento: HUBS è vuoto.
STATION = dict(id='stazione', name='Stazione centrale', kind='station', at=(2470, 900))
HUBS = [
]
HUB_RADIUS_M = 150.0
ST = STATION['at']
LINES = [
    # (nome, punto) = fermata con quel nome; (nome, punto, lotto) = fermata che cita il lotto;
    # (False, punto) = solo passaggio, per tenere l'autobus su una strada precisa (nessuna fermata)
    dict(id='1', name='Linea 1', color='#E63946', via=[
        ('Belvedere', (3643, 800)), ('Incrocio lotti 700-579', (4330, 800)), ('Corso della Libertà', (4330, 240)),
        ('Via San Michele', (4470, -320)), (False, (4910, -320)), ('Via dei Prati', (4920, 240)), ("Viale dell'Industria", (4625, 800))]),
    dict(id='2', name='Linea 2', color='#1D8FE1', via=[
        ('Belvedere', (3643, 800)), ('Incrocio lotti 700-579', (4330, 800)), ('Via dei Cedri', (5180, 171)),
        ('Viale degli Olmi', (5337, 88)), ('Via degli Abeti', (5463, 185))]),
    dict(id='3', name='Linea 3', color='#2BB673', via=[
        ('Le Corti', (3200, 1500)), ('Aeroporto', (3249, 2413)), ("Viale dell'Aeroporto", (2170, 2425)),
        ('Corso Nazionale', (1720, 2350)), (None, (1720, 1809), 268), (None, (1720, 1297), 85), (None, (1959, 835), 23)]),
    dict(id='4', name='Linea 4', color='#8E44AD', via=[
        ('Tecnopolo', (2051, -121)), (False, (1720, -400)), ('Borgo Fiorito', (1720, -940)), ('Viale Roma', (1330, -800)),
        (False, (1330, -480)), ('San Lorenzo', (1532, -83)), ('Centro', (1712, 600))]),
    dict(id='5', name='Linea 5', color='#F2A900', via=[
        ('Centro', (1633, 782)), ('Borgo Fiera', (762, -30)), ('Villanova', (143, -73)), ('Incrocio lotti 308-309', (-215, -168)),
        ('Istituto professionale', (-540, 800), 589), ('Santa Lucia', (90, 800)), ('San Rocco', (860, 800))]),
    dict(id='6', name='Linea 6', color='#00A6A6', via=[
        (False, (2500, 1335)), ("Sant'Elena", (1950, 1730)), ('Parco del Lago', (893, 1921)),
        ('Via Carducci', (250, 1760)), ('Via Mazzini', (130, 2200)), ('Via delle Rogge', (250, 2640)), (False, (925, 2630)), ('Via Verdi', (930, 2300)),
        ('Viale del Sole', (1300, 2395)), (False, (2163, 2390)), ('Via Napoli', (2377, 1938)), (False, (2124, 1500))]),
    dict(id='7', name='Linea 7', color='#FF6F00', via=[
        ("Sant'Elena", (1728, 1950)), ("Sant'Anna", (1745, 3540)), ('Porta Sud', (2330, 5403)), ('Strada del Guado', (3477, 5111)),
        ('Riva dei Salici', (3760, 4800)), ('Zona Industriale Sud', (3748, 3786)), ('Strada di Levante', (3795, 2009))]),
    dict(id='8', name='Linea 8', color='#C2185B', via=[
        ("Sant'Anna", (1745, 3540)), ('Viale dei Gelsi', (1956, 3778)), ('Via degli Ulivi', (3480, 3800)),
        ('Via delle Acacie', (2860, 4400)), ('Via dei Mandorli', (2625, 4650)), (False, (3300, 4728)), ('Strada del Guado', (2700, 5140)), ('Porta Sud', (2020, 5185)),
        ('Corso Nazionale', (1720, 4800)), (False, (1720, 2600))]),
    dict(id='9', name='Linea 9', color='#795548', via=[
        (False, (1973, 1083)), ('Viale dei Mille', (1690, 1200)), (False, (1407, 1083)), ('Viale Roma', (1330, 1150)),
        ('Via Dante', (400, 1270)), (False, (-215, 1280)), ('Via Leopardi', (-215, 1950)), (False, (-215, 2630)),
        ('Via delle Rogge', (-40, 2640)), ('Via della Golena', (900, 2830)), 
        ('Corso Nazionale', (1720, 2400)), ('Viale Europa', (2368, 1467)), (False, (2592, 1128)), (False, (2635, 967))]),
]
STOP_SPACING = 450.0           # una fermata ogni ~450 m
SHARED_STOP_M = 120.0          # due linee usano la stessa fermata se sono più vicine di così
CATCHMENT_M = 350.0            # una fermata serve se entro questa distanza ci sono abitanti o attività


def coords(path):
    n = list(map(float, re.findall(r'-?\d+\.?\d*', path)))
    return list(zip(n[0::2], n[1::2]))


def subpaths(path):
    return [coords(s) for s in re.split(r'[MZ]', path) if len(coords(s)) >= 3]


def w2p(x, y):
    return int(round((y - Y0) / RES)), int(round((x - X0) / RES))


def p2w(i, j):
    return X0 + j * RES, Y0 + i * RES


# ------------------------------------------------------------------ griglia delle strade
mask = Image.new('L', (N, N), 0)
draw = ImageDraw.Draw(mask)
for lot in lots:
    for sp in subpaths(lot['path']):
        draw.polygon([((x - X0) / RES, (y - Y0) / RES) for x, y in sp], fill=255)
# strade che nei dati non hanno spazio tra i lotti (i due lotti si toccano) ma nella foto ci sono: si aprono a mano
ROADS_BETWEEN_LOTS = [
    (130, 2824, 1720, 2836),     # Via della Golena, tra i lotti 293 e 803
]
for x0_, y0_, x1_, y1_ in ROADS_BETWEEN_LOTS:
    draw.rectangle([(x0_ - X0) / RES, (y0_ - Y0) / RES, (x1_ - X0) / RES, (y1_ - Y0) / RES], fill=0)
free = np.array(mask) == 0
dist = ndimage.distance_transform_edt(free) * RES                 # metri dal lotto più vicino

seeds = [w2p(x, y) for s in streets if s['kind'] == 'river' for x, y in coords(s['path'])]
core = free & (dist >= 9.0)
labels, _ = ndimage.label(core)
river = np.isin(labels, list({labels[i, j] for i, j in seeds if labels[i, j] > 0}))
river = ndimage.binary_dilation(river, iterations=6) & free
ii, jj = np.nonzero(river)
avenue = (X0 + jj * RES > 1680) & (X0 + jj * RES < 1770)         # il viale nord-sud è largo come il fiume: non è fiume
river[ii[avenue], jj[avenue]] = False

parts, _ = ndimage.label(free, structure=np.ones((3, 3)))
network = parts == np.argmax(np.bincount(parts.ravel())[1:]) + 1      # la rete stradale collegata (niente sacche chiuse tra i lotti)

cost = np.full(free.shape, np.inf, np.float32)
centre = 1.0 + 3.0 * np.clip((6.0 - dist) / 6.0, 0, 1)            # più caro vicino ai bordi della strada
cost[free] = centre[free]
cost[river] *= 8

# la ferrovia (dalla stazione verso est-sud-est, retta per la scritta "Ferrovia") è spazio libero tra i lotti come una strada:
# la si rende cara, così gli autobus la attraversano ai passaggi a livello ma non la percorrono
I_, J_ = np.indices(free.shape)
XW, YW = X0 + J_ * RES, Y0 + I_ * RES
rail = free & (XW > 2380) & (np.abs(YW - (1351 + 0.25 * (XW - 3930))) / math.hypot(1, 0.25) <= 14.0)
cost[rail] *= 10


def snap(x, y, r=250.0):
    i0, j0 = w2p(x, y)
    k = int(r / RES)
    rows = slice(max(0, i0 - k), i0 + k + 1)
    cols = slice(max(0, j0 - k), j0 + k + 1)
    I, J = np.nonzero(network[rows, cols] & ~river[rows, cols] & ~rail[rows, cols])
    if len(I) == 0:
        raise SystemExit(f'nessuna strada entro {r} m da {x}, {y}')
    I = I + rows.start
    J = J + cols.start
    score = np.hypot(I - i0, J - j0) * RES - 2.0 * np.minimum(dist[I, J], 8)
    b = int(np.argmin(score))
    return int(I[b]), int(J[b])


def route(points):
    out = []
    for a, b in zip(points, points[1:]):
        sa, sb = snap(*a), snap(*b)
        mcp = MCP_Geometric(cost)
        mcp.find_costs([sa], [sb])
        seg = [p2w(i, j) for i, j in mcp.traceback(sb)]
        out += seg if not out else seg[1:]
    return out


def simplify(pts, eps=4.0):
    if len(pts) < 3:
        return pts
    a = np.array(pts)
    s, e = a[0], a[-1]
    v = e - s
    L = math.hypot(*v)
    d = np.hypot(*(a - s).T) if L == 0 else np.abs(v[0] * (a[:, 1] - s[1]) - v[1] * (a[:, 0] - s[0])) / L
    k = int(np.argmax(d))
    if d[k] > eps:
        return simplify(pts[:k + 1], eps)[:-1] + simplify(pts[k:], eps)
    return [pts[0], pts[-1]]


def length(p):
    return sum(math.dist(p[i], p[i + 1]) for i in range(len(p) - 1))


def along(p, s):
    """Il punto a distanza s dall'inizio della spezzata."""
    for a, b in zip(p, p[1:]):
        d = math.dist(a, b)
        if s <= d:
            t = s / d if d else 0
            return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        s -= d
    return p[-1]


def nearest_on(p, q, with_distance=False):
    """Distanza lungo la spezzata del punto più vicino a q."""
    best, acc = (float('inf'), 0.0), 0.0
    for a, b in zip(p, p[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / L2))
        c = (a[0] + dx * t, a[1] + dy * t)
        dd = math.dist(c, q)
        if dd < best[0]:
            best = (dd, acc + math.sqrt(L2) * t)
        acc += math.sqrt(L2)
    return best[1] if not with_distance else (best[1], best[0])


# ------------------------------------------------------------------ cosa c'è intorno a una fermata (nome, quartiere, se serve)
lot_points = [((l['label']['x'], l['label']['y']), l) for l in lots]
activity_points = [((p['bbox'][0] + p['bbox'][2]) / 2, (p['bbox'][1] + p['bbox'][3]) / 2) for p in places if p['category'] != 'agr']
street_points = [((x, y), s['name']) for s in streets if s['kind'] in ('main', 'minor', 'country') for x, y in coords(s['path'])]

# luoghi che danno il nome a una fermata: servizi e attività riconoscibili, non i nomi generici
GENERIC = re.compile(r'^(Uffici|Palazzina|Silo|Serbatoio|Stalla|Fienile|Pensilina|Parcheggio|Deposito|Magazzino|Tettoia|'
                     r'Spogliatoi|Tribuna|Ricovero|Rimessa|Serra|Essiccatoio|Laboratori|Botteghe|Distributore|Bar|Dehors|'
                     r'Cappella|Campanile|Canonica|Sagrato|Accesso|Vasca|Condensatori|Mensa)', re.I)
NOTABLE_SHOPS = re.compile(r'^(Hotel|Fiera|Cinema|Supermercato|Centro commerciale|Mercato)', re.I)
HOSPITAL_PARTS = re.compile(r'^(Neonatologia|Neurologia|Oncologia|Ematologia|Ortopedia|Cardiologia|Day hospital|Amministrazione ospedale)', re.I)
landmarks = []                 # (bbox, nome, peso): servizi pubblici grandi e pochi negozi notevoli
for p in places:
    b = p['bbox']
    size = (b[2] - b[0]) * (b[3] - b[1])
    name = 'Ospedale' if HOSPITAL_PARTS.match(p['name']) else p['name']
    if p['category'] == 'pub' and size >= 1500 and not GENERIC.match(name):
        landmarks.append((b, name, size * 3))
    elif p['category'] == 'com' and size >= 2000 and NOTABLE_SHOPS.match(name):
        landmarks.append((b, name, size))


def quarter_at(q):
    return min(lot_points, key=lambda lp: math.dist(lp[0], q))[1]['quarter']


def street_at(q, r=120.0):
    best = min(street_points, key=lambda sp: math.dist(sp[0], q))
    return best[1] if math.dist(best[0], q) <= r else None


def to_box(b, q):
    dx = max(b[0] - q[0], 0, q[0] - b[2])
    dy = max(b[1] - q[1], 0, q[1] - b[3])
    return math.hypot(dx, dy)


def landmark_at(q, r=60.0):
    near = [(weight, name) for b, name, weight in landmarks if to_box(b, q) <= r]
    return max(near)[1] if near else None


def stop_name(q):
    return landmark_at(q) or street_at(q) or quarter_at(q)


def useful(q):
    people = sum(l['population'] for pt, l in lot_points if math.dist(pt, q) <= CATCHMENT_M)
    jobs = sum(1 for pt in activity_points if math.dist(pt, q) <= CATCHMENT_M)
    return people >= 30 or jobs >= 3


# ------------------------------------------------------------------ percorsi e fermate
stops = {}                      # id -> fermata


def add_stop(kind, name, q, sid=None):
    sid = sid or f's{len(stops) + 1}'
    stops[sid] = dict(id=sid, name=name, quarter=quarter_at(q), kind=kind, x=round(q[0], 1), y=round(q[1], 1), lines=[])
    return sid


out_lines = []
for line in LINES:
    pts = simplify(route([ST] + [v[1] for v in line['via']] + [ST]))
    total = length(pts)
    if 'stazione' not in stops:
        add_stop('station', STATION['name'], pts[0], 'stazione')
    marks = [(0.0, 'stazione')]

    def stop_near(q, kind, name, named=False):
        near = [st for st in stops.values() if math.dist((st['x'], st['y']), q) <= SHARED_STOP_M]
        if near:
            st = near[0]
            if named and not st.get('_named') and st['kind'] == 'stop':
                st['name'], st['_named'] = name, True          # un punto indicato dà il nome alla fermata
            return st['id']
        sid = add_stop(kind, name, q)
        stops[sid]['_named'] = named
        return sid

    # i punti indicati: una fermata con quel nome dove il percorso passa più vicino
    via_ids = []
    for v in line['via']:
        label, pt, lot_n = v[0], v[1], (v[2] if len(v) > 2 else None)
        if label is False:
            continue
        s = nearest_on(pts, pt)
        q = along(pts, s)
        via_ids.append((stop_near(q, 'stop', label or stop_name(q), named=bool(label)), lot_n))
        marks.append((s, via_ids[-1][0]))
    # gli smistamenti vicini al percorso
    for h in HUBS:
        s, d = nearest_on(pts, h['at'], with_distance=True)
        if d <= HUB_RADIUS_M:
            if h['id'] not in stops:
                add_stop('hub', h['name'], along(pts, s), h['id'])
            marks.append((s, h['id']))
    # fermate intermedie, ogni STOP_SPACING metri, lontane dalle altre
    s = STOP_SPACING
    while s < total - STOP_SPACING / 2:
        q = along(pts, s)
        if all(abs(s - m) > STOP_SPACING * 0.55 for m, _ in marks) and useful(q):
            sid = stop_near(q, 'stop', stop_name(q))
            marks.append((s, sid))
        s += STOP_SPACING
    order = [sid for _, sid in sorted(marks)]
    order = [sid for k, sid in enumerate(order) if k == 0 or sid != order[k - 1]]
    for sid in order:
        if line['id'] not in stops[sid]['lines']:
            stops[sid]['lines'].append(line['id'])
    path = 'M' + ' '.join(f'{x:.1f},{y:.1f}' for x, y in pts)
    out_lines.append(dict(id=line['id'], name=line['name'], short=line['id'], color=line['color'], circular=True,
                          via=via_ids, lengthM=round(total), path=path, stops=order))
    print(f"{line['name']:<10} {round(total):>6} m  {len(order):>2} fermate")

# nomi doppi: i punti indicati tengono il loro nome; le altre fermate prendono il quartiere, poi un numero
for st in stops.values():
    st['_named'] = bool(st.get('_named')) or st['kind'] != 'stop'
groups = {}
for st in stops.values():
    groups.setdefault(st['name'], []).append(st)
for name, group in groups.items():
    if len(group) > 1:
        for g in group:
            if not g['_named'] and g['quarter'] != name:
                g['name'] = f"{name} ({g['quarter']})"
groups = {}
for st in stops.values():
    groups.setdefault(st['name'], []).append(st)
for name, group in groups.items():
    rest = [g for g in group if not g['_named']] if any(g['_named'] for g in group) else group
    if len(group) > 1:
        for k, g in enumerate(rest, 1):
            g['name'] = f'{name} {k}' if len(rest) > 1 or len(rest) < len(group) else name
for st in stops.values():
    st.pop('_named', None)

for line in out_lines:
    via = line.pop('via')
    line['description'] = ' → '.join(['Stazione centrale'] + [stops[i]['name'] + (f' (lotto {n})' if n else '') for i, n in via] + ['Stazione centrale'])
network = dict(updated='2026-11-13', lines=out_lines, stops=list(stops.values()))
with open(DATA + 'bus.json', 'w', encoding='utf-8') as fh:
    json.dump(network, fh, ensure_ascii=False, indent=1)
print(len(stops), 'fermate in tutto, di cui', sum(1 for s in stops.values() if len(s['lines']) > 1), 'condivise')
