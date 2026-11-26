# Disegna il Centro nel satellite, inventato da zero (nessun pezzo della foto), con l'aspetto delle viste aeree dei
# centri delle grandi città: tetti piani chiari o scuri pieni di impianti (macchine, torri di raffreddamento, condotti,
# vani scala), facciate a griglia fitta di finestre in pietra o vetro scuro, colori neutri, ombre lunghe e scure, poco verde.
# Gli edifici (tools/centro.py) si vedono un po' da sud come nella foto di base: il tetto spostato verso nord di 0,27 m
# per metro di altezza e le facciate rivolte a sud; l'ombra cade verso sud-sud-ovest.
# Usato da tools/disegna_satellite.py in tre passate: il terreno di ogni lotto, le ombre di tutto il Centro (anche sulle
# strade), gli edifici di ogni lotto.
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from shapely.geometry import LineString, Point, Polygon, box
from shapely import affinity
from shapely.ops import unary_union

from centro import ALTEZZA_PIANO, PROSPETTIVA

OMBRA = (-0.42, 0.91)             # direzione dell'ombra (verso sud-sud-ovest), come quella degli edifici della foto
OMBRA_PER_METRO = 0.6             # lunghezza dell'ombra per metro di altezza
SOLE = (0.9, -0.42)               # da dove viene la luce, per schiarire o scurire le facciate
VANO_SCALA = 4.0                  # altezza del vano scala e ascensore che sporge dal tetto (m)

CEMENTO = (170, 168, 162)
MARCIAPIEDE = (184, 182, 176)
CORDOLO = (204, 202, 196)
PRATO = (100, 114, 74)
CHIOMA = (48, 66, 40)
FACCIATE = {                      # colore, passo delle finestre (m), vetro
    'intonaco_caldo': ((196, 184, 164), 2.6, False),     # pietra beige
    'intonaco_chiaro': ((214, 212, 206), 2.4, False),    # cemento chiaro
    'mattone': ((150, 116, 96), 2.4, False),             # mattone spento
    'pietra': ((204, 198, 186), 2.8, False),             # pietra calcarea
    'vetro_blu': ((52, 64, 80), 1.6, True),
    'vetro_verde': ((58, 72, 72), 1.6, True),
    'vetro_grigio': ((76, 82, 90), 1.6, True),
}
TETTI = {
    'chiaro': (226, 226, 222), 'ghiaia': (188, 186, 180), 'scuro': (118, 118, 116), 'solare': (206, 206, 202),
    'verde': (96, 112, 70), 'piscina': (214, 210, 202), 'eliporto': (150, 152, 154), 'osservatorio': (200, 200, 196),
    'terrazza': (198, 194, 186), 'lucernari': (200, 198, 192),
}


# ------------------------------------------------------------------ strumenti
def _polys(g):
    if g is None or g.is_empty:
        return []
    return [p for p in getattr(g, 'geoms', [g]) if p.geom_type == 'Polygon' and p.area > 0.05]


def _rings(g):
    return [r for p in _polys(g) for r in [p.exterior] + list(p.interiors)]


