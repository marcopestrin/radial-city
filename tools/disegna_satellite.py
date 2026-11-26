# Disegna nelle immagini satellitari (public/tiles/*.jpg) gli edifici che la foto di base non ha
# (elenco DISEGNATI qui sotto).
#
# Parte SEMPRE dalle immagini di base in backup/tiles_originali/ (le copia lì la prima volta), così si può
# rilanciare senza disegnare due volte. Le immagini senza disegni restano identiche a quelle di base. Servono numpy e Pillow.
#   python3 tools/disegna_satellite.py            (tutto)
#   python3 tools/disegna_satellite.py 1834 ...   (solo i luoghi con questi id; le altre immagini tornano originali)
#   SENZA_NUOVI=1 USCITA=backup/base python3 tools/disegna_satellite.py
#       il satellite senza i tetti dei nuovi edifici (perimetri.json), in un'altra cartella: tools/perimetri.py lo guarda per
#       mettere i nuovi edifici su terreno libero (prato, terra) e non su parcheggi, tetti o strade
import json, math, os, random, re, shutil, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.join(os.path.dirname(__file__), '..')
os.chdir(ROOT)
ORIG = 'backup/tiles_originali/'
PX = 1.2                     # pixel per metro delle immagini satellitari
SS = 2                       # si disegna al doppio e poi si riduce: bordi morbidi come in una foto
S = PX * SS

world = json.load(open('public/data/world.json'))
places = json.load(open('public/data/places.json', encoding='utf-8'))
lots = {l['number']: l for l in json.load(open('public/data/lots.json', encoding='utf-8'))}
# i contorni degli edifici del censimento che la mappa non aveva (tools/perimetri.py): si disegna il loro tetto
PERIMETRI = os.environ.get('PERIMETRI', 'public/data/perimetri.json')      # (per le prove: un altro perimetri.json)
CONTORNI_NUOVI = [q for q in (json.load(open(PERIMETRI, encoding='utf-8')) if os.path.exists(PERIMETRI) else [])
                  if q['kind'] == 'footprint' and q.get('origine') != 'foto' and not os.environ.get('SENZA_NUOVI')]
USCITA = os.environ.get('USCITA', 'public').rstrip('/') + '/'

if not os.path.isdir(ORIG):
    os.makedirs(ORIG)
    for t in world['tiles']:
        shutil.copy2('public/' + t['file'], ORIG + os.path.basename(t['file']))
    print('copia delle immagini originali in', ORIG)
tiles = [(t, Image.open(ORIG + os.path.basename(t['file'])).convert('RGB')) for t in world['tiles']]
touched = set()


# ------------------------------------------------------------------ geometria
def coords(path):
    n = list(map(float, re.findall(r'-?\d+\.?\d*', path)))
    return list(zip(n[0::2], n[1::2]))


def area(p):
    return sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1] for i in range(len(p))) / 2


def main_poly(path):
    subs = [coords(s) for s in re.split(r'[MZ]', path) if len(coords(s)) >= 3]
    return max(subs, key=lambda p: abs(area(p)))


def centroid(p):
    a = area(p)
    cx = sum((p[i][0] + p[(i + 1) % len(p)][0]) * (p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1]) for i in range(len(p)))
    cy = sum((p[i][1] + p[(i + 1) % len(p)][1]) * (p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1]) for i in range(len(p)))
    return cx / (6 * a), cy / (6 * a)


def scale(p, f, c=None):
    cx, cy = c or centroid(p)
    return [(cx + (x - cx) * f, cy + (y - cy) * f) for x, y in p]


