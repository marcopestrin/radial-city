# Disegna nelle immagini satellitari (public/tiles/*.jpg) gli edifici che la foto di base non ha
# (elenco DISEGNATI qui sotto).
#
# Parte SEMPRE dalle immagini di base in backup/tiles_originali/ (le copia lì la prima volta), così si può
# rilanciare senza disegnare due volte. Le immagini senza disegni restano identiche a quelle di base. Servono numpy e Pillow.
#   python3 tools/disegna_satellite.py            (tutto)
#   python3 tools/disegna_satellite.py 1834 ...   (solo i luoghi con questi id; le altre immagini tornano originali)
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
TRANSPLANT = {
    # Scuola media, lotto 65: l'edificio a L del Tecnopolo (lotto 161), raddrizzato e un po' ingrandito, sul prato
    # originale del lotto (niente campo da calcio).
    1834: dict(src=(1780, -450, 1975, -305), center=(1878, -378), angle=-18.0, size=(100, 66), scale=1.12),
    # Bar, lotto 66 (dove c'era la stazione autobus Ovest): il bar del lotto 85, sul lastricato
    1839: dict(src=(1735, 1280, 1790, 1330), center=(1761, 1303), angle=0.0, size=(22, 19), scale=0.7, feather=1.5),
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


def transplant(pt, poly, src, center, angle, size, scale, feather=3.0):
    """Un edificio vero preso da `src`: ruotato di `angle` gradi attorno a `center` (così viene dritto), ritagliato a
    `size` metri, ingrandito di `scale` e messo al centro del luogo con un bordo sfumato; intorno resta la foto originale."""
    img = photo(src, S)
    cx, cy = (center[0] - src[0]) * S, (center[1] - src[1]) * S
    img = img.rotate(angle, resample=Image.BICUBIC, center=(cx, cy))
    w, h = size[0] * S, size[1] * S
    img = img.crop((int(cx - w / 2), int(cy - h / 2), int(cx + w / 2), int(cy + h / 2)))
    img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
    m = Image.new('L', img.size, 0)
    f = int(feather * S)                                # bordo sfumato
    ImageDraw.Draw(m).rectangle([f, f, img.width - f, img.height - f], fill=255)
    m = m.filter(ImageFilter.GaussianBlur(f / 2))
    img = img.convert('RGBA')
    img.putalpha(m)
    xs, ys = [x for x, _ in poly], [y for _, y in poly]
    px, py = pt.P((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
    layer = pt.layer()
    layer.paste(img, (int(px - img.width / 2), int(py - img.height / 2)), img)
    pt.img = Image.alpha_composite(pt.img, layer)


# ------------------------------------------------------------------ cosa disegnare
ROOF = {'uff': (152, 162, 174), 'com': (196, 150, 112), 'ind': (186, 108, 78), 'art': (176, 120, 90), 'pub': (204, 196, 182), 'agr': (140, 72, 52), 'res': (176, 150, 120)}
ONLY = {int(a) for a in sys.argv[1:]}
# luoghi che la foto di base non ha: scuole di La Cerchia, istituto tecnico, ospedale di Porta Sud, bar del lotto 66
DISEGNATI = {1832, 1833, 1834, 1835, 1836, 1837, 1838, 1839, 1896}
features = []
for p in places:
    if p['id'] not in DISEGNATI:
        continue
    if ONLY and p['id'] not in ONLY:
        continue
    poly = main_poly(p['path'])
    lot = lots.get(p['lot'])
    whole = lot is not None and abs(area(poly)) >= 0.8 * abs(area(main_poly(lot['path'])))
    n = p['name']
    if p['id'] in TRANSPLANT:
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

# l'ordine conta: prima il terreno (campi, parchi), poi gli edifici sopra
ORDER = ['transplant', 'solar', 'field', 'park', 'houses', 'farmyard', 'campus', 'busstation', 'warehouses', 'parking', 'roof']
features.sort(key=lambda f: (ORDER.index(f[0]), -abs(area(f[2]))))

counts = {}
built_houses = {}
for kind, fid, poly, p in features:
    rng = random.Random(fid)
    pt = Patch(poly)
    if kind == 'transplant':
        transplant(pt, poly, **TRANSPLANT[p['id']])
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
               else (200, 92, 80) if p['name'] == 'Pronto soccorso' else ROOF[p['category']])
        roof(pt, poly, rgb, p.get('floors', 3), rng, ribs=p['category'] in ('ind', 'art') or p['name'].startswith(('Mercato', 'Padiglione')),
             helipad=p['name'] == 'Ospedale di Porta Sud')
    counts[kind] = counts.get(kind, 0) + 1

    # dalla toppa alla risoluzione delle immagini, con un po' di grana fotografica
    small = pt.img.resize((max(1, int(pt.w / SS)), max(1, int(pt.h / SS))), Image.LANCZOS)
    a = np.array(small).astype(np.float32)
    grain = np.random.default_rng(fid).normal(0, 5.5, a.shape[:2])[..., None]
    if kind != 'transplant':                            # una foto vera ha già la sua grana
        a[..., :3] = np.clip(a[..., :3] + grain * (a[..., 3:4] > 0), 0, 255)
    small = Image.fromarray(a.astype(np.uint8))
    if kind != 'transplant':
        small = small.filter(ImageFilter.GaussianBlur(0.35))
    for t, img in tiles:
        ox = round((pt.x0 - t['x']) * PX)
        oy = round((pt.y0 - t['y']) * PX)
        if ox >= img.width or oy >= img.height or ox + small.width <= 0 or oy + small.height <= 0:
            continue
        img.paste(small, (ox, oy), small)
        touched.add(t['file'])

for t, img in tiles:
    if t['file'] in touched:
        img.save('public/' + t['file'], 'JPEG', quality=88, optimize=True, progressive=True)
    else:
        shutil.copy2(ORIG + os.path.basename(t['file']), 'public/' + t['file'])
print('disegnati:', counts, '· immagini modificate:', len(touched), 'su', len(tiles))
print('villette disegnate per lotto:', built_houses)