class Tela:
    """Disegno su una toppa (pt): maschere con i buchi, colori con una tessitura, linee e cerchi in metri."""

    def __init__(self, pt, rng):
        self.pt, self.rng = pt, rng
        self.nrng = np.random.default_rng(rng.randrange(1 << 30))
        self.S = pt.P(1, 0)[0] - pt.P(0, 0)[0]          # pixel per metro della toppa

    def P(self, x, y):
        return self.pt.P(x, y)

    def mask(self, g, blur=0.0):
        m = Image.new('L', (self.pt.w, self.pt.h), 0)
        d = ImageDraw.Draw(m)
        for p in _polys(g):
            d.polygon([self.P(*c) for c in p.exterior.coords], fill=255)
            for h in p.interiors:
                d.polygon([self.P(*c) for c in h.coords], fill=0)
        if blur:
            m = m.filter(ImageFilter.GaussianBlur(blur * self.S / 2))
        return m

    def rumore(self, cella, amp):
        """Variazione lenta di luminosità (macchie larghe `cella` metri) più la grana fine."""
        w, h = self.pt.w, self.pt.h
        c = max(2, int(cella * self.S))
        small = self.nrng.normal(0, 1, (h // c + 3, w // c + 3)).astype(np.float32)
        big = np.array(Image.fromarray(small, 'F').resize((small.shape[1] * c, small.shape[0] * c), Image.BICUBIC))[:h, :w]
        return big * amp + self.nrng.normal(0, amp * 0.3, (h, w)).astype(np.float32)

    def colora(self, g, rgb, alpha=255, cella=6.0, amp=6.0, blur=0.0, macchie=0.0):
        """Riempie g di rgb con una tessitura; `macchie` aggiunge chiazze più scure (sporco, umidità)."""
        if not _polys(g):
            return
        a = np.empty((self.pt.h, self.pt.w, 4), np.float32)
        n = self.rumore(cella, amp) if amp else 0
        if macchie:
            n = n - np.clip(self.rumore(cella * 2.5, macchie), 0, None)
        for i in range(3):
            a[..., i] = rgb[i] + n
        a[..., 3] = np.array(self.mask(g, blur), np.float32) * (alpha / 255)
        self.pt.put(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)))

    def strato(self):
        L = self.pt.layer()
        return L, ImageDraw.Draw(L)

    def linea(self, d, pts, rgb, larghezza, alpha=255):
        d.line([self.P(*q) for q in pts], fill=tuple(rgb) + (alpha,), width=max(1, int(round(larghezza * self.S))))

    def cerchio(self, d, c, r, rgb, alpha=255, outline=None, ow=0.0):
        x, y = c
        d.ellipse([self.P(x - r, y - r), self.P(x + r, y + r)], fill=None if rgb is None else tuple(rgb) + (alpha,),
                  outline=None if outline is None else tuple(outline) + (alpha,), width=max(1, int(ow * self.S)) if ow else 0)

    def poligono(self, d, g, rgb, alpha=255):
        for p in _polys(g):
            d.polygon([self.P(*c) for c in p.exterior.coords], fill=tuple(rgb) + (alpha,))

    def quad(self, d, pts, rgb, alpha=255):
        d.polygon([self.P(*q) for q in pts], fill=tuple(rgb) + (alpha,))

    def metti(self, L, clip=None, blur=0.0):
        if clip is not None:
            a = np.array(L)
            a[..., 3] = (a[..., 3].astype(np.uint16) * np.array(self.mask(clip, blur)) // 255).astype(np.uint8)
            L = Image.fromarray(a)
        self.pt.put(L)


def _shade(rgb, f):
    return tuple(int(max(0, min(255, c * f))) for c in rgb)


def _assi(ang):
    return (math.cos(ang), math.sin(ang)), (-math.sin(ang), math.cos(ang))


def _sposta(g, z):
    """Dove si vede, nella foto, una cosa che sta a z metri d'altezza."""
    return affinity.translate(g, 0, -z * PROSPETTIVA)


def _strisce(area, ang, passo, larghezza, offset=0.0):
    """Strisce parallele all'asse `ang`, ritagliate sull'area."""
    if area.is_empty:
        return []
    (ux, uy), (vx, vy) = _assi(ang)
    c = area.centroid
    x0, y0, x1, y1 = area.bounds
    R = math.hypot(x1 - x0, y1 - y0) / 2 + 5
    out = []
    k = -R + offset
    while k < R:
        a = (c.x + vx * k - ux * R, c.y + vy * k - uy * R)
        b = (c.x + vx * k + ux * R, c.y + vy * k + uy * R)
        s = Polygon([a, b, (b[0] + vx * larghezza, b[1] + vy * larghezza), (a[0] + vx * larghezza, a[1] + vy * larghezza)])
        g = s.intersection(area)
        if not g.is_empty:
            out.append(g)
        k += passo
    return out


def _rett(c, w, h, ang):
    r = box(-w / 2, -h / 2, w / 2, h / 2)
    return affinity.translate(affinity.rotate(r, ang, origin=(0, 0), use_radians=True), *c)


def _punti_dentro(area, n, rng, distanza=0.0):
    if area.is_empty or n <= 0:
        return []
    if not area.is_valid:
        area = area.buffer(0)
    x0, y0, x1, y1 = area.bounds
    out, tries = [], 0
    while len(out) < n and tries < n * 30:
        tries += 1
        p = (rng.uniform(x0, x1), rng.uniform(y0, y1))
        if not area.contains(Point(p)):
            continue
        if distanza and any(math.dist(p, q) < distanza for q in out):
            continue
        out.append(p)
    return out


def _normale_esterna(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy)
    n = (dy / L, -dx / L)
    m = ((a[0] + b[0]) / 2 + n[0] * 0.05, (a[1] + b[1]) / 2 + n[1] * 0.05)
    return (-n[0], -n[1]) if p.contains(Point(m)) else n


def _bordi_visibili(g):
    """I lati che guardano verso sud (di cui si vede la facciata), con la normale verso l'esterno del pieno."""
    out = []
    for p in _polys(g):
        for ring in [p.exterior] + list(p.interiors):
            cs = list(ring.coords)
            for a, b in zip(cs, cs[1:]):
                if math.dist(a, b) < 0.3:
                    continue
                n = _normale_esterna(p, a, b)
                if n[1] > 0.03:
                    out.append((a, b, n))
    return out


def _sweep(g, z0, z1):
    """L'ombra a terra di un volume che va da z0 a z1 metri d'altezza."""
    steps = max(2, int((z1 - z0) * OMBRA_PER_METRO / 1.2) + 1)
    parts = []
    for k in range(steps):
        z = (z0 + (z1 - z0) * k / (steps - 1)) * OMBRA_PER_METRO
        parts.append(affinity.translate(g, OMBRA[0] * z, OMBRA[1] * z))
    return unary_union(parts)


# ------------------------------------------------------------------ terreno
def alberi(t, punti, rmin=2.0, rmax=3.6):
    """Chiome irregolari (qualche cerchio sovrapposto), scure e spente come nelle foto aeree, con la loro ombra."""
    if not punti:
        return
    L, d = t.strato()
    rng = t.rng
    forme = []
    for x, y in punti:
        r = rng.uniform(rmin, rmax)
        blob = [(x, y, r)] + [(x + rng.uniform(-r, r) * 0.55, y + rng.uniform(-r, r) * 0.55, r * rng.uniform(0.5, 0.8))
                              for _ in range(rng.randint(2, 4))]
        forme.append(blob)
    for blob in forme:
        for x, y, r in blob:
            o = r * 1.3
            t.cerchio(d, (x + OMBRA[0] * o, y + OMBRA[1] * o), r, (16, 20, 18), 120)
    for blob in forme:
        base = tuple(max(0, min(255, c + rng.randint(-8, 8))) for c in CHIOMA)
        for x, y, r in blob:
            t.cerchio(d, (x, y), r, base)
        for x, y, r in blob:
            t.cerchio(d, (x + r * 0.25, y - r * 0.28), r * 0.55, _shade(base, 1.28), 200)
    t.metti(L)


def persone(t, area, densita):
    L, d = t.strato()
    for x, y in _punti_dentro(area, int(area.area * densita), t.rng):
        t.cerchio(d, (x, y), 0.3, (36, 36, 40) if t.rng.random() < 0.75 else (140, 60, 50), 220)
    t.metti(L)


def pavimento(t, area, ang, rgb=CEMENTO, passo=2.5):
    """Cemento o lastre: colore con macchie e una griglia leggera di giunti girata come l'edificio."""
    if area.is_empty:
        return
    t.colora(area, rgb, cella=3, amp=7, blur=0.5, macchie=9)
    L, d = t.strato()
    for a in (ang, ang + math.pi / 2):
        for s in _strisce(area, a, passo, 0.12):
            t.poligono(d, s, _shade(rgb, 0.9), 45)
    t.metti(L)


def prato(t, area):
    if area.is_empty:
        return
    t.colora(area, PRATO, cella=3, amp=10, blur=0.8, macchie=12)


def _pianta(e):
    return unary_union([Polygon(p.exterior.coords) for v in e['volumi'] if v['z0'] == 0 for p in _polys(v['forma'])])


def disegna_suolo(pt, suolo, edifici, buchi, rng):
    """Prima passata: il terreno del lotto. Cemento e lastre, marciapiede con cordolo lungo le strade, alberi in filare;
    poco verde: aiuole e piccoli giardini dove ci sono case, e nelle corti."""
    t = Tela(pt, rng)
    ang = edifici[0]['disposizione']['angolo']
    libero = suolo.difference(unary_union(buchi)) if buchi else suolo
    pavimento(t, libero, ang, passo=3.0)
    t.colora(libero.difference(suolo.buffer(-2.8, join_style=2)), MARCIAPIEDE, cella=3, amp=5, macchie=6)
    L, d = t.strato()
    for r in _rings(suolo):
        t.linea(d, list(r.coords), CORDOLO, 0.4)
    t.metti(L, libero)

    piante = unary_union([_pianta(e) for e in edifici])
    piante = unary_union([piante] + [c for e in edifici for c in e['corti']]).difference(
        unary_union([c for e in edifici for c in e['corti']]))
    vicino = piante.buffer(3.0, join_style=2)
    interno = libero.buffer(-3.5, join_style=2)
    punti = []
    # alberi in filare lungo i marciapiedi, ogni 10 m
    for r in _rings(libero.buffer(-1.6, join_style=2)):
        k = rng.uniform(0, 5)
        while k < r.length:
            q = r.interpolate(k)
            if not vicino.contains(q):
                punti.append((q.x, q.y))
            k += 10.0
    piazza = interno.difference(vicino)
    if any(e['cat'] == 'res' for e in edifici):
        # aiuole verdi a strisce attorno alle case, con qualche albero
        verde = piazza.buffer(-3.0, join_style=2)
        verde = unary_union([g for g in _polys(verde) if g.area > 60])
        prato(t, verde)
        punti += _punti_dentro(verde.buffer(-2.0), int(verde.area / 220), rng, 7)
    else:
        for _ in range(int(piazza.area / 1400)):         # fioriere rettangolari nella piazza
            c = _punti_dentro(piazza.buffer(-5), 1, rng)
            if not c:
                break
            aiuola = _rett(c[0], rng.uniform(6, 12), rng.uniform(3, 5), ang)
            if piazza.contains(aiuola):
                L, d = t.strato()
                t.poligono(d, aiuola.buffer(0.5, join_style=2), (150, 148, 142))
                t.metti(L)
                prato(t, aiuola)
                punti += _punti_dentro(aiuola.buffer(-1.0), 1, rng)
        persone(t, piazza, 0.003)
    for e in edifici:                                    # le corti
        for corte in e['corti']:
            pavimento(t, corte, ang, rgb=(160, 158, 152), passo=2.0)
            if e['corte'] == 'giardino':
                prato(t, corte.buffer(-3, join_style=2))
                punti += _punti_dentro(corte.buffer(-4), int(corte.area / 200), rng, 6)
            elif e['corte'] == 'lastricato':           # alberi in griglia ogni 10 m, con le loro aiuole
                interna = corte.buffer(-5, join_style=2)
                (ux, uy), (vx, vy) = _assi(ang)
                c = corte.centroid
                L, d = t.strato()
                for i in range(-12, 13):
                    for j in range(-12, 13):
                        q = (c.x + ux * i * 10 + vx * j * 10, c.y + uy * i * 10 + vy * j * 10)
                        if interna.contains(Point(q)):
                            t.poligono(d, _rett(q, 2.6, 2.6, ang), (120, 112, 96))
                            punti.append(q)
                t.metti(L)
    alberi(t, [q for q in punti if not piante.contains(Point(q))])
    # ombra di contatto: il terreno si scurisce appena al piede degli edifici
    t.colora(piante.buffer(1.2).difference(piante), (20, 22, 26), alpha=70, amp=0, blur=1.2)


# ------------------------------------------------------------------ ombre
def disegna_ombre(pt, edifici, area, rng):
    """Seconda passata: le ombre di tutti gli edifici (e dei vani scala sui tetti) su terreno e strade del Centro."""
    t = Tela(pt, rng)
    parts = []
    for e in edifici:
        for v in e['volumi']:
            parts.append(_sweep(v['forma'], v['z0'], v['z1']))
            if v['vano']:
                for vano in vani_scala(e, v):
                    parts.append(_sweep(vano, v['z1'], v['z1'] + VANO_SCALA))
    t.colora(unary_union(parts).intersection(area), (24, 28, 38), alpha=188, amp=0, blur=0.7)


# ------------------------------------------------------------------ edifici
def _misure(g):
    """Lato corto e lato lungo del rettangolo che contiene il volume."""
    r = g.minimum_rotated_rectangle
    cs = list(r.exterior.coords)
    a, b = math.dist(cs[0], cs[1]), math.dist(cs[1], cs[2])
    return min(a, b), max(a, b)


def vani_scala(e, v):
    """Il vano scala e ascensore (con le macchine) che sporge dal tetto del corpo: uno, due nei corpi lunghi."""
    ang = e['disposizione']['angolo']
    main = max(_polys(v['forma']), key=lambda p: p.area)
    inner = main.buffer(-2.5, join_style=2)
    if inner.is_empty:
        return []
    inner = max(_polys(inner), key=lambda p: p.area)
    out = []
    lungo = _misure(main)[1] > 45
    pts = [inner.representative_point()]
    if lungo:
        x0, y0, x1, y1 = inner.bounds
        pts = [Point(x0 + (x1 - x0) * f, y0 + (y1 - y0) * f) for f in (0.3, 0.7)]
        pts = [p if inner.contains(p) else inner.representative_point() for p in pts]
    for k, p in enumerate(pts):
        w, h = 6.0 + 2 * (k % 2), 4.5
        r = _rett((p.x, p.y), w, h, ang)
        if inner.contains(r):
            out.append(r)
    return out


def facciate(t, e, g, z0, z1, stile):
    """Le facciate rivolte a sud di un volume da z0 a z1: griglia di finestre, vetrine al piano terra, luce secondo
    l'orientamento."""
    rgb0, passo, vetro = FACCIATE[stile]
    vetrine = z0 == 0 and e['piani_dettaglio'][0]['destinazione_uso'] in ('negozio', 'ricettivo')
    rng = t.rng
    L, d = t.strato()
    k0, k1 = z0 * PROSPETTIVA, z1 * PROSPETTIVA
    piani = max(1, int(round((z1 - z0) / ALTEZZA_PIANO)))
    for a, b, n in sorted(_bordi_visibili(g), key=lambda q: (q[0][1] + q[1][1]) / 2):
        f = 0.74 + 0.24 * (n[0] * SOLE[0] + n[1] * SOLE[1])
        rgb = _shade(rgb0, f)
        t.quad(d, [(a[0], a[1] - k0), (b[0], b[1] - k0), (b[0], b[1] - k1), (a[0], a[1] - k1)], rgb)
        Lb = math.dist(a, b)
        cols = max(1, int(Lb / passo))
        ux, uy = (b[0] - a[0]) / cols, (b[1] - a[1]) / cols
        for i in range(piani):
            za = (z0 + i * ALTEZZA_PIANO + (0.15 if vetro else 0.9)) * PROSPETTIVA
            zb = (z0 + i * ALTEZZA_PIANO + (3.3 if vetro else 2.5)) * PROSPETTIVA
            for j in range(cols):
                if vetro:                                # pannelli di vetro con riflessi diversi
                    s = rng.uniform(0.85, 1.25)
                    col, x0, x1 = _shade(rgb, s), j, j + 0.94
                else:                                    # finestre scure tra i pilastri
                    col, x0, x1 = (52, 56, 62) if rng.random() > 0.08 else (120, 120, 116), j + 0.22, j + 0.78
                p0 = (a[0] + ux * x0, a[1] + uy * x0)
                p1 = (a[0] + ux * x1, a[1] + uy * x1)
                t.quad(d, [(p0[0], p0[1] - za), (p1[0], p1[1] - za), (p1[0], p1[1] - zb), (p0[0], p0[1] - zb)], col,
                       200 if vetro else 210)
        if vetro:                                        # il cielo si riflette più chiaro in alto
            km = k0 + (k1 - k0) * 0.6
            t.quad(d, [(a[0], a[1] - km), (b[0], b[1] - km), (b[0], b[1] - k1), (a[0], a[1] - k1)], (170, 186, 200), 45)
        if vetrine:
            zt = 3.2 * PROSPETTIVA
            t.quad(d, [a, b, (b[0], b[1] - zt), (a[0], a[1] - zt)], (44, 50, 58), 230)
        t.linea(d, [(a[0], a[1] - k1), (b[0], b[1] - k1)], _shade(rgb0, 1.15), 0.3)   # il bordo del parapetto
    t.metti(L)


def _parapetto(t, g, rgb):
    """Il bordo del tetto: un filo chiaro all'esterno e l'ombra del parapetto dentro."""
    L, d = t.strato()
    for r in _rings(g.buffer(-0.7, join_style=2)):
        t.linea(d, list(r.coords), (40, 40, 42), 0.5, 70)
    for r in _rings(g):
        t.linea(d, list(r.coords), _shade(rgb, 1.12), 0.4)
    t.metti(L)


def _sezioni(t, g, ang, rgb):
    """Il tetto diviso in campiture di tono un po' diverso, come i tetti rifatti in tempi diversi, con le giunture."""
    rng = t.rng
    (ux, uy), (vx, vy) = _assi(ang)
    x0, y0, x1, y1 = g.bounds
    R = math.hypot(x1 - x0, y1 - y0)
    c = g.centroid
    cuts = sorted(rng.uniform(-0.35, 0.35) * R for _ in range(rng.randint(1, 3)))
    edges = [-R] + cuts + [R]
    L, d = t.strato()
    for k in range(len(edges) - 1):
        a, b = edges[k], edges[k + 1]
        strip = Polygon([(c.x + ux * a - vx * R, c.y + uy * a - vy * R), (c.x + ux * b - vx * R, c.y + uy * b - vy * R),
                         (c.x + ux * b + vx * R, c.y + uy * b + vy * R), (c.x + ux * a + vx * R, c.y + uy * a + vy * R)])
        f = rng.uniform(0.9, 1.06)
        if abs(f - 1) > 0.02:
            t.poligono(d, strip.intersection(g), (255, 255, 255) if f > 1 else (0, 0, 0), int(abs(f - 1) * 600))
    for cut in cuts:
        t.linea(d, [(c.x + ux * cut - vx * R, c.y + uy * cut - vy * R), (c.x + ux * cut + vx * R, c.y + uy * cut + vy * R)],
                _shade(rgb, 0.8), 0.25, 160)
    t.metti(L, g)


def _scatola(t, d, c, w, h, ang, alto, rgb):
    """Una macchina sul tetto: la sua ombra, il fianco a sud e il coperchio più chiaro."""
    r = _rett(c, w, h, ang)
    t.poligono(d, _sweep(r, 0, alto), (30, 32, 36), 120)
    top = affinity.translate(r, 0, -alto * PROSPETTIVA)
    for a, b, n in _bordi_visibili(r):
        t.quad(d, [a, b, (b[0], b[1] - alto * PROSPETTIVA), (a[0], a[1] - alto * PROSPETTIVA)], _shade(rgb, 0.72))
    t.poligono(d, top, rgb)
    return top


def _impianti(t, area, ang, densita, grandi=False):
    """Gli impianti sul tetto: macchine di varie misure (alcune con le ventole), torri di raffreddamento, condotti,
    lucernari e botole, sparsi come nelle foto vere."""
    if area.is_empty:
        return
    rng = t.rng
    L, d = t.strato()
    n = max(1, int(area.area * densita))
    centri = _punti_dentro(area.buffer(-1.0), n, rng, 3.2)
    scatole = []
    for c in centri:
        kind = rng.random()
        if kind < 0.12:                                  # lucernario o botola
            w, h = rng.uniform(1.2, 3.0), rng.uniform(1.2, 2.2)
            t.poligono(d, _rett(c, w, h, ang), (108, 124, 134) if rng.random() < 0.6 else (90, 90, 92))
            continue
        w, h = rng.uniform(1.4, 5.5), rng.uniform(1.2, 3.4)
        col = tuple([rng.randint(186, 226)] * 3)
        top = _scatola(t, d, c, w, h, ang, rng.uniform(0.8, 2.2), col)
        scatole.append(c)
        if rng.random() < 0.35:                          # ventole
            tc = top.centroid
            for s in (-1, 1):
                q = (tc.x + math.cos(ang) * s * w * 0.22, tc.y + math.sin(ang) * s * w * 0.22)
                t.cerchio(d, q, min(w, h) * 0.22, (70, 72, 76))
    if grandi and area.area > 700:                       # torri di raffreddamento
        for c in _punti_dentro(area.buffer(-3), rng.randint(1, 3), rng, 7):
            r = rng.uniform(1.6, 2.6)
            t.cerchio(d, (c[0] + OMBRA[0] * 1.5, c[1] + OMBRA[1] * 1.5), r, (30, 32, 36), 120)
            t.cerchio(d, c, r, (206, 206, 204), outline=(150, 150, 150), ow=0.25)
            t.cerchio(d, c, r * 0.55, (64, 66, 70))
    for i in range(0, len(scatole) - 1, 3):              # condotti tra le macchine
        a, b = scatole[i], scatole[i + 1]
        if math.dist(a, b) < 25:
            mid = (a[0], b[1]) if rng.random() < 0.5 else (b[0], a[1])
            t.linea(d, [(a[0] + 0.5, a[1] + 0.8), (mid[0] + 0.5, mid[1] + 0.8), (b[0] + 0.5, b[1] + 0.8)], (40, 40, 44), 0.55, 90)
            t.linea(d, [a, mid, b], (196, 196, 194), 0.55)
    t.metti(L, area)


SPECIALI = ('piscina', 'eliporto', 'osservatorio', 'terrazza', 'lucernari')


def ombre_sul_tetto(t, g, h, piu_alti):
    """L'ombra dei corpi più alti (la torre sul suo podio, il corpo accanto un piano più su) sul tetto alto h metri."""
    parts = []
    for w in piu_alti:
        sh = _sweep(w['forma'], 0, w['z1'] - h)
        parts.append(_sposta(sh, h))
    if parts:
        t.colora(unary_union(parts).intersection(g), (24, 28, 38), alpha=170, amp=0, blur=0.4)


def tetto(t, e, v, piu_alti=()):
    """Il tetto di un volume: piano, con campiture, parapetto, impianti e vano scala; sul corpo principale le cose
    speciali dell'edificio (piscina, eliporto, osservatorio, terrazza, lucernari); pannelli e tetto verde anche altrove."""
    stile = v['tetto']
    if stile in SPECIALI and not v['speciale']:
        stile = 'ghiaia'
    ultimo = v['vano']
    ang = e['disposizione']['angolo']
    g = _sposta(v['forma'], v['z1'])
    rgb = TETTI[stile]
    rng = t.rng
    t.colora(g, rgb, cella=2.5, amp=6, macchie=14 if stile in ('chiaro', 'solare') else 9)
    if stile != 'verde':
        _sezioni(t, g, ang, rgb)
    _parapetto(t, g, rgb)
    ombre_sul_tetto(t, g, v['z1'], piu_alti)
    area = g.buffer(-1.2, join_style=2)
    if area.is_empty:
        return
    corto = _misure(v['forma'])[0]
    vani = vani_scala(e, v) if ultimo else []                 # a terra; sul tetto stanno spostati di z1
    sul_tetto = [_sposta(q, v['z1']) for q in vani]
    libero = area.difference(unary_union([q.buffer(1.5) for q in sul_tetto])) if vani else area
    if stile == 'solare':
        L, d = t.strato()
        zona = libero.buffer(-1.5, join_style=2)
        for s in _strisce(zona, ang, 2.6, 1.6):
            t.poligono(d, s, (36, 46, 70))
            t.poligono(d, affinity.translate(s, 0.3, 0.6), (20, 22, 28), 60)
        for s in _strisce(zona, ang + math.pi / 2, 1.1, 0.1):
            t.poligono(d, s, (120, 130, 150), 70)
        t.metti(L, zona)
        _impianti(t, libero.difference(zona.buffer(-0.5)), ang, 1 / 300)
    elif stile == 'verde':
        prato(t, libero.buffer(-0.8, join_style=2))
        L, d = t.strato()
        c = libero.centroid
        for u in _assi(ang):
            t.linea(d, [(c.x - u[0] * 80, c.y - u[1] * 80), (c.x + u[0] * 80, c.y + u[1] * 80)], (186, 180, 166), 1.8)
        t.metti(L, libero.buffer(-0.8, join_style=2))
        alberi(t, _punti_dentro(libero.buffer(-3), int(libero.area / 160), rng, 5), 1.2, 2.2)
    elif stile == 'piscina':
        main = max(_polys(libero), key=lambda p: p.area)
        c = main.centroid
        r = main.minimum_rotated_rectangle
        cs = list(r.exterior.coords)
        long_axis = max(((cs[i], cs[i + 1]) for i in range(2)), key=lambda q: math.dist(*q))
        long_axis = math.atan2(long_axis[1][1] - long_axis[0][1], long_axis[1][0] - long_axis[0][0])
        ph = min(5.0, corto * 0.3)
        pool = None
        for pw in (16.0, 11.0, 7.0):
            cand = _rett((c.x, c.y), pw, ph, long_axis)
            if main.buffer(-1.5).contains(cand):
                pool = cand
                break
        if pool is not None:
            L, d = t.strato()
            t.poligono(d, pool.buffer(1.6, join_style=2), (190, 168, 132))      # ponte in legno
            t.poligono(d, pool, (46, 132, 168))
            t.poligono(d, pool.buffer(-0.6, join_style=2), (70, 160, 192))
            (ux, uy), (vx, vy) = _assi(long_axis)
            for i in range(-3, 4):
                p = (c.x + ux * i * 2.2 + vx * (ph / 2 + 2.4), c.y + uy * i * 2.2 + vy * (ph / 2 + 2.4))
                if main.contains(Point(p)):
                    t.poligono(d, _rett(p, 0.7, 1.8, long_axis), (236, 236, 232))
            t.metti(L)
            libero = libero.difference(pool.buffer(3.5))
        _impianti(t, libero, ang, 1 / 220)
    elif stile == 'eliporto':
        c = max(_polys(libero), key=lambda p: p.area).representative_point()
        r = max(4.0, min(9.0, corto * 0.22))
        L, d = t.strato()
        t.cerchio(d, (c.x, c.y), r, (74, 76, 80), outline=(230, 230, 226), ow=0.5)
        t.cerchio(d, (c.x, c.y), r * 0.7, None, outline=(220, 190, 70), ow=0.3)
        s = r * 0.38
        for p1, p2 in (((-s * 0.6, -s), (-s * 0.6, s)), ((s * 0.6, -s), (s * 0.6, s)), ((-s * 0.6, 0), (s * 0.6, 0))):
            t.linea(d, [(c.x + p1[0], c.y + p1[1]), (c.x + p2[0], c.y + p2[1])], (236, 236, 232), 0.5)
        t.metti(L)
        _impianti(t, libero.difference(Point(c.x, c.y).buffer(r + 2)), ang, 1 / 200, grandi=True)
    elif stile == 'osservatorio':
        # la cupola di vetro dell'osservatorio panoramico, blu come quelle delle foto, con la terrazza intorno
        c = max(_polys(libero), key=lambda p: p.area).representative_point()
        r = max(3.5, min(8.0, corto * 0.2))
        L, d = t.strato()
        t.cerchio(d, (c.x + OMBRA[0] * r * 0.6, c.y + OMBRA[1] * r * 0.6), r, (24, 28, 36), 130)
        t.cerchio(d, (c.x, c.y), r + 1.6, (196, 192, 184))
        for i in range(10, 0, -1):
            f = i / 10
            t.cerchio(d, (c.x + r * 0.22 * (1 - f), c.y - r * 0.22 * (1 - f)), r * f, _shade((52, 92, 132), 0.8 + 0.6 * (1 - f)))
        for i in range(10):
            a = i * math.pi / 5
            t.linea(d, [(c.x, c.y), (c.x + math.cos(a) * r, c.y + math.sin(a) * r)], (150, 176, 200), 0.12, 150)
        t.metti(L)
    elif stile == 'terrazza':
        L, d = t.strato()
        t.poligono(d, libero, (176, 150, 116))                                  # pavimento in legno
        for c in _punti_dentro(libero.buffer(-1.0), int(libero.area / 28), rng, 3.4):
            t.cerchio(d, (c[0] + OMBRA[0], c[1] + OMBRA[1]), 1.2, (30, 30, 30), 110)
            t.cerchio(d, c, 1.2, (236, 234, 226) if rng.random() < 0.7 else (176, 70, 56))
        t.metti(L, libero)
    elif stile == 'lucernari':
        L, d = t.strato()
        for s in _strisce(libero.buffer(-2.5, join_style=2), ang + math.pi / 2, 6.5, 2.2):
            t.poligono(d, s, (112, 132, 146))
            t.poligono(d, affinity.translate(s, -0.2, -0.4), (160, 178, 190), 160)
        t.metti(L)
        _impianti(t, libero, ang, 1 / 500)
    else:
        _impianti(t, libero, ang, 1 / 75 if ultimo else 1 / 160, grandi=ultimo and e['cat'] in ('uff', 'pub', 'com'))
    for q, qt in zip(vani, sul_tetto):                   # i vani scala, con le loro facciate e la loro ombra sul tetto
        L, d = t.strato()
        t.poligono(d, _sweep(qt, 0, VANO_SCALA).intersection(g), (26, 28, 34), 130)
        t.metti(L)
        facciate(t, e, q, v['z1'], v['z1'] + VANO_SCALA, 'intonaco_chiaro')
        top = _sposta(q, v['z1'] + VANO_SCALA)
        t.colora(top, (198, 198, 194), cella=2, amp=5, macchie=8)
        _parapetto(t, top, (198, 198, 194))
        _impianti(t, top.buffer(-0.8), ang, 1 / 15)


def corte_coperta(t, e):
    """Nella corte: una vetrata alla quota del corpo più basso, oppure una cupola."""
    ang = e['disposizione']['angolo']
    z1 = min(v['z1'] for v in e['volumi'] if v['z0'] == 0)
    v = {'z1': z1}
    for corte in e['corti']:
        if True:
            if e['corte'] == 'vetrata':
                g = _sposta(corte, v['z1'] - 1.0)
                t.colora(g, (118, 138, 152), alpha=240, amp=4)
                L, d = t.strato()
                for s in _strisce(g, ang, 2.4, 0.22):
                    t.poligono(d, s, (190, 204, 212), 170)
                for s in _strisce(g, ang + math.pi / 2, 6.0, 0.35):
                    t.poligono(d, s, (70, 80, 90), 220)
                t.metti(L, g)
            elif e['corte'] == 'cupola':
                c = corte.centroid
                x0, y0, x1, y1 = corte.bounds
                r = min(12.0, min(x1 - x0, y1 - y0) * 0.32)
                z = v['z1'] + r * 0.4
                cx, cy = c.x, c.y - z * PROSPETTIVA
                L, d = t.strato()
                t.cerchio(d, (cx + OMBRA[0] * r * 0.7, cy + OMBRA[1] * r * 0.7), r, (24, 28, 36), 120)
                t.quad(d, [(c.x - r, c.y), (c.x + r, c.y), (cx + r, cy), (cx - r, cy)], (176, 172, 162))
                for i in range(12, 0, -1):               # la cupola blu, più chiara verso nord-est
                    f = i / 12
                    t.cerchio(d, (cx + r * 0.22 * (1 - f), cy - r * 0.22 * (1 - f)), r * f,
                              _shade((46, 86, 128), 0.8 + 0.6 * (1 - f)))
                for i in range(12):
                    a = i * math.pi / 6
                    t.linea(d, [(cx, cy), (cx + math.cos(a) * r, cy + math.sin(a) * r)], (140, 168, 196), 0.15, 150)
                t.cerchio(d, (cx, cy), r * 0.12, (220, 214, 196))
                t.metti(L)


def disegna_edifici(pt, edifici, rng):
    """Terza passata: i corpi del lotto dal basso in alto (prima quelli a terra, poi il fusto delle torri sul podio, poi la
    loro cima) e, alla stessa quota, da nord a sud (quelli più a sud coprono quelli dietro); infine le corti coperte."""
    t = Tela(pt, rng)
    vol = [(e, v) for e in edifici for v in e['volumi']]
    for e, v in sorted(vol, key=lambda q: (q[1]['z0'], q[1]['forma'].bounds[3])):
        facciate(t, e, v['forma'], v['z0'], v['z1'], v['facciata'])
        vicini = v['forma'].buffer(v['z1'])               # solo i corpi abbastanza vicini da fare ombra
        tetto(t, e, v, [w for _, w in vol if w['z1'] > v['z1'] + 0.5 and w['forma'].intersects(vicini)])
    for e in edifici:
        if e['corte'] in ('vetrata', 'cupola') and e['corti']:
            corte_coperta(t, e)