def inside(pt, poly):
    x, y = pt
    c = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[i - 1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def main_axis(p):
    """Angolo del lato più lungo: strisce, file e capannoni seguono questa direzione."""
    best = max(range(len(p)), key=lambda i: math.dist(p[i], p[i - 1]))
    (x1, y1), (x2, y2) = p[best - 1], p[best]
    return math.atan2(y2 - y1, x2 - x1)


# ------------------------------------------------------------------ una "toppa" disegnata in metri, poi incollata nelle immagini
class Patch:
    def __init__(self, poly, margin=30):
        xs = [x for x, _ in poly]
        ys = [y for _, y in poly]
        self.x0, self.y0 = min(xs) - margin, min(ys) - margin
        self.w = int((max(xs) + margin - self.x0) * S) + 1
        self.h = int((max(ys) + margin - self.y0) * S) + 1
        self.img = Image.new('RGBA', (self.w, self.h), (0, 0, 0, 0))

    def P(self, x, y):
        return ((x - self.x0) * S, (y - self.y0) * S)

    def layer(self):
        return Image.new('RGBA', (self.w, self.h), (0, 0, 0, 0))

    def mask(self, poly):
        m = Image.new('L', (self.w, self.h), 0)
        ImageDraw.Draw(m).polygon([self.P(*q) for q in poly], fill=255)
        return m

    def put(self, layer, clip=None):
        """Aggiunge un livello, ritagliato su un poligono se richiesto."""
        if clip is not None:
            a = np.array(layer)
            a[..., 3] = (a[..., 3].astype(np.uint16) * (np.array(self.mask(clip)) // 255)).astype(np.uint8)
            layer = Image.fromarray(a)
        self.img = Image.alpha_composite(self.img, layer)


def col(rgb, rng, var=10):
    return tuple(max(0, min(255, c + rng.randint(-var, var))) for c in rgb) + (255,)


def stripes(pt, poly, angle, period, width, color_a, color_b, rng):
    """Strisce parallele dentro il poligono (campi, pannelli, corsie, nervature dei tetti)."""
    L = pt.layer()
    d = ImageDraw.Draw(L)
    c = centroid(poly)
    R = max(math.dist(c, q) for q in poly) + period
    ux, uy = math.cos(angle), math.sin(angle)          # lungo le strisce
    vx, vy = -uy, ux                                   # attraverso
    k = -R
    i = 0
    while k < R:
        a = (c[0] + vx * k - ux * R, c[1] + vy * k - uy * R)
        b = (c[0] + vx * k + ux * R, c[1] + vy * k + uy * R)
        a2 = (a[0] + vx * width, a[1] + vy * width)
        b2 = (b[0] + vx * width, b[1] + vy * width)
        color = color_a if i % 2 == 0 else color_b
        if color:
            d.polygon([pt.P(*a), pt.P(*b), pt.P(*b2), pt.P(*a2)], fill=col(color, rng, 8))
        k += period
        i += 1
    pt.put(L, poly)


# ------------------------------------------------------------------ elementi
GRASS = (104, 136, 70)
TREE = (52, 82, 38)


def ground(pt, poly, rgb, rng):
    L = pt.layer()
    ImageDraw.Draw(L).polygon([pt.P(*q) for q in poly], fill=col(rgb, rng, 4))
    pt.put(L)


def trees(pt, poly, density, rng, rmin=2.5, rmax=5.5, avoid=()):
    L = pt.layer()
    d = ImageDraw.Draw(L)
    xs = [x for x, _ in poly]
    ys = [y for _, y in poly]
    for _ in range(int(abs(area(poly)) * density)):
        x, y = rng.uniform(min(xs), max(xs)), rng.uniform(min(ys), max(ys))
        if not inside((x, y), poly) or any(inside((x, y), a) for a in avoid):
            continue
        r = rng.uniform(rmin, rmax)
        d.ellipse([pt.P(x - r + 1.2, y - r + 1.2), pt.P(x + r + 1.2, y + r + 1.2)], fill=(20, 30, 15, 90))   # ombra
        d.ellipse([pt.P(x - r, y - r), pt.P(x + r, y + r)], fill=col(TREE, rng, 12))
        d.ellipse([pt.P(x - r * 0.5, y - r * 0.6), pt.P(x + r * 0.2, y - r * 0.05)], fill=col((80, 115, 55), rng, 10))
    pt.put(L, poly)


def path_cross(pt, poly, rng, width=3.5):
    c = centroid(poly)
    ang = main_axis(poly)
    L = pt.layer()
    d = ImageDraw.Draw(L)
    R = max(math.dist(c, q) for q in poly)
    for a in (ang, ang + math.pi / 2):
        ux, uy = math.cos(a), math.sin(a)
        d.line([pt.P(c[0] - ux * R, c[1] - uy * R), pt.P(c[0] + ux * R, c[1] + uy * R)], fill=col((196, 182, 150), rng, 6), width=int(width * S))
    r = min(12, R * 0.15)
    d.ellipse([pt.P(c[0] - r, c[1] - r), pt.P(c[0] + r, c[1] + r)], fill=col((196, 182, 150), rng, 6))
    pt.put(L, poly)


def roof(pt, poly, rgb, floors, rng, ribs=False, helipad=False, hvac=True):
    h = min(floors * 3.0 * 0.35, 16)
    L = pt.layer()
    ImageDraw.Draw(L).polygon([pt.P(x + h * 0.8, y + h * 0.6) for x, y in poly], fill=(15, 15, 12, 105))   # ombra verso sud-est
    pt.put(L)
    L = pt.layer()
    d = ImageDraw.Draw(L)
    base = col(rgb, rng, 6)
    d.polygon([pt.P(*q) for q in poly], fill=base, outline=tuple(max(0, c - 45) for c in base[:3]) + (255,))
    inner = scale(poly, 0.94)
    d.line([pt.P(*q) for q in inner + [inner[0]]], fill=tuple(min(255, c + 22) for c in base[:3]) + (255,), width=max(1, int(0.8 * S)))
    pt.put(L)
    if ribs:
        stripes(pt, scale(poly, 0.97), main_axis(poly) + math.pi / 2, 3.0, 1.0, tuple(max(0, c - 25) for c in rgb), None, rng)
    if hvac and abs(area(poly)) > 400:
        L = pt.layer()
        d = ImageDraw.Draw(L)
        xs = [x for x, _ in poly]
        ys = [y for _, y in poly]
        for _ in range(int(abs(area(poly)) / 350)):
            x, y = rng.uniform(min(xs), max(xs)), rng.uniform(min(ys), max(ys))
            w, hh = rng.uniform(1.5, 4), rng.uniform(1.5, 3)
            if inside((x, y), scale(poly, 0.85)):
                d.rectangle([pt.P(x, y), pt.P(x + w, y + hh)], fill=col((215, 215, 210), rng, 10))
                d.rectangle([pt.P(x + w, y + 0.3), pt.P(x + w + 0.8, y + hh + 0.6)], fill=(40, 40, 40, 120))
        pt.put(L, poly)
    if helipad:
        xs = [x for x, _ in poly]
        cx, cy = max(xs) - 22, centroid(poly)[1]
        L = pt.layer()
        d = ImageDraw.Draw(L)
        d.ellipse([pt.P(cx - 11, cy - 11), pt.P(cx + 11, cy + 11)], fill=(70, 75, 80, 255), outline=(235, 235, 230, 255), width=int(1.2 * S))
        for a, b in [((-4, -6), (-4, 6)), ((4, -6), (4, 6)), ((-4, 0), (4, 0))]:
            d.line([pt.P(cx + a[0], cy + a[1]), pt.P(cx + b[0], cy + b[1])], fill=(240, 240, 235, 255), width=int(1.4 * S))
        pt.put(L)


def parking(pt, poly, rng):
    ground(pt, poly, (92, 92, 92), rng)
    ang = main_axis(poly)
    stripes(pt, scale(poly, 0.92), ang, 16.0, 5.0, (78, 78, 80), None, rng)                 # corsie più scure
    L = pt.layer()
    d = ImageDraw.Draw(L)
    xs = [x for x, _ in poly]
    ys = [y for _, y in poly]
    cars = [(200, 200, 205), (40, 40, 45), (150, 30, 30), (60, 80, 140), (170, 170, 175), (230, 230, 230)]
    ux, uy = math.cos(ang), math.sin(ang)
    vx, vy = -uy, ux
    for _ in range(int(abs(area(poly)) / 18)):
        x, y = rng.uniform(min(xs), max(xs)), rng.uniform(min(ys), max(ys))
        if not inside((x, y), scale(poly, 0.9)) or rng.random() < 0.3:
            continue
        a = [(x - ux * 1 - vx * 2.2, y - uy * 1 - vy * 2.2), (x + ux * 1 - vx * 2.2, y + uy * 1 - vy * 2.2),
             (x + ux * 1 + vx * 2.2, y + uy * 1 + vy * 2.2), (x - ux * 1 + vx * 2.2, y - uy * 1 + vy * 2.2)]
        d.polygon([pt.P(*q) for q in a], fill=rng.choice(cars) + (255,))
    pt.put(L, poly)


def campus(pt, poly, roof_rgb, floors, rng, sports=True):
    """Un lotto intero: prato, cortile, edificio e, per le scuole, un campo sportivo."""
    ground(pt, poly, GRASS, rng)
    c = centroid(poly)
    ang = main_axis(poly)
    ux, uy = math.cos(ang), math.sin(ang)
    R = max(math.dist(c, q) for q in poly)
    bc = (c[0] - ux * R * 0.22, c[1] - uy * R * 0.22)          # edificio spostato verso un lato
    building = scale(poly, 0.42, bc) if abs(area(poly)) < 12000 else scale(poly, 0.33, bc)
    ground(pt, scale(poly, 0.62, bc), (176, 170, 158), rng)                                    # cortile
    roof(pt, building, roof_rgb, floors, rng)
    if sports:
        fc = (c[0] + ux * R * 0.45, c[1] + uy * R * 0.45)
        fw, fh = (40, 22) if abs(area(poly)) > 6000 else (24, 14)
        vx, vy = -uy, ux
        rect = [(fc[0] - ux * fw / 2 - vx * fh / 2, fc[1] - uy * fw / 2 - vy * fh / 2), (fc[0] + ux * fw / 2 - vx * fh / 2, fc[1] + uy * fw / 2 - vy * fh / 2),
                (fc[0] + ux * fw / 2 + vx * fh / 2, fc[1] + uy * fw / 2 + vy * fh / 2), (fc[0] - ux * fw / 2 + vx * fh / 2, fc[1] - uy * fw / 2 + vy * fh / 2)]
        if all(inside(q, poly) for q in rect):
            L = pt.layer()
            d = ImageDraw.Draw(L)
            d.polygon([pt.P(*q) for q in rect], fill=col((86, 150, 74), rng, 5), outline=(240, 240, 235, 255))
            mid = [((rect[0][0] + rect[1][0]) / 2, (rect[0][1] + rect[1][1]) / 2), ((rect[3][0] + rect[2][0]) / 2, (rect[3][1] + rect[2][1]) / 2)]
            d.line([pt.P(*mid[0]), pt.P(*mid[1])], fill=(240, 240, 235, 255), width=max(1, int(0.5 * S)))
            pt.put(L)
    trees(pt, poly, 0.0025, rng, avoid=[scale(poly, 0.66, bc)])


def houses(pt, poly, n_target, rng):
    """Villette con giardino, in file lungo due strade interne, con alberi e qualche piscina come nei quartieri vicini."""
    ground(pt, poly, (100, 128, 68), rng)
    c = centroid(poly)
    ang = main_axis(poly)
    ux, uy = math.cos(ang), math.sin(ang)
    vx, vy = -uy, ux
    R = max(math.dist(c, q) for q in poly)
    L = pt.layer()
    d = ImageDraw.Draw(L)
    for off in (-24, 24):
        a = (c[0] + vx * off - ux * R, c[1] + vy * off - uy * R)
        b = (c[0] + vx * off + ux * R, c[1] + vy * off + uy * R)
        d.line([pt.P(*a), pt.P(*b)], fill=col((108, 108, 104), rng, 4), width=int(6 * S))
    pt.put(L, scale(poly, 0.96))
    palette = [(166, 92, 70), (150, 82, 64), (128, 124, 122), (104, 104, 108), (176, 116, 88), (140, 102, 82), (186, 180, 170)]
    roofs = []
    for k in [-60, -36, -12, 12, 36, 60, -84, 84]:              # file di case ai lati delle strade (a ±24 m)
        for t in np.arange(-R, R, 15):
            x = c[0] + vx * (k + rng.uniform(-1.8, 1.8)) + ux * (t + rng.uniform(-1.5, 1.5))
            y = c[1] + vy * (k + rng.uniform(-1.8, 1.8)) + uy * (t + rng.uniform(-1.5, 1.5))
            hw, hd = rng.uniform(3.8, 5.8), rng.uniform(4.5, 6.8)
            q = [(x - ux * hw - vx * hd, y - uy * hw - vy * hd), (x + ux * hw - vx * hd, y + uy * hw - vy * hd),
                 (x + ux * hw + vx * hd, y + uy * hw + vy * hd), (x - ux * hw + vx * hd, y - uy * hw + vy * hd)]
            if all(inside(p, scale(poly, 0.95)) for p in q):
                roofs.append(q)
    rng.shuffle(roofs)
    roofs = roofs[:max(n_target, 1)]
    for q in roofs:
        L = pt.layer()
        d = ImageDraw.Draw(L)
        d.polygon([pt.P(x + 2.0, y + 1.5) for x, y in q], fill=(15, 15, 12, 100))
        base = col(rng.choice(palette), rng, 10)
        d.polygon([pt.P(*p) for p in q], fill=base)
        m1 = ((q[0][0] + q[3][0]) / 2, (q[0][1] + q[3][1]) / 2)
        m2 = ((q[1][0] + q[2][0]) / 2, (q[1][1] + q[2][1]) / 2)
        d.polygon([pt.P(*q[0]), pt.P(*q[1]), pt.P(*m2), pt.P(*m1)], fill=tuple(max(0, v - 26) for v in base[:3]) + (255,))   # falda in ombra
        if rng.random() < 0.15:                                    # piscina in giardino
            px_, py_ = q[2][0] + vx * 4, q[2][1] + vy * 4
            d.rectangle([pt.P(px_, py_), pt.P(px_ + 3, py_ + 5)], fill=(90, 175, 205, 255))
        pt.put(L, scale(poly, 0.97))
    trees(pt, poly, 0.004, rng, 2.2, 4.8, avoid=roofs)
    return len(roofs)


def warehouses(pt, poly, rng):
    ground(pt, poly, (118, 116, 110), rng)                    # piazzali
    ang = main_axis(poly)
    c = centroid(poly)
    ux, uy = math.cos(ang), math.sin(ang)
    vx, vy = -uy, ux
    R = max(math.dist(c, q) for q in poly)
    k = -R
    while k < R:
        for t0 in np.arange(-R, R, 100):
            q = [(c[0] + vx * k + ux * t0, c[1] + vy * k + uy * t0), (c[0] + vx * k + ux * (t0 + 88), c[1] + vy * k + uy * (t0 + 88)),
                 (c[0] + vx * (k + 40) + ux * (t0 + 88), c[1] + vy * (k + 40) + uy * (t0 + 88)), (c[0] + vx * (k + 40) + ux * t0, c[1] + vy * (k + 40) + uy * t0)]
            if all(inside(p, scale(poly, 0.97)) for p in q):
                roof(pt, q, (186, 108, 78), 3, rng, ribs=True, hvac=False)
        k += 58


# ------------------------------------------------------------------ pezzi di foto vera trapiantati
# Per alcuni luoghi, invece di disegnare, si copia un edificio vero della stessa foto (stessa luce, stesse ombre).
# id del luogo -> (riquadro sorgente minX, minY, maxX, maxY in metri, [riquadri da coprire con il prato preso da...])
#   at   = centro in cui incollarlo (metri; se manca, il centro del luogo)
#   rot  = rotazione in gradi (antiorari) del pezzo già raddrizzato, per seguire una strada inclinata
#   clip = True: il pezzo si ritaglia sul contorno del luogo, con un bordo sfumato; 'lot': sul contorno del lotto (per i
#          luoghi il cui contorno è solo l'edificio, mentre il pezzo comprende anche il parcheggio)
#   scale può essere (sx, sy) per adattare una fila di case alla profondità del lotto
#   shadow = (dx, dy) in metri: ombra disegnata sotto il pezzo (per i tetti ritagliati senza la loro ombra)
# L'ospedale del lotto 209 è inclinato di 50°: h209(fx, fy) dà il punto della foto che, raddrizzato l'ospedale (rotazione di
# -50° attorno a 2366,1294), sta a fx, fy metri dal centro; box209 il riquadro sorgente attorno; wing209 un tratto lungo
# `length` di uno dei due bracci (centrato in fx, fy, spesso 17 m), ingrandito di 1,1 e con l'ombra.
def h209(fx, fy):
    c, s_ = math.cos(math.radians(-50)), math.sin(math.radians(-50))
    return (2366 + fx * c - fy * s_, 1294 + fx * s_ + fy * c)


def box209(fx, fy, r=130):
    x, y = h209(fx, fy)
    return (x - r, y - r, x + r, y + r)


def wing209(fx, fy, length, at, flip=False):
    return dict(src=box209(fx, fy), center=h209(fx, fy), angle=-50.0, size=(length, 17), scale=1.1, feather=1.0, at=at,
                shadow=(5, 4), flip=flip)


PK808 = (1497, 5030, 1597, 5180)          # parcheggio dei negozi del lotto 808 (la parte pulita: x 1522-1572, y 5058-5150)
PK807 = (1407, 5030, 1507, 5180)          # parcheggio dei negozi del lotto 807 (x 1434-1480, y 5060-5150)
PK806 = (1180, 5110, 1410, 5210)          # parcheggio del discount del lotto 806: file est-ovest lunghe 190 m (x 1206-1386)


def band806(x0, x1, y0, y1, fx=0.0, flip=False):
    """Una fascia di parcheggio da x0 a x1, y0 a y1 (alta al massimo 32 m), presa dal parcheggio del lotto 806: le file di
    auto corrono est-ovest per tutta la larghezza, senza giunture; fx sposta il ritaglio lungo il parcheggio."""
    return dict(src=PK806, center=(1296 + fx, 5160 - 13 + (y1 - y0) / 2), size=(x1 - x0, y1 - y0), feather=0.6,
                at=((x0 + x1) / 2, (y0 + y1) / 2), flip=flip)


PK54A = {k: v for k, v in band806(0, 54, 0, 22).items() if k != 'at'}
PK54B = {k: v for k, v in band806(0, 54, 0, 22, fx=30, flip=True).items() if k != 'at'}

TRANSPLANT = {
    # Scuola dell'infanzia, lotto 57 (La Cerchia): il centro giovanile col tetto arancione di La Cerchia (lotto 2),
    # raddrizzato e rimpicciolito, nella parte larga del lotto a est; a ovest il giardino coi giochi, su un prato.
    1832: [dict(src=(1630, 2315, 1710, 2395), center=(1670, 2355), size=(60, 60), feather=6.0, at=(x, y),
                flip=(i + j) % 2 == 1, clip=True)
           for i, x in enumerate((2130, 2165, 2200, 2230)) for j, y in enumerate((765, 785))]
          + [dict(src=(1530, 300, 1625, 375), center=(1577, 337), angle=-9.5, size=(70, 50), feather=1.5, scale=0.66,
                  at=(2200, 770), clip=True, shadow=(2, 2)),
             dict(src=(1530, 2365, 1575, 2400), center=(1554, 2384), size=(16, 16), feather=1.5, at=(2150, 778), clip=True)],
    # Palestra, lotto 657 (Parco del Lago, il triangolo tra le due strade e la diagonale): la palestra col tetto a pannelli
    # solari di Le Magnolie (lotto 868), un po' più piccola, nell'angolo retto a nord-est; il resto resta prato alberato.
    1887: dict(src=(3685, 4585, 3740, 4630), center=(3712, 4607), size=(42, 32), feather=1.0, scale=0.72,
               at=(1108.5, 2308.5), clip='lot', shadow=(2, 2)),
    # Laboratori artigiani, lotto 658 (Parco del Lago): due capannoni lunghi della Zona Artigianale (lotti 1381-1382), col
    # piazzale di carico a nord e il parcheggio davanti a quello a sud; ogni capannone è fatto con le sue due testate vere
    # (ovest ed est) accostate, così risulta lungo quanto il lotto senza deformare tetti e auto.
    1888: [dict(src=(1250, 4040, 1540, 4180), center=(cx, cy), size=(99, h), feather=1.0, at=(ax, ay), clip=True)
           for cy, h, ay in ((4079, 36, 2238.4), (4137.5, 35, 2274.1))
           for cx, ax in ((1323, 1175.4), (1463, 1269.2))],
    # Lotti 52 e 54 (La Cerchia), lungo il viale a -26,6°: i pezzi si raddrizzano e poi si girano di 26,6° (rot).
    # Scuola primaria, lotto 52: la scuola a U di Campagna Est (lotto 579) col giardino nella corte, su un prato.
    1833: [dict(src=(1630, 2315, 1710, 2395), center=(1670, 2355), size=(60, 60), feather=6.0, at=(x, y),
                flip=(i + j) % 2 == 1, clip=True)
           for i, x in enumerate((2190, 2225, 2260, 2295)) for j, y in enumerate((500, 535, 570))]
          + [dict(src=(4340, 940, 4470, 1020), center=(4404.5, 980.5), size=(118, 62), feather=2.0, rot=26.6,
                  at=(2242.4, 539.0), clip=True, shadow=(3, 3))],
    # Uffici comunali, lotto 54: due stecche per uffici dal tetto bianco (gli uffici tecnici della Zona Industriale Sud e
    # la palazzina uffici del Polo Logistico), parallele al viale con un cortile in mezzo, a ovest, e il
    # parcheggio dei dipendenti e del pubblico (le file del discount del lotto 806) a est, sul prato del lotto.
    1843: [dict(src=(1630, 2315, 1710, 2395), center=(1670, 2355), size=(60, 60), feather=6.0, at=(x, y),
                flip=(i + j) % 2 == 1, clip='lot')
           for i, x in enumerate((2080, 2115, 2150, 2185)) for j, y in enumerate((560, 595, 630))]
          + [dict(PK54A, rot=26.6, at=(2150.2, 573.0), clip='lot'), dict(PK54B, rot=26.6, at=(2160.0, 592.7), clip='lot'),
             dict(src=(3760, 4115, 3850, 4150), center=(3806.3, 4133), size=(58, 18), feather=1.0, scale=0.95,
                  rot=26.6, at=(2100.4, 598.6), clip='lot', shadow=(2, 2)),
             dict(src=(3235, 1065, 3325, 1100), center=(3281, 1082.3), size=(58, 18), feather=1.0, scale=0.95,
                  rot=26.6, at=(2109.8, 617.3), clip='lot', shadow=(2, 2))],
    # Lotto 460 (Le Grazie), i servizi che mancavano al quartiere, tutti su un prato con alberi (il giardino della scuola
    # primaria di Borgo Nazionale). Scuola media: la scuola a U del Tecnopolo (lotto 161) raddrizzata, col campo da calcio
    # e il campo da basket della primaria di Borgo Nazionale a sud.
    1871: [dict(src=(1630, 2315, 1710, 2395), center=(1670, 2355), size=(60, 60), feather=6.0, at=(x, y), flip=(i + j) % 2 == 1, clip=True)
           for i, x in enumerate((-405, -365, -330)) for j, y in enumerate((2340, 2380, 2415))]
          + [dict(src=(1780, -450, 1975, -305), center=(1878, -378), angle=-18.0, size=(100, 66), feather=2.0,
                  at=(-370, 2358), clip=True),
             dict(src=(1515, 2315, 1595, 2367), center=(1555.5, 2341), size=(70, 42), feather=1.5, at=(-382, 2408),
                  clip=True),
             dict(src=(1590, 2338, 1630, 2366), center=(1609.5, 2352), size=(36, 24), feather=1.5, at=(-330, 2410),
                  clip=True)],
    # Casa della salute (medici di base, pediatra, consultorio): l'edificio basso col tetto a pannelli solari del
    # Tecnopolo, raddrizzato, col parcheggio dei pazienti (le file di auto del discount del lotto 806) a est.
    1921: [dict(src=(1630, 2315, 1710, 2395), center=(1670, 2355), size=(60, 60), feather=6.0, at=(x, y), flip=(i + j) % 2 == 1, clip=True)
           for i, x in enumerate((-295, -255, -230)) for j, y in enumerate((2335, 2365))]
          + [band806(-252, -219, 2323, 2349), band806(-252, -219, 2349, 2374, fx=30, flip=True),
             dict(src=(1915, -420, 1990, -360), center=(1952, -390), angle=-18.0, size=(50, 38), feather=1.5,
                  at=(-283, 2348), clip=True)],
    # Campi da tennis della scuola media: i due campi affiancati di Gli Olmi (lotto 838), sul prato a sud della casa
    # della salute (dove era previsto il centro civico).
    1922: [dict(src=(1630, 2315, 1710, 2395), center=(1670, 2355), size=(60, 60), feather=6.0, at=(x, y),
                flip=(i + j) % 2 == 1, clip='lot')
           for i, x in enumerate((-295, -255, -230)) for j, y in enumerate((2390, 2408, 2422))]
          + [dict(src=(5215, 425, 5280, 485), center=(5247.5, 455.5), size=(42, 40), feather=1.5, at=(-266, 2404.5),
                  clip='lot')],
    # Scuola primaria, lotto 516 (Parco del Lago): il complesso della scuola primaria di Borgo Nazionale (lotto 291), con la
    # scuola a U e gli scuolabus sulla strada sud, il campo da calcio, il campo da basket, la palestra e il suo parcheggio,
    # su un prato con alberi (preso dal giardino della stessa scuola) che copre tutto il lotto.
    1879: [dict(src=(1630, 2315, 1710, 2395), center=(1670, 2355), size=(60, 60), feather=6.0, at=(x, y),
                flip=(i + j) % 2 == 1, clip=True)
           for i, x in enumerate((705, 750, 795, 840, 885, 915)) for j, y in enumerate((2545, 2585, 2625))]
          + [dict(src=(1500, 2310, 1715, 2445), center=(1607.5, 2376.5), size=(185, 111), feather=2.0,
                  at=(778.5, 2580.65), clip=True)],
    # Scuola dell'infanzia e asilo nido, lotto 515: edifici bassi dritti, paralleli alle strade. L'infanzia è la palestra
    # col tetto rosso di Santa Lucia (lotto 436), più grande, col giardino dei giochi (quello nella corte della primaria
    # di Borgo Nazionale) a est; il nido è lo stesso tetto rosso più corto con un'ala grigia bassa (la scuola di danza di
    # Santa Lucia) attaccata a est, e i giochi a ovest.
    1878: [dict(src=(1630, 2315, 1710, 2395), center=(1670, 2355), size=(60, 60), feather=6.0, at=(x, y),
                flip=i % 2 == 1, clip=True) for i, x in enumerate((545, 590, 635, 665)) for y in (2540, 2570)]
          + [dict(src=(-85, 825, -5, 860), center=(-46.8, 843.3), size=(56, 17), scale=1.25, feather=1.0,
                  at=(588, 2550), clip=True, shadow=(2.5, 2)),
             dict(src=(1530, 2365, 1575, 2400), center=(1554, 2384), size=(16, 16), feather=1.5, at=(652, 2556), clip=True)],
    1919: [dict(src=(1630, 2315, 1710, 2395), center=(1670, 2355), size=(60, 60), feather=6.0, at=(x, y),
                flip=i % 2 == 0, clip=True) for i, x in enumerate((545, 590, 635, 665)) for y in (2595, 2625)]
          + [dict(src=(-85, 825, -5, 860), center=(-46.8, 843.3), size=(56, 17), scale=0.9, feather=1.0,
                  at=(604, 2610), clip=True, shadow=(2.5, 2)),
             dict(src=(-130, 828, -85, 860), center=(-107.8, 843), size=(31, 19), scale=1.0, feather=1.0,
                  at=(644.5, 2611), clip=True, shadow=(2.5, 2)),
             dict(src=(1530, 2365, 1575, 2400), center=(1554, 2384), size=(16, 16), feather=1.5, flip=True, at=(553, 2606), clip=True)],
    # Scuola media, lotto 65: l'edificio a L del Tecnopolo (lotto 161), raddrizzato e un po' ingrandito, sul prato
    # originale del lotto (niente campo da calcio).
    1834: dict(src=(1780, -450, 1975, -305), center=(1878, -378), angle=-18.0, size=(100, 66), scale=1.12),
    # Bar, lotto 66 (dove c'era la stazione autobus Ovest): il bar del lotto 85, sul lastricato
    1839: dict(src=(1735, 1280, 1790, 1330), center=(1761, 1303), angle=0.0, size=(22, 19), scale=0.7, feather=1.5),
    # Ospedale di Porta Sud, lotto 937. Un corpo nord-sud sul retro (ingresso) con tre ali est-ovest, perpendicolari a Corso
    # Nazionale, e davanti a ogni ala un padiglione separato; dietro, il blocco dei laboratori e l'eliporto. Ali, corpo e
    # padiglioni sono tratti dei due bracci lunghi dell'ospedale del lotto 209, il blocco dei laboratori è il suo blocco
    # centrale: tutto ritagliato sul solo tetto, con l'ombra verso sud-est come gli edifici vicini. Giardini solo tra le ali.
    1836: dict(src=box209(-50, 39.5), center=h209(-50, 39.5), angle=40.0, size=(17, 98.8), scale=1.1, feather=1.0,
               at=(1309.35, 4952.0), shadow=(5, 4)),                                          # corpo nord-sud (ingresso)
    1910: wing209(-53.9, 39.5, 98.2, (1366.0, 4907.0)),                                       # ala nord: degenze
    1913: wing209(-50.9, -31.5, 98.2, (1366.0, 4952.0)),                                      # ala centrale: chirurgia
    1911: wing209(29.0, 39.5, 98.2, (1366.0, 4997.0), flip=True),                             # ala sud: ambulatori
    1914: wing209(41.4, -31.5, 72.7, (1472.0, 4907.0)),                                       # padiglione nord: maternità
    1837: wing209(61.4, 39.5, 72.7, (1472.0, 4952.0)),                                        # padiglione centrale: pronto soccorso
    1915: wing209(-58.7, -31.5, 72.7, (1472.0, 4997.0), flip=True),                           # padiglione sud: prelievi
    1916: dict(src=box209(-4, -84.5), center=h209(-4, -84.5), angle=-50.0, size=(62, 75), scale=1.0, feather=1.0,
               at=(1236.0, 4936.5), shadow=(5, 4)),                                           # laboratori e radiologia
    # Eliporto: la piazzola sul tetto di un'ala dell'ospedale del lotto 209, sul tetto del pronto soccorso (testata est)
    1912: dict(src=box209(-34.4, 87.5), center=h209(-34.4, 87.5), angle=-50.0, size=(18, 18), scale=1.0, feather=1.0),
    # Parcheggi dell'ospedale, fatti a fasce del parcheggio del discount del lotto 806 (file di auto est-ovest continue):
    # davanti, tra i padiglioni e Corso Nazionale, ai lati del viale d'accesso (un pezzo della traversa che sbocca sul corso
    # dal lato opposto, raddrizzata, in tratti), e in mezzo alle ali, dal corpo nord-sud fino a quello davanti.
    1838: [band806(1525, 1700, 4897, 4922.6, flip=True), band806(1525, 1700, 4931.5, 4963.5),
           band806(1525, 1700, 4963.5, 4995.5, flip=True), band806(1525, 1700, 4995.5, 5010.75)]
          + [dict(src=(1730, 4890, 1840, 4970), center=(1782, 4928.5), angle=3.2, size=(64, 10.5), at=(x, 4926.9),
                  feather=1.5, flip=fl, clip='lot')
             for x, fl in ((1452.0, False), (1514.0, True), (1576.0, False), (1638.0, True), (1676.0, False))],
    1918: [band806(1317.7, 1421, 4916.35, 4942.65, fx=-40), band806(1420, 1525, 4916.35, 4942.65, fx=40, flip=True)],
    1917: [band806(1317.7, 1421, 4961.35, 4987.65, fx=40, flip=True), band806(1420, 1525, 4961.35, 4987.65, fx=-40)],
    # Istituto tecnico, lotto 253: la parte nord dell'istituto professionale del lotto 589 (edificio a L in mattoni,
    # edificio bianco, alberi), girata come la strada
    1835: dict(src=(-680, 780, -410, 910), center=(-546, 845), angle=0.0, size=(212, 78), scale=0.95, rot=15.0, clip=True),
    # Panetteria, frutta e verdura e pescheria, lotto 251: tre negozietti in fila lungo la strada (girati come lei), ognuno
    # col suo parcheggio davanti, presi dalla fila di negozi dei lotti 378 e 382 (l'ottica, il fruttivendolo e la scuola di danza);
    # ogni parcheggio ha un passo carraio d'asfalto (dal parcheggio vuoto della cartoleria) sopra l'aiuola fino alla strada
    1852: [dict(src=(-233.5, 778, -113.5, 878), center=(-173.5, 828), angle=0.0, size=(48, 34), scale=1.0, at=(2103.9, 2292.2), rot=15.0, clip='lot'),
           dict(src=(-15, 800, 45, 840), center=(15, 820), size=(9, 14), feather=1.0, at=(2089.9, 2278.3), rot=15.0)],
    1900: [dict(src=(-311, 778.5, -191, 878.5), center=(-251, 828.5), angle=0.0, size=(43, 35), scale=1.0, at=(2151.2, 2281.1), rot=15.0, clip='lot'),
           dict(src=(-15, 800, 45, 840), center=(15, 820), size=(9, 14), feather=1.0, at=(2145.9, 2263.3), rot=15.0)],
    1901: [dict(src=(-168, 783, -48, 883), center=(-108, 833), angle=0.0, size=(36, 44), scale=1.0, at=(2193.1, 2273.5), rot=15.0, clip='lot'),
           dict(src=(-15, 800, 45, 840), center=(15, 820), size=(9, 14), feather=1.0, at=(2187.4, 2252.2), rot=15.0)],
    # Supermercato di quartiere, lotto 304 (Villanova, prima un campo): a ovest una fetta del parcheggio del discount del
    # lotto 806 con un passo carraio sulla strada a sud, a est il supermercato del lotto 374 (tetto con i pannelli solari)
    1861: [dict(src=(1180, 5110, 1300, 5210), center=(1240, 5162), angle=0.0, size=(56, 35), scale=1.0, at=(163.5, -391.85), clip='lot'),
           dict(src=(-130, 700, -10, 820), center=(-70, 759.5), angle=0.0, size=(60, 35), scale=1.0, at=(222.3, -391.85), clip='lot'),
           dict(src=(-15, 800, 45, 840), center=(15, 820), size=(9, 9), feather=1.0, at=(150, -374))],
    # Panetteria, gelateria e fioraio, lotto 469 (Parco del Lago, prima un giardinetto): un tratto della fila di negozi
    # del lotto 378 (la palestra col tetto rosso e la cartoleria, coi parcheggi davanti), coi parcheggi sulla strada a nord
    1873: dict(src=(-110, 790, 65, 880), center=(-23, 832.5), size=(116, 37), scale=0.98, at=(582.3, 1326.85), clip='lot'),
    1866: dict(src=(3566, 4252, 3642, 4328), center=(3604, 4290), size=(60, 60), feather=1.5, at=(149.5, 1075.2), clip='lot'),
    # Condominio, lotto 447 (Le Grazie, nel giardinetto tra le villette): la palazzina a stecca del lotto 206 (Le Corti),
    # con la sua ombra e un po' del cortile lastricato, che sfuma nel prato del giardino
    1870: dict(src=(3063, 1480, 3183, 1580), center=(3123, 1530.5), size=(68, 35), feather=4.0, at=(224, 1681.4), clip='lot'),
    # Lotto 294: il capannone col tetto fotovoltaico diviso in due stabili (a nord la lavorazione dell'alluminio, a sud il
    # calzaturificio) da un piazzale che va dal cortile a ovest al parcheggio a est. Il piazzale è un pezzo del cortile
    # ovest dello stesso stabilimento, girato in orizzontale; sopra, la testata sud del capannone (con la sua ombra) chiude
    # lo stabile nord e la testata nord (col marciapiede) apre quello sud.
    1904: [dict(src=(1400, 2530, 1584, 2714), center=(1492, 2622), angle=90.0, size=(172, 24), feather=1.5, at=(1590.5, 2674), clip='lot'),
           dict(src=(1500, 2780, 1670, 2830), center=(1585.5, 2803), size=(153, 16), feather=1.0, at=(1585.5, 2662), clip='lot'),
           dict(src=(1500, 2490, 1665, 2535), center=(1582.25, 2513.5), size=(146.5, 11), feather=1.0, at=(1582.25, 2688.7), clip='lot')],
    # Negozi, lotto 361: il supermercato del lotto 555 con il suo parcheggio, nella parte sud del lotto
    1863: dict(src=(3470, 3880, 3630, 4040), center=(3550, 3958), angle=0.0, size=(112, 100), scale=0.97, at=(708, 172), clip=True),
}
# Lotti senza un luogo, ricoperti di foto vera (lotto -> pezzo come sopra). Villanova, lotti 297-299 (prima campi):
# file di villette prese da altri lotti di Villanova della stessa larghezza.
LOT_TRANSPLANT = {
    # Porta Sud, lotto 937 (ospedale): prato con qualche albero al posto del campo secco, preso dal prato a sud del cimitero.
    937: [dict(src=(1400, 4815, 1615, 4910), center=(1507.5, 4862), size=(160, 44), feather=8.0, at=(x, y),
               flip=(k + r) % 2 == 1, clip=True)
          for r, y in enumerate((4900, 4924, 4948, 4972, 4996, 5012)) for k, x in enumerate((1250, 1355, 1460, 1565, 1665))]
          # e dietro l'ospedale, attorno ai laboratori e all'eliporto, un piazzale sterrato: la terra del campo arato che
          # c'era nel lotto 297 (prima delle villette)
          + [dict(src=(-140, -470, 20, -400), center=(-61.5, -434.5), size=(75, 30), feather=5.0, at=(x, y),
                  flip=(k + r) % 2 == 1, clip=True)
             for r, y in enumerate((4898, 4914, 4930, 4946, 4962, 4978, 4994, 5010)) for k, x in enumerate((1225, 1265))],
    297: dict(src=(-230, -200, 140, -90), center=(-44, -146), size=(336, 42), at=(-43.7, -435.1), clip=True),
    298: dict(src=(120, 110, 270, 200), center=(194, 153), size=(117, 40), scale=(1.0, 1.1), at=(194, -434.1), clip=True),
    299: dict(src=(240, 110, 530, 200), center=(385.5, 153), size=(258, 40), scale=(1.0, 1.13), at=(385.8, -433.5), clip=True),
    # Sant'Elena, lotto 251 (dietro i negozietti): il campo arato in mezzo diventa prato come i due campi ai lati, con
    # pezzi del prato del campo a est (alcuni specchiati, perché non si vedano ripetuti), con un bordo sfumato largo e
    # sovrapposti, così le giunture non si vedono
    251: [dict(src=(2161, 2238, 2241, 2338), center=(2201, 2286), size=(54, 66), feather=8.0, at=(a, b), flip=fl, clip=True)
          for a, b, fl in ((2128, 2283, False), (2151, 2281, True), (2174, 2279, False),
                         (2128, 2315, True), (2151, 2313, False), (2174, 2311, True))],
}


def photo(box, scale):
    """Il riquadro box (metri) delle immagini originali, a `scale` pixel per metro."""
    x0, y0, x1, y1 = box
    out = Image.new('RGB', (int(round((x1 - x0) * PX)), int(round((y1 - y0) * PX))))
    for t, img in tiles:
        ox, oy = round((t['x'] - x0) * PX), round((t['y'] - y0) * PX)
        if ox < out.width and oy < out.height and ox + img.width > 0 and oy + img.height > 0:
            out.paste(Image.open(ORIG + os.path.basename(t['file'])).convert('RGB'), (ox, oy))
    return out.resize((max(1, int(round((x1 - x0) * scale))), max(1, int(round((y1 - y0) * scale)))), Image.LANCZOS)


def transplant(pt, poly, src, center, size, angle=0.0, scale=1.0, feather=3.0, at=None, rot=0.0, clip=False, flip=False,
               lot_poly=None, shadow=None):
    """Un edificio vero preso da `src`: ruotato di `angle` gradi attorno a `center` (così viene dritto), ritagliato a
    `size` metri, ingrandito di `scale` e messo al centro del luogo (o in `at`) con un bordo sfumato, eventualmente
    specchiato destra-sinistra (`flip`), girato di `rot` e ritagliato sul contorno del luogo; intorno resta la foto originale."""
    img = photo(src, S)
    cx, cy = (center[0] - src[0]) * S, (center[1] - src[1]) * S
    img = img.rotate(angle, resample=Image.BICUBIC, center=(cx, cy))
    w, h = size[0] * S, size[1] * S
    img = img.crop((int(cx - w / 2), int(cy - h / 2), int(cx + w / 2), int(cy + h / 2)))
    if flip:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    sx, sy = scale if isinstance(scale, tuple) else (scale, scale)
    img = img.resize((int(img.width * sx), int(img.height * sy)), Image.LANCZOS)
    m = Image.new('L', img.size, 0)
    f = int(feather * S)                                # bordo sfumato
    ImageDraw.Draw(m).rectangle([f, f, img.width - f, img.height - f], fill=255)
    m = m.filter(ImageFilter.GaussianBlur(f / 2))
    img = img.convert('RGBA')
    img.putalpha(m)
    if rot:
        img = img.rotate(rot, resample=Image.BICUBIC, expand=True)
    if at is None:
        xs, ys = [x for x, _ in poly], [y for _, y in poly]
        at = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
    px, py = pt.P(*at)
    if shadow:                                          # ombra verso sud-est come gli edifici vicini (il pezzo è ritagliato
        sh = pt.layer()                                 # sul solo tetto, la sua ombra vera è rimasta nella foto di origine)
        a = np.array(img)[..., 3]
        dark = Image.new('RGBA', img.size, (15, 15, 12, 0))
        dark.putalpha(Image.fromarray((a.astype(np.uint16) * 150 // 255).astype(np.uint8)))
        sh.paste(dark, (int(px - img.width / 2 + shadow[0] * S), int(py - img.height / 2 + shadow[1] * S)), dark)
        pt.img = Image.alpha_composite(pt.img, sh)
    layer = pt.layer()
    layer.paste(img, (int(px - img.width / 2), int(py - img.height / 2)), img)
    if clip:                                            # niente fuori dal lotto: il bordo del lotto sfuma di 1,5 m
        a = np.array(layer)
        m = pt.mask(lot_poly if clip == 'lot' else poly).filter(ImageFilter.GaussianBlur(1.5 * S / 2))
        a[..., 3] = (a[..., 3].astype(np.uint16) * np.array(m) // 255).astype(np.uint8)
        layer = Image.fromarray(a)
    pt.img = Image.alpha_composite(pt.img, layer)


# ------------------------------------------------------------------ edifici nuovi copiati da un edificio vero della foto
LUOGO = {q['id']: q for q in places}


def ombra(pt, poly, floors, rng):
    """L'ombra di un edificio sul terreno, verso sud-est come quelle della foto, sfumata ai bordi."""
    h = min(floors * 3.0 * 0.35, 16)
    m = Image.new('L', (pt.w, pt.h), 0)
    d = ImageDraw.Draw(m)
    for t in np.linspace(0, 1, 9):
        d.polygon([pt.P(x + 0.8 * h * t, y + 0.6 * h * t) for x, y in poly], fill=255)
    m = m.filter(ImageFilter.GaussianBlur(0.5 * S))
    L = Image.new('RGBA', (pt.w, pt.h), (14, 16, 12, 0))
    L.putalpha(m.point(lambda v: v * 118 // 255))
    pt.put(L)


def modello(pt, p, rng):
    """Un edificio nuovo copiato da un edificio vero della foto (tools/perimetri.py sceglie il modello): il tetto con la sua luce e
    i suoi dettagli, girato di pochi gradi e messo in scala, con la sua ombra sul terreno nuovo."""
    m = p['donatore']
    src = main_poly(LUOGO[m['id']]['path'])
    cx, cy = centroid(src)
    xs, ys = [x for x, _ in src], [y for _, y in src]
    pad = 0.2 * max(max(xs) - min(xs), max(ys) - min(ys)) + 4
    box = (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)
    img = photo(box, S).convert('RGBA')
    mask = Image.new('L', img.size, 0)
    ImageDraw.Draw(mask).polygon([((x - box[0]) * S, (y - box[1]) * S) for x, y in src], fill=255)
    mask = mask.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.35 * S))
    img.putalpha(mask)
    ccx, ccy = (cx - box[0]) * S, (cy - box[1]) * S
    if m['rot']:
        img = img.rotate(-m['rot'], resample=Image.BICUBIC, center=(ccx, ccy))
    sc = m['scala']
    if abs(sc - 1) > 1e-3:
        img = img.resize((max(1, int(img.width * sc)), max(1, int(img.height * sc))), Image.LANCZOS)
        ccx, ccy = ccx * sc, ccy * sc
    ombra(pt, main_poly(p['path']), p.get('floors', 1), rng)
    layer = pt.layer()
    px, py = pt.P(*m['centro'])
    layer.paste(img, (int(round(px - ccx)), int(round(py - ccy))), img)
    pt.img = Image.alpha_composite(pt.img, layer)


# ------------------------------------------------------------------ gli insediamenti dei nuovi edifici (tools/siti.py)
# Intorno a ogni edificio nuovo: il parcheggio, l'accesso dalla strada, il marciapiede, il vialetto, l'aia con la siepe. Ogni pezzo è
# un pezzo di foto vera (tools/tessiture.py) girato nel verso dell'insediamento e ritagliato sulla sua forma, con il bordo sfumato.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tessiture as tess

SITI_JSON = os.environ.get('SITI', 'tools/siti.json')
SITI = ([] if os.environ.get('SENZA_NUOVI') or not os.path.exists(SITI_JSON) else json.load(open(SITI_JSON, encoding='utf-8')))
_sorgenti = {}
_moduli = []


def sorgente(box):
    """Il riquadro box (metri) delle immagini originali a S pixel per metro (tenuto in memoria)."""
    k = tuple(round(v, 2) for v in box)
    if k not in _sorgenti:
        _sorgenti[k] = photo(box, S)
    return _sorgenti[k]


def moduli_parcheggio():
    """I pezzi di parcheggio vero che si possono copiare: da una cucitura all'altra (1 o 2 moduli) lungo tutte le file."""
    if not _moduli:
        for nome, x0, x1, y0, y1, asse in tess.PARCHEGGI:
            a = np.array(photo((x0, y0, x1, y1), PX))
            cuc = tess.cuciture(a, asse, y0 if asse == 'x' else x0)
            for n in (1, 2):
                for da, a_ in tess.moduli(cuc, n):
                    _moduli.append({'nome': nome, 'n': n, 'da': da, 'a': a_, 'asse': asse, 'box': (x0, y0, x1, y1)})
    return _moduli


def incolla(pt, poly, src, origine, A, t, sfuma=0.5):
    """Dentro `poly` (mondo) l'immagine `src` (a S pixel per metro, il suo pixel (0, 0) è il punto `origine` delle sue coordinate)
    vista attraverso la trasformazione mondo -> sorgente (xs, ys) = A (x, y) + t; bordo sfumato di `sfuma` metri."""
    (a, b), (c, d) = A
    coeff = (a, b, S * (a * pt.x0 + b * pt.y0 + t[0] - origine[0]), c, d, S * (c * pt.x0 + d * pt.y0 + t[1] - origine[1]))
    img = src.transform((pt.w, pt.h), Image.AFFINE, coeff, resample=Image.BICUBIC).convert('RGBA')
    m = pt.mask(poly)
    if sfuma:
        m = m.filter(ImageFilter.GaussianBlur(sfuma * S / 2))
    img.putalpha(m)
    pt.img = Image.alpha_composite(pt.img, img)


def _locale(o, eu, ev, u0, v0, u1, v1):
    return [tuple(o + u * eu + v * ev) for u, v in ((u0, v0), (u1, v0), (u1, v1), (u0, v1))]


def parcheggio_vero(pt, o, eu, ev, rc, rng):
    """Un parcheggio: un pezzo di parcheggio vero della foto con lo stesso numero di moduli (fila, corsia, fila), le file lungo u."""
    u0, v0, u1, v1 = rc
    W, D = u1 - u0, v1 - v0
    n = max(1, round(D / 16.5))
    adatti = []
    for m in moduli_parcheggio():
        if m['n'] != n:
            continue
        s = D / (m['a'] - m['da'])
        x0, y0, x1, y1 = m['box']
        lungo = (x1 - x0) if m['asse'] == 'x' else (y1 - y0)
        if 0.85 <= s <= 1.18 and lungo - 2 >= W / s:
            adatti.append((m, s, lungo))
    if not adatti:
        return False
    m, s, lungo = adatti[rng.randrange(len(adatti))]
    x0, y0, x1, y1 = m['box']
    off = rng.uniform(1, lungo - 1 - W / s)
    gira = rng.random() < 0.5                           # mezzo giro: la stessa scena vista dall'altra parte
    ou, ov = float(o @ eu) + u0, float(o @ ev) + v0     # (u, v) - (ou, ov) = coordinate dentro il rettangolo
    if m['asse'] == 'x':
        if not gira:      # xs = x0 + off + (u - u0)/s, ys = da + (v - v0)/s
            A, t = (eu / s, ev / s), (x0 + off - ou / s, m['da'] - ov / s)
        else:             # xs = x0 + off + W/s - (u - u0)/s, ys = a - (v - v0)/s
            A, t = (-eu / s, -ev / s), (x0 + off + W / s + ou / s, m['a'] + ov / s)
    else:
        if not gira:      # xs = da + (v - v0)/s, ys = y0 + off + W/s - (u - u0)/s
            A, t = (ev / s, -eu / s), (m['da'] - ov / s, y0 + off + W / s + ou / s)
        else:             # xs = a - (v - v0)/s, ys = y0 + off + (u - u0)/s
            A, t = (-ev / s, eu / s), (m['a'] + ov / s, y0 + off - ou / s)
    box = (x0 - 3, y0 - 3, x1 + 3, y1 + 3)
    incolla(pt, _locale(o, eu, ev, *rc), sorgente(box), box[:2], A, t, sfuma=0.6)
    return True


def materiale(pt, nome, poly_locale, o, eu, ev, rc, rng, sfuma=0.5):
    """Un materiale uniforme (asfalto, pavimento chiaro, ghiaia): una finestra vera della foto ripetuta a specchio fino a coprire il
    rettangolo rc, in un verso a caso."""
    u0, v0, u1, v1 = rc
    cx, cy, hh = tess.MATERIALI[nome][rng.randrange(len(tess.MATERIALI[nome]))]
    base = sorgente((cx - hh, cy - hh, cx + hh, cy + hh))
    lato = max(u1 - u0, v1 - v0) + 2 * hh + 4
    nt = int(math.ceil(lato / (2 * hh)))
    tess_img = Image.new('RGB', (base.width * nt, base.height * nt))
    for i in range(nt):
        for j in range(nt):
            q = base.transpose(Image.FLIP_LEFT_RIGHT) if i % 2 else base
            q = q.transpose(Image.FLIP_TOP_BOTTOM) if j % 2 else q
            tess_img.paste(q, (i * base.width, j * base.height))
    off_u, off_v = rng.uniform(0, 2 * hh), rng.uniform(0, 2 * hh)
    ou, ov = float(o @ eu) + u0, float(o @ ev) + v0
    if rng.random() < 0.5:
        A, t = (eu, ev), (off_u - ou, off_v - ov)
    else:
        A, t = (ev, eu), (off_u - ov, off_v - ou)
    incolla(pt, poly_locale, tess_img, (0.0, 0.0), A, t, sfuma=sfuma)


def siepe(pt, a, b, n, rng, dentro=4.0, fuori=2.0):
    """Il bordo di un'aia: una fila vera di arbusti della foto (con le loro ombre) lungo il lato a-b, n verso l'interno; la striscia
    va da `fuori` metri fuori a `dentro` metri dentro l'aia (ghiaia, arbusti, prato)."""
    xc, y0, y1 = tess.SIEPI[rng.randrange(len(tess.SIEPI))]
    L = math.dist(a, b)
    lungo = y1 - y0
    if L > lungo - 2:
        m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        siepe(pt, a, m, n, rng, dentro, fuori)
        siepe(pt, m, b, n, rng, dentro, fuori)
        return
    es = np.array([(b[0] - a[0]) / L, (b[1] - a[1]) / L])
    en = np.array(n)
    A0 = np.array(a)
    poly = [tuple(A0 - fuori * en), tuple(A0 + L * es - fuori * en), tuple(A0 + L * es + dentro * en), tuple(A0 + dentro * en)]
    off = rng.uniform(1, lungo - 1 - L)
    sa, ta = float(A0 @ es), float(A0 @ en)
    # xs = xc - t (t: metri verso l'interno dell'aia dalla fila), ys = y0 + off + s (s lungo il lato)
    A, t = (-en, es), (xc + ta, y0 + off - sa)
    box = (xc - 8, y0 - 2, xc + 8, y1 + 2)
    incolla(pt, poly, sorgente(box), box[:2], A, t, sfuma=1.0)


def campo_vero(pt, o, eu, ev, rc, rng):
    """Un campetto da basket vero della foto, girato e messo in scala sul rettangolo rc (con il suo bordo)."""
    cx, cy = tess.CAMPI[rng.randrange(len(tess.CAMPI))]
    box = (cx - 26, cy - 26, cx + 26, cy + 26)
    cd, ad, Ld, _ = tess.campo(np.array(photo(box, PX)), box[0], box[1])
    u0, v0, u1, v1 = rc
    at = eu if (u1 - u0) >= (v1 - v0) else ev
    Lt = max(u1 - u0, v1 - v0)
    ct = o + (u0 + u1) / 2 * eu + (v0 + v1) / 2 * ev
    R90 = lambda a: np.array([-a[1], a[0]])
    s = Lt / Ld
    if rng.random() < 0.5:
        ad = -ad
    M = (np.outer(ad, at) + np.outer(R90(ad), R90(at))) / s     # mondo (attorno a ct) -> campo vero (attorno a cd)
    A, t = (M[0], M[1]), tuple(cd - M @ ct)
    g = 1.5
    poly = _locale(o, eu, ev, u0 - g, v0 - g, u1 + g, v1 + g)
    incolla(pt, poly, sorgente(box), box[:2], A, t, sfuma=0.9)


ORDINE_SITO = ['giardino', 'aia', 'piazzale', 'strada', 'campo', 'parcheggio', 'accesso', 'marciapiede', 'piazzetta', 'vialetto']
MATERIALE_DI = {'piazzale': 'asfalto', 'strada': 'asfalto', 'accesso': 'asfalto', 'marciapiede': 'chiaro', 'piazzetta': 'chiaro',
                'vialetto': 'chiaro', 'aia': 'ghiaia', 'giardino': 'prato'}


def disegna_sito(pt, s, rng):
    o, eu, ev = np.array(s['o']), np.array(s['u']), np.array(s['v'])
    for el in sorted(s['elementi'], key=lambda e: ORDINE_SITO.index(e['tipo'])):
        rc = el['rect']
        if el['tipo'] == 'parcheggio' and parcheggio_vero(pt, o, eu, ev, rc, rng):
            continue
        if el['tipo'] == 'campo':
            campo_vero(pt, o, eu, ev, rc, rng)
            continue
        nome = MATERIALE_DI.get(el['tipo'], 'asfalto')
        materiale(pt, nome, _locale(o, eu, ev, *rc), o, eu, ev, rc, rng,
                  sfuma={'ghiaia': 0.7, 'prato': 1.6}.get(nome, 0.45))
        if el['tipo'] == 'giardino':                    # arbusti lungo il confine del giardino, ai lati e dietro
            u0, v0, u1, v1 = rc
            P = lambda u, v: tuple(o + u * eu + v * ev)
            for a, b, n in ((P(u0, v1), P(u0, v0 + 4), eu), (P(u1, v0 + 4), P(u1, v1), -eu), (P(u1, v1), P(u0, v1), -ev)):
                if rng.random() < 0.8:
                    siepe(pt, a, b, tuple(n), rng, dentro=2.5, fuori=0.8)
        if el['tipo'] == 'aia':                         # la siepe sui tre lati senza ingresso
            u0, v0, u1, v1 = rc
            P = lambda u, v: tuple(o + u * eu + v * ev)
            for a, b, n in ((P(u0, v1), P(u0, v0), eu), (P(u1, v0), P(u1, v1), -eu), (P(u1, v1), P(u0, v1), -ev)):
                if rng.random() < 0.85:
                    siepe(pt, a, b, tuple(n), rng)


# ------------------------------------------------------------------ capannoni divisi tra le aziende (tools/perimetri.py, divisioni.json)
# Un capannone con più aziende diventa più corpi: tra un corpo e l'altro una corsia di cemento (il cemento del piazzale vero), con
# l'ombra del corpo a nord-ovest e il bordo chiaro dei tetti tagliati, come i capannoni separati della foto.
DIVISIONI_JSON = os.environ.get('DIVISIONI', 'tools/divisioni.json')
DIVISIONI = ([] if os.environ.get('SENZA_NUOVI') or not os.path.exists(DIVISIONI_JSON)
             else json.load(open(DIVISIONI_JSON, encoding='utf-8')))


def riempi(pt, poly, nome, rng):
    """Un poligono qualsiasi pieno di un materiale di tessiture.MATERIALI, nel verso del suo rettangolo orientato."""
    from shapely.geometry import Polygon as _P
    r = list(_P(poly).minimum_rotated_rectangle.exterior.coords)
    o = np.array(r[0])
    eu, ev = np.array(r[1]) - o, np.array(r[3]) - o
    L1, L2 = np.linalg.norm(eu), np.linalg.norm(ev)
    eu, ev = eu / L1, ev / L2
    materiale(pt, nome, poly, o, eu, ev, (0.0, 0.0, L1, L2), rng, sfuma=0.3)


def dividi_capannone(pt, d, rng):
    corsie = [main_poly(c) for c in d['corsie']]
    corpi = [main_poly(c) for c in d['corpi']]
    for c in corsie:
        riempi(pt, c, 'cemento', rng)
    m_corsie = Image.new('L', (pt.w, pt.h), 0)
    for c in corsie:
        ImageDraw.Draw(m_corsie).polygon([pt.P(*q) for q in c], fill=255)
    # l'ombra di ogni corpo cade nelle corsie come quella vera dei capannoni nella foto: 6 m verso est, 3 m verso sud, scura
    L = Image.new('RGBA', (pt.w, pt.h), (14, 16, 12, 0))
    m = Image.new('L', (pt.w, pt.h), 0)
    for g in corpi:
        for t in np.linspace(0, 1, 7):                  # il corpo trascinato lungo la direzione dell'ombra
            ImageDraw.Draw(m).polygon([pt.P(x + 6.0 * t, y + 3.0 * t) for x, y in g], fill=255)
    m = m.filter(ImageFilter.GaussianBlur(0.3 * S))
    a = (np.array(m).astype(np.uint16) * np.array(m_corsie) // 255 * 200 // 255).astype(np.uint8)
    L.putalpha(Image.fromarray(a))
    pt.img = Image.alpha_composite(pt.img, L)
    # il bordo chiaro dei tetti lungo le corsie (il parapetto)
    L = pt.layer()
    dr = ImageDraw.Draw(L)
    for g in corpi:
        dr.line([pt.P(*q) for q in g + [g[0]]], fill=(226, 226, 220, 170), width=max(1, int(0.7 * S)))
    vicino = m_corsie.filter(ImageFilter.MaxFilter(int(2.0 * S) | 1))
    a = np.array(L)
    a[..., 3] = (a[..., 3].astype(np.uint16) * np.array(vicino) // 255).astype(np.uint8)
    pt.img = Image.alpha_composite(pt.img, Image.fromarray(a))


# ------------------------------------------------------------------ cosa disegnare
ROOF = {'uff': (152, 162, 174), 'com': (196, 150, 112), 'ind': (186, 108, 78), 'art': (176, 120, 90), 'pub': (204, 196, 182), 'agr': (140, 72, 52), 'res': (176, 150, 120)}
ONLY = {int(a) for a in sys.argv[1:]}
# luoghi che la foto di base non ha: scuole di La Cerchia, istituto tecnico, ospedale di Porta Sud, bar del lotto 66,
# negozi dei lotti 251, 304, 361 e 469 (l'ospedale di Porta Sud è diviso in corpo, ali, padiglioni, laboratori, eliporto e parcheggi)
DISEGNATI = {1887, 1888, 1843, 1871, 1921, 1922, 1878, 1879, 1919, 1832, 1833, 1834, 1835, 1836, 1866, 1837, 1838, 1839, 1852, 1861, 1863, 1870, 1873, 1900, 1901, 1904, 1910, 1911, 1912, 1913, 1914, 1915, 1916, 1917, 1918}
# I luoghi di La Cerchia disegnati qui sopra (scuole, uffici comunali, bar) non sono più in places.json (La Cerchia ha
# i suoi edifici censiti, tools/cerchia.py), ma la foto resta quella: i loro contorni stanno in tools/cerchia_luoghi_foto.json.
LUOGHI_FOTO = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cerchia_luoghi_foto.json'), encoding='utf-8'))
features = []
for p in places + [q for q in LUOGHI_FOTO if q['id'] not in {x['id'] for x in places}] + CONTORNI_NUOVI:
    if p['id'] not in DISEGNATI and p.get('kind') != 'footprint':
        continue
    if ONLY and p['id'] not in ONLY:
        continue
    poly = main_poly(p['path'])
    lot = lots.get(p['lot'])
    whole = lot is not None and abs(area(poly)) >= 0.8 * abs(area(main_poly(lot['path'])))
    n = p['name']
    if p.get('donatore'):
        kind = 'modello'
    elif p['id'] in TRANSPLANT:
        kind = 'transplant'
    elif n.startswith('Campi e impianto fotovoltaico'):
        kind = 'solar'
    elif n.startswith('Campi'):
        kind = 'field'
    elif n.startswith(('Parco', 'Giardino', 'Orti')):
        kind = 'park'
    elif n.startswith('Parcheggio'):
        kind = 'parking'
    elif n == 'Stazione autobus Ovest':
        kind = 'busstation'
    elif n.startswith('Polo logistico'):
        kind = 'warehouses'
    elif whole and p['category'] == 'agr':
        kind = 'farmyard'
    elif whole:
        kind = 'campus'
    else:
        kind = 'roof'
    features.append((kind, p['id'], poly, p))
for s_ in SITI:                                         # gli insediamenti dei nuovi edifici, sotto i loro tetti
    if ONLY and -200000 - s_['id'] not in ONLY:
        continue
    o_, eu_, ev_ = np.array(s_['o']), np.array(s_['u']), np.array(s_['v'])
    pts_ = [tuple(o_ + u * eu_ + v * ev_) for el in s_['elementi'] for u in el['rect'][0::2] for v in el['rect'][1::2]]
    features.append(('sito', -200000 - s_['id'], pts_, s_))
for d_ in DIVISIONI:                                    # capannoni divisi: sopra il capannone, dopo tutto il resto
    if ONLY and -300000 - d_['luogo'] not in ONLY:
        continue
    features.append(('divisione', -300000 - d_['luogo'], [q for c in d_['corsie'] for q in main_poly(c)], d_))
for n, tp in LOT_TRANSPLANT.items():
    if not ONLY or -n in ONLY:                          # da riga di comando un lotto si indica col meno: -297
        features.append(('transplant', -n, main_poly(lots[n]['path']), {'id': -n, 'name': f'lotto {n}', 'tp': tp}))

# Il Centro (tools/centro.py), disegnato da zero da tools/disegna_centro.py: ogni lotto con edifici, tolta la sua metà
# delle strade, ha il suo terreno (lastricato, marciapiedi, giardini, alberi) e i suoi edifici, con facciate, tetti e
# ombre. Prima, sulle strade del Centro si schiariscono le ombre dei vecchi grattacieli della foto di base. La Cerchia
# resta la foto: i suoi edifici censiti (tools/cerchia.py) sono gli edifici della foto.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import centro as centro_mod
from centro import suolo as centro_suolo, poligono as centro_poligono
from disegna_centro import disegna_suolo, disegna_ombre, disegna_edifici

RIFATTI = [('Centro', centro_mod.edifici(), centro_mod.RESTANO)]     # La Cerchia resta la foto (tools/cerchia.py)
QUARTIERI = {q['name']: q for q in json.load(open('public/data/quarters.json', encoding='utf-8'))}
centro_places = {p['id']: p for p in places if p['id'] in centro_mod.RESTANO}
RIFATTI_LOTTI = {}
# tre passate: il terreno di tutti i lotti, le ombre di tutto il quartiere (cadono anche sulle strade e sui lotti vicini),
# gli edifici di ogni lotto; gli edifici che restano come sono (il Duomo) non si disegnano
for k, (nome, es_q, _) in enumerate(RIFATTI):
    per_lotto = {}
    for e in es_q:
        if e['forma'] != 'esistente':
            per_lotto.setdefault(e['lotto'], []).append(e)
    RIFATTI_LOTTI[nome] = per_lotto
    if ONLY and not any(-n in ONLY for n in per_lotto):
        continue
    area_q = centro_poligono(QUARTIERI[nome]['path'])
    for n, es in per_lotto.items():
        suolo_xy = list(centro_suolo(n).exterior.coords)[:-1]
        features.append(('centro', -n, suolo_xy, {'id': -n, 'lot': n, 'edifici': es}))
        features.append(('centro_edifici', -n, suolo_xy, {'id': -n, 'lot': n, 'edifici': es}))
    features.append(('centro_ombre', -9999 + k, list(area_q.exterior.coords)[:-1],
                     {'id': -9999 + k, 'edifici': [e for es in per_lotto.values() for e in es], 'area': area_q}))

# l'ordine conta: prima il terreno (campi, parchi), poi gli edifici sopra
ORDER = ['centro', 'centro_ombre', 'centro_edifici', 'transplant', 'solar', 'field', 'park', 'houses', 'farmyard', 'campus', 'busstation', 'warehouses', 'parking', 'roof', 'sito', 'modello', 'divisione']
features.sort(key=lambda f: (ORDER.index(f[0]), -abs(area(f[2]))))

# Le strade dei quartieri rifatti (il quartiere meno il suolo dei suoi lotti) erano in ombra sotto i vecchi edifici: i
# pixel scuri dell'asfalto si riportano al colore dell'asfalto al sole (guadagno per canale misurato sulla foto di base).
OMBRA_STRADE = (2.6, 2.4, 2.1)
from shapely.ops import unary_union
for nome, _, _ in RIFATTI:
    if ONLY and not any(-n in ONLY for n in RIFATTI_LOTTI[nome]):
        continue
    q_lots = [l['number'] for l in lots.values() if l['quarter'] == nome]
    strade = centro_poligono(QUARTIERI[nome]['path']).difference(unary_union([centro_suolo(n) for n in q_lots]))
    bx0, by0, bx1, by1 = strade.bounds
    for t, img in tiles:
        if t['x'] > bx1 or t['y'] > by1 or t['x'] + t['size'] < bx0 or t['y'] + t['size'] < by0:
            continue
        m = Image.new('L', img.size, 0)
        dm = ImageDraw.Draw(m)
        for g in getattr(strade, 'geoms', [strade]):
            dm.polygon([((x - t['x']) * PX, (y - t['y']) * PX) for x, y in g.exterior.coords], fill=255)
            for h in g.interiors:
                dm.polygon([((x - t['x']) * PX, (y - t['y']) * PX) for x, y in h.coords], fill=0)
        M = np.array(m.filter(ImageFilter.GaussianBlur(1))).astype(np.float32) / 255
        if not M.any():
            continue
        a = np.array(img).astype(np.float32)
        lum = np.array(Image.fromarray(a.mean(2).astype(np.uint8)).filter(ImageFilter.GaussianBlur(2))).astype(np.float32)
        w = np.clip((68 - lum) / 20, 0, 1) * M
        w = np.array(Image.fromarray((w * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.5))).astype(np.float32) / 255
        a = a * (1 + w[..., None] * (np.array(OMBRA_STRADE) - 1))
        img.paste(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)))
        touched.add(t['file'])

counts = {}
built_houses = {}
for kind, fid, poly, p in features:
    rng = random.Random(fid)
    pt = Patch(poly)
    if kind == 'centro':
        holes = [centro_poligono(q['path']) for q in centro_places.values() if q['lot'] == p['lot'] and q['id'] != 9]
        disegna_suolo(pt, centro_suolo(p['lot']), p['edifici'], holes, rng)
    elif kind == 'centro_ombre':
        pt = Patch(poly, margin=5)
        disegna_ombre(pt, p['edifici'], p['area'], rng)
    elif kind == 'centro_edifici':
        pt = Patch(poly, margin=24)                    # i tetti alti si vedono spostati a nord, fuori dal lotto
        disegna_edifici(pt, p['edifici'], rng)
    elif kind == 'transplant':                            # uno o più pezzi; la toppa deve contenerli tutti
        pieces = p.get('tp') or TRANSPLANT[p['id']]
        pieces = pieces if isinstance(pieces, list) else [pieces]
        ats = [q['at'] for q in pieces if q.get('at')]
        pt = Patch(poly + [(a[0] + d, a[1] + d) for a in ats for d in (-80, 80)])
        lp = main_poly(lots[p['lot']]['path']) if p.get('lot') in lots else poly
        for q in pieces:
            transplant(pt, poly, lot_poly=lp, **q)
    elif kind == 'modello':
        modello(pt, p, rng)
    elif kind == 'sito':
        pt = Patch(poly, margin=6)
        disegna_sito(pt, p, rng)
    elif kind == 'divisione':
        pt = Patch(poly, margin=8)
        dividi_capannone(pt, p, rng)
    elif kind == 'field':
        stripes(pt, poly, main_axis(poly), 9.0, 9.0, (150, 134, 92), (118, 132, 78), rng)
    elif kind == 'solar':
        stripes(pt, poly, main_axis(poly), 9.0, 9.0, (150, 134, 92), (118, 132, 78), rng)
        panels = scale(poly, 0.55)
        ground(pt, panels, (150, 145, 125), rng)
        stripes(pt, panels, main_axis(poly), 6.5, 4.0, (42, 56, 86), None, rng)
    elif kind == 'park':
        ground(pt, poly, GRASS, rng)
        if abs(area(poly)) > 3000:
            path_cross(pt, poly, rng)
        trees(pt, poly, 0.004 if abs(area(poly)) > 3000 else 0.006, rng)
    elif kind == 'houses':
        built_houses[p['lot']] = houses(pt, poly, p['n'], rng)
    elif kind == 'farmyard':
        ground(pt, poly, (152, 136, 104), rng)
        roof(pt, scale(poly, 0.55), ROOF['agr'], 2, rng, ribs=True, hvac=False)
    elif kind == 'campus':
        school = p['name'].startswith(('Scuola', 'Istituto'))
        campus(pt, poly, (172, 82, 72) if school else ROOF[p['category']], p.get('floors', 3), rng, sports=school)
    elif kind == 'busstation':
        ground(pt, poly, (96, 96, 96), rng)
        stripes(pt, scale(poly, 0.8), main_axis(poly), 14.0, 4.0, (232, 232, 226), None, rng)       # pensiline
    elif kind == 'warehouses':
        warehouses(pt, poly, rng)
    elif kind == 'parking':
        parking(pt, poly, rng)
    else:
        rgb = ((226, 226, 220) if p['name'].startswith(('Ospedale', 'Stazione autobus'))
               else (200, 92, 80) if p['name'] == 'Pronto soccorso'
               else (172, 82, 72) if p['name'].startswith(('Scuola', 'Asilo', 'Liceo')) else ROOF[p['category']])
        roof(pt, poly, rgb, p.get('floors', 3), rng, ribs=p['category'] in ('ind', 'art') or p['name'].startswith(('Mercato', 'Padiglione')),
             helipad=p['name'] == 'Ospedale di Porta Sud')
    counts[kind] = counts.get(kind, 0) + 1

    # dalla toppa alla risoluzione delle immagini, con un po' di grana fotografica
    small = pt.img.resize((max(1, int(pt.w / SS)), max(1, int(pt.h / SS))), Image.LANCZOS)
    a = np.array(small).astype(np.float32)
    grain = np.random.default_rng(abs(fid)).normal(0, 5.5, a.shape[:2])[..., None]
    if kind not in ('transplant', 'modello', 'sito', 'divisione'):   # una foto vera ha già la sua grana
        a[..., :3] = np.clip(a[..., :3] + grain * (a[..., 3:4] > 0), 0, 255)
    small = Image.fromarray(a.astype(np.uint8))
    if kind not in ('transplant', 'modello', 'sito', 'divisione'):
        small = small.filter(ImageFilter.GaussianBlur(0.35))
    for t, img in tiles:
        ox = round((pt.x0 - t['x']) * PX)
        oy = round((pt.y0 - t['y']) * PX)
        if ox >= img.width or oy >= img.height or ox + small.width <= 0 or oy + small.height <= 0:
            continue
        img.paste(small, (ox, oy), small)
        touched.add(t['file'])

os.makedirs(USCITA + 'tiles', exist_ok=True)
for t, img in tiles:
    if t['file'] in touched:
        img.save(USCITA + t['file'], 'JPEG', quality=88, optimize=True, progressive=True)
    else:
        shutil.copy2(ORIG + os.path.basename(t['file']), USCITA + t['file'])
print('disegnati:', counts, '· immagini modificate:', len(touched), 'su', len(tiles))
print('villette disegnate per lotto:', built_houses)
