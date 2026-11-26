# Gli insediamenti dei nuovi edifici del censimento (scuole, negozi, supermercati, aziende agricole). Lo usa tools/perimetri.py;
# tools/disegna_satellite.py li disegna con pezzi veri della foto (tools/tessiture.py).
#
# Un edificio nuovo non si mette da solo in mezzo a un prato: arriva con quello che gli serve intorno, come gli edifici veri della
# foto. I negozi di uno stesso nucleo stanno in fila con il parcheggio davanti e il marciapiede; una scuola ha il parcheggio di
# lato, il vialetto pedonale dalla strada all'ingresso e il giardino; un supermercato il parcheggio grande davanti; un'azienda
# agricola l'aia di ghiaia con la siepe intorno e la strada d'accesso dai campi. Tutto l'insediamento sta su terreno libero
# (prato, campi, terra: niente tetti, asfalto, giardini recintati, piscine, vialetti, alberi fitti), lontano dalle case, dentro un
# lotto e affacciato su una strada vera (public/data/streets.json); l'accesso va dall'asfalto della strada al parcheggio o all'aia.
#
# La ricerca: per ogni lotto una griglia con gli assi lungo un lato del lotto (Griglia), le maschere di ciò che c'è già nella foto e
# nei dati; la disposizione dell'insediamento (Disposizione) è un insieme di rettangoli con il fronte verso la strada; con le
# immagini integrali si trovano tutte le posizioni in cui ogni rettangolo ha il terreno che gli serve, nei quattro versi del lotto.
import collections, json, math, os, re

import cv2
import numpy as np
import shapely
from shapely import affinity
from shapely.geometry import LineString, MultiPolygon, Point, Polygon

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'public', 'data')

MARGINE_GRIGLIA = 32.0        # metri di griglia fuori dal lotto: la strada davanti e le case dei lotti vicini
CORSIA = 6.0                  # larghezza di un accesso carrabile
MODULO = 16.5                 # profondità di un parcheggio a pettine: fila di auto, corsia, fila di auto
MARCIAPIEDE = 3.0
VERDE_STRADA = 1.5            # dal bordo del lotto al primo elemento (il marciapiede della strada resta com'è)
# distanza dell'edificio dalle case della foto (metri) e dal resto (asfalto, cortili, recinti), per tipo
DISTANZA_CASE = {'scuola': 20, 'supermercato': 16, 'negozio': 12, 'agricolo': 30, 'fabbrica': 30}
DISTANZA_ALTRO = {'scuola': 6, 'supermercato': 5, 'negozio': 4, 'agricolo': 6, 'fabbrica': 6}
# gradi di ricerca, dal più severo: (moltiplicatore delle distanze dalle case, parte massima di alberi sotto edifici e parcheggi,
# raggio massimo dal posto previsto come multiplo del raggio del tipo; None: ovunque)
GRADI = [(1.0, 0.08, 1.0), (1.0, 0.12, 1.6), (0.75, 0.2, 1.6), (0.55, 0.3, None)]


def linea(path):
    n = list(map(float, re.findall(r'-?\d+\.?\d*', path)))
    return LineString(list(zip(n[0::2], n[1::2])))


class Strade:
    """Le strade: streets.json ha le vie principali (main, country, minor, larghe `size`); le altre sono nella foto, tra un lotto e
    l'altro. Una cella è strada se sta fuori da ogni lotto e la foto lì ha asfalto (o c'è una via di streets.json), non binari."""

    def __init__(self, lotti):
        streets = json.load(open(os.path.join(DATA, 'streets.json'), encoding='utf-8'))
        self.linee = [(linea(s['path']), s['size'], s['kind'], s['name']) for s in streets if s['kind'] in ('main', 'country', 'minor')]
        self.asfalto = shapely.STRtree([l.buffer(sz / 2) for l, sz, _, _ in self.linee])
        self.binari = shapely.STRtree([linea(s['path']).buffer(s['size'] / 2 + 3) for s in streets if s['kind'] in ('rail', 'river')])
        self.lotti = shapely.STRtree(list(lotti))

    @staticmethod
    def _vicini(albero, bbox):
        idx = albero.query(shapely.box(*bbox))
        if len(idx) == 0:
            return None
        g = shapely.union_all(albero.geometries.take(idx))
        shapely.prepare(g)
        return g

    def maschera(self, foto, X, Y, dentro):
        """Le celle di strada (fuori da `dentro`, il lotto della griglia)."""
        bbox = (X.min(), Y.min(), X.max(), Y.max())
        fuori = ~dentro
        xs, ys = X[fuori], Y[fuori]
        ok = np.ones(xs.shape, bool)
        for albero in (self.lotti, self.binari):
            g = self._vicini(albero, bbox)
            if g is not None:
                ok &= ~shapely.contains_xy(g, xs, ys)
        a = foto.campiona('asfalto', xs, ys)
        g = self._vicini(self.asfalto, bbox)
        if g is not None:
            a |= shapely.contains_xy(g, xs, ys)
        out = np.zeros(X.shape, bool)
        out[fuori] = ok & a
        return out


def integrale(m):
    return np.pad(np.cumsum(np.cumsum(m.astype(np.int32), 0), 1), ((1, 0), (1, 0)))


def finestre(S, h, w):
    """Somme su tutte le finestre h×w (in alto a sinistra) da un'immagine integrale."""
    return S[h:, w:] - S[:-h, w:] - S[h:, :-w] + S[:-h, :-w]


def senza_puntini(m, area_min, passo):
    """La maschera senza le macchie più piccole di `area_min` m²."""
    m = m.astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    piccoli = np.nonzero(st[:, cv2.CC_STAT_AREA] * passo * passo < area_min)[0]
    piccoli = piccoli[piccoli > 0]
    if len(piccoli):
        m[np.isin(lab, piccoli)] = 0
    return m.astype(bool)


def disco(r):
    r = max(1, int(round(r)))
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


class Griglia:
    """Un lotto visto su una griglia con gli assi lungo l'angolo `ang` (un lato del lotto), con un margine intorno: dentro il lotto,
    terreno libero, case, alberi, acqua e vialetti, strade, luoghi mappati e nuovi insediamenti."""

    def __init__(self, foto, strade, lp, ang, bloccati):
        self.lp, self.ang = lp, ang
        c = lp.centroid
        self.cx, self.cy = c.x, c.y
        self.passo = p = 1.5 if lp.area < 300000 else 2.0
        rot = affinity.rotate(lp, -ang, origin=(self.cx, self.cy))
        umin, vmin, umax, vmax = rot.bounds
        m = MARGINE_GRIGLIA
        us = np.arange(umin - m + p / 2, umax + m, p) - self.cx
        vs = np.arange(vmin - m + p / 2, vmax + m, p) - self.cy
        self.U, self.V = np.meshgrid(us, vs)
        self.cs, self.sn = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        X, Y = self.mondo(self.U, self.V)
        self.dentro = shapely.contains_xy(lp, X, Y)
        pad = np.pad(self.dentro.astype(np.uint8), 1)
        self.bordo = cv2.distanceTransform(pad, cv2.DIST_L2, 3)[1:-1, 1:-1] * p
        libero = np.ones(X.shape, bool)
        for du, dv in ((0, 0), (-p / 3, -p / 3), (p / 3, -p / 3), (-p / 3, p / 3), (p / 3, p / 3)):
            xx, yy = X + du * self.cs - dv * self.sn, Y + du * self.sn + dv * self.cs
            libero &= foto.libero_array(xx, yy)
        self.libero = libero
        # case: i tetti della foto, senza righe sottili (campi sportivi, strisce) e senza le auto
        case = foto.campiona('case', X, Y).astype(np.uint8)
        k = max(1, int(round(2 / p)))
        case = cv2.morphologyEx(case, cv2.MORPH_OPEN, np.ones((k, k), np.uint8))
        n, lab, st, _ = cv2.connectedComponentsWithStats(case, connectivity=8)
        piccoli = [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] * p * p < 25]
        if piccoli:
            case[np.isin(lab, piccoli)] = 0
        self.case = case.astype(bool)
        # il resto di ciò che non è terreno libero (asfalto, cortili, tetti scuri, recinti), senza i puntini isolati (sassi, ombre di
        # cespugli, chiazze nei campi secchi): contano solo le macchie di almeno 15 m²
        self.altro = senza_puntini(~libero, 15, p)
        self.ostacoli = senza_puntini(foto.campiona('acqua', X, Y) | foto.campiona('vialetti', X, Y), 12, p)
        self.scuro = senza_puntini(foto.campiona('scuro', X, Y), 40, p)
        self.alberi = foto.campiona('alberi', X, Y)
        self.strada = strade.maschera(foto, X, Y, self.dentro)
        self.bloc = np.zeros(X.shape, bool)
        if bloccati is not None and not bloccati.is_empty:
            self.bloc = shapely.contains_xy(bloccati, X, Y)
        self._cache = {}

    # ---- coordinate
    def mondo(self, U, V):
        return self.cx + U * self.cs - V * self.sn, self.cy + U * self.sn + V * self.cs

    def in_griglia(self, x, y):
        dx, dy = x - self.cx, y - self.cy
        return dx * self.cs + dy * self.sn, -dx * self.sn + dy * self.cs

    def occupa(self, poly):
        X, Y = self.mondo(self.U, self.V)
        self.bloc |= shapely.contains_xy(poly, X, Y)
        self._cache = {}

    # ---- maschere (nei quattro versi: k quarti di giro, il fronte dell'insediamento è sempre in alto)
    def _dil(self, nome, metri):
        chiave = ('dil', nome, round(metri, 1))
        if chiave not in self._cache:
            m = getattr(self, nome).astype(np.uint8)
            self._cache[chiave] = cv2.dilate(m, disco(metri / self.passo)).astype(bool) if metri > 0 else m.astype(bool)
        return self._cache[chiave]

    def _interno(self, metri):
        chiave = ('interno', round(metri, 1))
        if chiave not in self._cache:
            self._cache[chiave] = self.bordo > metri
        return self._cache[chiave]

    def cattivo(self, tipo, d_case, d_altro):
        """Le celle dove un elemento non può stare: 'E' edificio, 'P' parcheggio o pavimento, 'M' margine dell'insediamento,
        'T' strada d'accesso lunga (aziende agricole)."""
        chiave = ('bad', tipo, round(d_case, 1), round(d_altro, 1))
        if chiave not in self._cache:
            if tipo == 'E':
                m = (~self.libero | self._dil('case', d_case) | self._dil('altro', d_altro) | self._dil('ostacoli', 4)
                     | self._dil('bloc', 4) | self._dil('scuro', 2) | ~self._interno(2.0))
            elif tipo == 'P':
                m = (~self.libero | self._dil('case', min(d_case, 5)) | self._dil('ostacoli', 2) | self._dil('bloc', 2)
                     | self.scuro | ~self._interno(1.0))
            elif tipo == 'M':
                m = self._dil('case', 3) | self.ostacoli | self.bloc | ~self.dentro
            else:
                m = self._dil('case', 3) | self.ostacoli | self.bloc | ~self.dentro | self.alberi
            self._cache[chiave] = m
        return self._cache[chiave]

    def ruotata(self, k, chiave, f):
        c = ('rot', k, chiave)
        if c not in self._cache:
            self._cache[c] = f(np.rot90(self._sorgente(chiave), k))
        return self._cache[c]

    def _sorgente(self, chiave):
        if isinstance(chiave, tuple):
            return self.cattivo(*chiave)
        return getattr(self, chiave)

    def fronte(self, k):
        """Per ogni colonna (girata di k quarti): la prima riga dentro il lotto e se lì davanti (entro 12 m) c'è una strada."""
        c = ('fronte', k)
        if c not in self._cache:
            d = np.rot90(self.dentro, k)
            ny, nx = d.shape
            rb = np.where(d.any(0), d.argmax(0), ny)
            st = np.rot90(self.strada, k)
            cum = np.vstack([np.zeros((1, nx), np.int32), np.cumsum(st.astype(np.int32), 0)])
            s = int(round(12 / self.passo))
            cols = np.arange(nx)
            a = np.clip(rb - s, 0, ny)
            b = np.clip(rb, 0, ny)
            ok = (cum[b, cols] - cum[a, cols]) * self.passo >= 4.5         # una strada larga almeno 4,5 m
            self._cache[c] = (rb, ok)
        return self._cache[c]

    def assi(self, k):
        """Le direzioni (nel mondo) di colonne e righe della griglia girata di k quarti, e le coordinate (U, V) girate."""
        U, V = np.rot90(self.U, k), np.rot90(self.V, k)
        du = np.array([U[0, 1] - U[0, 0], V[0, 1] - V[0, 0]]) / self.passo
        dv = np.array([U[1, 0] - U[0, 0], V[1, 0] - V[0, 0]]) / self.passo
        def vett(d):
            return np.array([d[0] * self.cs - d[1] * self.sn, d[0] * self.sn + d[1] * self.cs])
        return vett(du), vett(dv), U, V


class Elemento:
    __slots__ = ('tipo', 'u0', 'v0', 'w', 'h', 'maschera', 'tol', 'edificio')

    def __init__(self, tipo, u0, v0, w, h, maschera=None, tol=0.0, edificio=None):
        self.tipo, self.u0, self.v0, self.w, self.h = tipo, u0, v0, w, h
        self.maschera, self.tol, self.edificio = maschera, tol, edificio


class Disposizione:
    """Un insediamento nel suo sistema: u lungo la strada, v verso l'interno del lotto (v = 0 è il bordo del lotto, davanti c'è la
    strada). `ingressi`: le colonne (u0, larghezza, fino a v) degli accessi dalla strada; `pista`: un accesso lungo (aziende
    agricole) che può attraversare il lotto fino a `pista_max` metri."""

    def __init__(self, tipo, elementi, W, H, ingressi, pista=None, pista_max=0.0, costo=0.0):
        self.tipo, self.elementi, self.W, self.H = tipo, elementi, W, H
        self.ingressi, self.pista, self.pista_max, self.costo = ingressi, pista, pista_max, costo


def cerca(g, disp, k, bersaglio, d_case, d_altro, alberi_max, scarta=(), vicini=(), entro=None, storto_extra=0.0):
    """La posizione migliore di `disp` nella griglia girata di k quarti: (punteggio, r, c, dettagli) o None."""
    p = g.passo
    rb, strada_ok = g.fronte(k)
    dentro = np.rot90(g.dentro, k)
    ny, nx = dentro.shape
    Hc, Wc = int(math.ceil(disp.H / p)), int(math.ceil(disp.W / p))
    if Hc + 2 > ny or Wc + 2 > nx:
        return None
    R, C = ny - Hc + 1, nx - Wc + 1
    ok = np.ones((R, C), bool)
    alb = np.zeros((R, C), np.float32)
    area_alb = 0
    for e in disp.elementi:
        if e.maschera is None:
            continue
        r0, c0 = int(round(e.v0 / p)), int(round(e.u0 / p))
        h, w = max(1, int(round(e.h / p))), max(1, int(round(e.w / p)))
        h, w = min(h, Hc - r0), min(w, Wc - c0)
        chiave = (e.maschera, d_case, d_altro)
        S = g.ruotata(k, chiave, integrale)
        sub = finestre(S, h, w)[r0:r0 + R, c0:c0 + C]
        ok &= sub <= e.tol * h * w
        if not ok.any():
            return None
        if e.maschera in ('E', 'P'):
            A = g.ruotata(k, 'alberi', integrale)
            alb += finestre(A, h, w)[r0:r0 + R, c0:c0 + C]
            area_alb += h * w
    alb /= max(1, area_alb)
    ok &= alb <= alberi_max
    # nessuna sovrapposizione con i luoghi della mappa e con gli altri insediamenti nuovi, nemmeno ai bordi
    ok &= finestre(g.ruotata(k, 'bloc', integrale), Hc, Wc)[:R, :C] == 0
    if not ok.any():
        return None
    if disp.pista is None:                              # il fronte segue la strada: il bordo del lotto è parallelo al fronte
        win = np.lib.stride_tricks.sliding_window_view(rb, Wc)
        storto = (win.max(1) - win.min(1))[:C] * p
        ok &= (storto <= 3.0 + 0.06 * disp.W + storto_extra)[None, :]
        if not ok.any():
            return None
    rows = np.arange(R)[:, None]
    lunghezza = np.zeros((R, C), np.float32)
    for u0, w_m in disp.ingressi:
        c0, w = int(round(u0 / p)), max(1, int(round(w_m / p)))
        win_rb = np.lib.stride_tricks.sliding_window_view(rb, w)
        rbmin, rbmax = win_rb.min(1)[c0:c0 + C], win_rb.max(1)[c0:c0 + C]
        sok = np.lib.stride_tricks.sliding_window_view(strada_ok, w).all(1)[c0:c0 + C]
        gap = rows - rbmin[None, :]                       # celle tra il bordo del lotto e il fronte dell'insediamento
        ok &= (rows >= rbmax[None, :]) & sok[None, :]
        lungo = disp.pista is not None and (u0, w_m) == disp.pista
        lim = disp.pista_max if lungo else 3.5
        ok &= gap * p <= lim
        if lungo:
            # la pista attraversa il lotto: niente case, acqua, alberi o luoghi tra il bordo e l'aia
            T = np.rot90(g.cattivo('T', d_case, d_altro), k)
            cum = np.vstack([np.zeros((1, nx), np.int32), np.cumsum(T.astype(np.int32), 0)])
            cols = np.arange(nx)
            # per ogni riga r e colonna: celle cattive dalla prima riga del lotto alla riga r
            conta = cum[:R, :] - cum[np.clip(rb, 0, ny), cols][None, :]
            conta = np.where(rows >= rb[None, :], conta, 10 ** 6)
            cs = np.hstack([np.zeros((R, 1), np.int64), np.cumsum(conta, 1)])
            somma = cs[:, c0 + w:c0 + w + C] - cs[:, c0:c0 + C]
            ok &= somma == 0
            lunghezza = np.maximum(lunghezza, gap * p)
        if not ok.any():
            return None
    for r, c in scarta:
        if 0 <= r < R and 0 <= c < C:
            ok[r, c] = False
    if not ok.any():
        return None
    _, _, U, V = g.assi(k)
    uc, vc = U[Hc // 2:Hc // 2 + R, Wc // 2:Wc // 2 + C], V[Hc // 2:Hc // 2 + R, Wc // 2:Wc // 2 + C]
    bu, bv = g.in_griglia(*bersaglio)
    dist = np.hypot(uc - bu, vc - bv)
    punteggio = dist + 600 * alb + 1.5 * lunghezza + disp.costo
    for x, y, peso, raggio in vicini:                   # altri insediamenti simili già messi lì vicino
        gu, gv = g.in_griglia(x, y)
        punteggio = punteggio + peso * np.clip(1 - np.hypot(uc - gu, vc - gv) / raggio, 0, None)
    if entro is not None:                               # messo a mano: non più lontano di così dal punto dato
        ok &= dist <= entro
    punteggio = np.where(ok, punteggio, np.inf)
    i = int(np.argmin(punteggio))
    r, c = divmod(i, C)
    return float(punteggio[r, c]), r, c, {'dist': float(dist[r, c]), 'alberi': float(alb[r, c]), 'pista': float(lunghezza[r, c])}


def telaio(g, k, r, c):
    """Il sistema dell'insediamento nel mondo: l'origine (angolo in alto a sinistra) e le direzioni u (colonne) e v (righe)."""
    eu, ev, U, V = g.assi(k)
    x, y = g.mondo(U[r, c], V[r, c])
    o = np.array([x, y]) - 0.5 * g.passo * (eu + ev)
    return o, eu, ev


def rettangolo(o, eu, ev, u0, v0, u1, v1):
    return Polygon([tuple(o + u0 * eu + v0 * ev), tuple(o + u1 * eu + v0 * ev), tuple(o + u1 * eu + v1 * ev), tuple(o + u0 * eu + v1 * ev)])


def accesso(g, k, r, c, u0, w, v1):
    """L'accesso dalla strada: dalle colonne u0..u0+w, dall'asfalto della strada davanti fino a v1 (nel sistema dell'insediamento).
    Restituisce v0 (negativo: fuori dal lotto, sull'asfalto)."""
    p = g.passo
    st = np.rot90(g.strada, k)
    rb, _ = g.fronte(k)
    c0, cw = c + int(round(u0 / p)), max(1, int(round(w / p)))
    righe = []
    for cc in range(c0, min(c0 + cw, st.shape[1])):
        sopra = np.nonzero(st[:rb[cc], cc])[0]
        righe.append(sopra.max() if len(sopra) else rb[cc] - 1)
    v0 = (min(righe) - r) * p - 0.5                    # mezzo metro dentro l'asfalto
    return min(v0, -0.5)


# ------------------------------------------------------------------ disposizioni per tipo
def _dimensioni(d, k_par, ang):
    """Larghezza (lungo la strada) e profondità dell'edificio modello nel sistema dell'insediamento."""
    g = d['g0']
    q = affinity.rotate(g, -ang, origin=(0, 0))
    x0, y0, x1, y1 = q.bounds
    return (x1 - x0, y1 - y0) if k_par == 0 else (y1 - y0, x1 - x0)


SCUOLA_PARCHEGGIO = {'Asilo nido': 16, "Scuola dell'infanzia": 20, 'Scuola primaria': 28, 'Scuola media': 32, 'Liceo': 40}


def disposizione_negozi(modelli, dims, costo):
    """Negozi in fila, con il parcheggio davanti (fila, corsia, fila) e il marciapiede lungo le vetrine."""
    ms, gap = 3.0, 3.0
    Wb = sum(w for w, _ in dims) + gap * (len(dims) - 1)
    Wp = max(Wb, 16.0)
    v0 = VERDE_STRADA
    vf = v0 + MODULO + MARCIAPIEDE
    H = vf + max(h for _, h in dims) + 4
    W = Wp + 2 * ms
    el = [Elemento('margine', 0, 0, W, H, 'M', 0.03),
          Elemento('parcheggio', ms, v0, Wp, MODULO, 'P', 0.02),
          Elemento('marciapiede', ms, v0 + MODULO, Wp, MARCIAPIEDE, 'P', 0.04)]
    u = ms + (Wp - Wb) / 2
    for i, (w, h) in enumerate(dims):
        el.append(Elemento('edificio', u, vf, w, h, 'E', 0.01, edificio=i))
        u += w + gap
    ingressi = [(ms + 1.0, CORSIA)] if Wp < 34 else [(ms + 1.0, CORSIA), (ms + Wp - 1.0 - CORSIA, CORSIA)]
    return Disposizione('negozi', el, W, H, ingressi, costo=costo)


def disposizione_supermercato(dims, costo):
    (w, h), = dims
    ms = 4.0
    Wp = max(w + 20, 48.0)
    v0 = VERDE_STRADA
    vf = v0 + 2 * MODULO + 4
    H = vf + h + 10
    W = Wp + 2 * ms
    el = [Elemento('margine', 0, 0, W, H, 'M', 0.03),
          Elemento('parcheggio', ms, v0, Wp, 2 * MODULO, 'P', 0.02),
          Elemento('marciapiede', ms + (Wp - w) / 2 - 3, v0 + 2 * MODULO, w + 6, 4, 'P', 0.04),
          Elemento('edificio', ms + (Wp - w) / 2, vf, w, h, 'E', 0.01, edificio=0),
          # il cortile di carico dietro, raggiunto da una corsia di lato
          Elemento('piazzale', ms + Wp - CORSIA, v0 + 2 * MODULO, CORSIA, 4 + h + 8, 'P', 0.04),
          Elemento('piazzale', ms + (Wp - w) / 2, vf + h + 1, (Wp + w) / 2 - CORSIA + 0.0, 8, 'P', 0.04)]
    return Disposizione('supermercato', el, W, H, [(ms + 1.0, CORSIA + 1), (ms + Wp - CORSIA - 2.0, CORSIA + 1)], costo=costo)


CAMPO = {'Scuola primaria': (26.0, 14.0), 'Scuola media': (28.0, 15.5), 'Liceo': (28.0, 15.5)}     # campetto (lungo, largo)


def disposizione_scuola(nome, dims, costo, lato):
    """Una scuola nel suo giardino (prato con alberi, arbusti lungo il confine): il parcheggio di lato (lato = 'sinistra' o
    'destra') con l'edificio arretrato, il giardino davanti e il vialetto dalla strada all'ingresso con lo slargo; oppure
    (lato = 'davanti') il parcheggio davanti, il vialetto accanto e il sagrato lungo la facciata. Le primarie, le medie e i licei
    hanno un campetto da gioco nel giardino."""
    (w, h), = dims
    tipo = next((t for t in SCUOLA_PARCHEGGIO if nome.startswith(t)), 'Scuola primaria')
    Wp = SCUOLA_PARCHEGGIO[tipo]
    sv = 10.0 if tipo in ('Asilo nido', "Scuola dell'infanzia") else 13.0
    ms, gap, dietro = 3.0, 7.0, 12.0
    v0 = VERDE_STRADA
    campo = CAMPO.get(tipo)
    if lato == 'davanti':
        Wf = max(w, Wp + 4.5)
        if campo:
            Wf = max(Wf, campo[0] + 2)
            dietro = campo[1] + 8
        W = ms + Wf + 8 + ms
        H = v0 + MODULO + 4 + h + dietro
        ux = ms + Wp + 1.5
        el = [Elemento('giardino', 0, 0, W, H),
              Elemento('margine', 0, 0, W, H, 'M', 0.04),
              Elemento('parcheggio', ms, v0, Wp, MODULO, 'P', 0.02),
              Elemento('vialetto', ux, v0, 3.0, MODULO, 'P', 0.1),
              Elemento('piazzetta', ms, v0 + MODULO, Wf, 4, 'P', 0.05),
              Elemento('edificio', ms + (Wf - w) / 2, v0 + MODULO + 4, w, h, 'E', 0.01, edificio=0)]
        if campo:
            el.append(Elemento('campo', ms + (Wf - campo[0]) / 2, v0 + MODULO + 4 + h + 4, campo[0], campo[1], 'P', 0.03))
        return Disposizione('scuola', el, W, H, [(ms + 1.0, CORSIA), (ux, 3.0)], costo=costo + 4)
    W = ms + Wp + gap + w + 10 + ms
    H = v0 + max(sv + h + dietro, MODULO + 4)
    if lato == 'sinistra':
        up, ub = ms, ms + Wp + gap
    else:
        ub, up = ms + 10, ms + 10 + w + gap
    ux = ub + w / 2
    el = [Elemento('giardino', 0, 0, W, H),
          Elemento('margine', 0, 0, W, H, 'M', 0.04),
          Elemento('parcheggio', up, v0, Wp, MODULO, 'P', 0.02),
          Elemento('vialetto', ux - 1.5, v0, 3.0, sv - 5, 'P', 0.1),
          Elemento('piazzetta', ux - 7, v0 + sv - 5, 14, 5, 'P', 0.05),
          Elemento('edificio', ub, v0 + sv, w, h, 'E', 0.01, edificio=0)]
    if campo:                                       # dietro il parcheggio, se c'è posto
        prof = H - (v0 + MODULO + 4) - 3
        if prof >= campo[0] and Wp >= campo[1] + 2:
            el.append(Elemento('campo', up + (Wp - campo[1]) / 2, v0 + MODULO + 4, campo[1], campo[0], 'P', 0.03))
        elif Wp >= campo[0] + 2 and prof >= campo[1]:
            el.append(Elemento('campo', up + (Wp - campo[0]) / 2, v0 + MODULO + 4, campo[0], campo[1], 'P', 0.03))
    ingressi = [(up + 1.0 if lato == 'sinistra' else up + Wp - 1.0 - CORSIA, CORSIA), (ux - 1.5, 3.0)]
    return Disposizione('scuola', el, W, H, ingressi, costo=costo)


def disposizione_agricola(tipo, dims, costo, ingresso):
    """Un'azienda agricola: l'edificio in un'aia di ghiaia (un piazzale per un'industria agroalimentare) con la siepe intorno e
    un cortile davanti; la strada d'accesso (ingresso: 'centro', 'sinistra', 'destra') attraversa i campi fino alla strada."""
    (w, h), = dims
    ma, davanti, mm = 7.0, 14.0, 4.0
    Aw, Ah = w + 2 * ma, davanti + h + ma
    W, H = Aw + 2 * mm, Ah + mm + 2
    el = [Elemento('margine', 0, 0, W, H, 'M', 0.04),
          Elemento('aia', mm, 2, Aw, Ah, 'P', 0.04),
          Elemento('edificio', mm + ma, 2 + davanti, w, h, 'E', 0.01, edificio=0)]
    uc = {'centro': mm + Aw / 2 - 2.0, 'sinistra': mm + 3, 'destra': mm + Aw - 7}[ingresso]
    pista = (uc, 4.0)
    return Disposizione(tipo, el, W, H, [pista], pista=pista, pista_max=160.0 if tipo == 'agricolo' else 90.0, costo=costo)


def varianti(tipo, nome, dims, costo):
    if tipo == 'negozi':
        return [disposizione_negozi(None, dims, costo)]
    if tipo == 'supermercato':
        return [disposizione_supermercato(dims, costo)]
    if tipo == 'scuola':
        return [disposizione_scuola(nome, dims, costo, lato) for lato in ('sinistra', 'destra', 'davanti')]
    return [disposizione_agricola(tipo, dims, costo, i) for i in ('centro', 'sinistra', 'destra')]


# ------------------------------------------------------------------ i modelli (edifici veri della foto)
# modelli da non usare: un edificio alto (dall'alto se ne vedono le facciate), un tetto arancione acceso, un tetto rosso e giallo
# e quelli con l'ombra di un palazzo vicino sul tetto, a gradoni, o due chiostri rosso acceso
ESCLUSI = {3001, 3018, 497, 523, 617, 3085, 575, 576}
ROTAZIONE_MAX = 12            # gradi: un tetto a falde girato di più avrebbe la luce sbagliata (un tetto piano si gira come si vuole)
SCALA_MIN, SCALA_MAX = 0.8, 1.25
USI_MAX = 4


def tetto_piano(foto, poly):
    """Un tetto piano (grigio o bianco, senza falde): girato non cambia la luce. Un tetto di coppi o con due metà di luce diversa
    (le falde) no."""
    x0, y0, x1, y1 = poly.bounds
    a = foto.rgb(x0, y0, x1, y1, originale=True).astype(np.int16)
    h, w = a.shape[:2]
    m = np.zeros((h, w), np.uint8)
    PXf = 1.2
    cv2.fillPoly(m, [np.array([((x - x0) * PXf, (y - y0) * PXf) for x, y in poly.exterior.coords], np.int32)], 1)
    m = cv2.erode(m, np.ones((3, 3), np.uint8))
    if m.sum() < 20:
        return False
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    rosso = ((r > g + 30) & (r > b + 40))[m > 0].mean()
    if rosso > 0.2:
        return False
    lum = a.mean(2)
    c = poly.centroid
    rr = poly.minimum_rotated_rectangle
    q = list(rr.exterior.coords)
    lati = [(math.dist(q[i], q[i + 1]), q[i], q[i + 1]) for i in range(2)]
    for _, p0, p1 in lati:                              # le due metà, divise lungo ciascun asse
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        Y, X = np.mgrid[0:h, 0:w]
        lato = ((X / PXf + x0 - c.x) * dy - (Y / PXf + y0 - c.y) * dx) > 0
        m1, m2 = (m > 0) & lato, (m > 0) & ~lato
        if m1.sum() > 10 and m2.sum() > 10 and abs(lum[m1].mean() - lum[m2].mean()) > 14:
            return False
    return True


class Insediatore:
    """Mette i gruppi di edifici nuovi (un gruppo = un insediamento) nei lotti, uno alla volta."""

    def __init__(self, foto, lotto_poly, bloccati_di, donatori):
        # bloccati_di(lotto, pool) -> (profilo, geometria dei luoghi mappati che un insediamento non può coprire)
        self.foto = foto
        self.strade = Strade(g for g in lotto_poly.values() if g is not None)
        self.lotto_poly = lotto_poly
        self.bloccati_di = bloccati_di
        self.donatori = donatori
        for ds in donatori.values():
            for d in ds:
                c = d['poly'].centroid
                d['g'] = affinity.translate(d['poly'], -c.x, -c.y)
                d['piano'] = tetto_piano(foto, d['poly'])
                q = affinity.rotate(d['poly'], -d['ang'], origin=c)
                x0, y0, x1, y1 = q.bounds
                d['ingombro'] = (x1 - x0) * (y1 - y0) / d['poly'].area      # 1: un rettangolo pieno; di più: a L, a U, a corte
        self.griglie = collections.OrderedDict()
        self._spazio = {}
        self.scuole = []                                 # (x, y, livello) delle scuole nuove già messe
        self.aziende = []                                # (x, y) delle aziende agricole nuove
        self.nuovi = []                                  # gli insediamenti già messi (poligoni)
        self.usati = collections.Counter()
        self.piazzati = []

    def griglia(self, lotto, ang, pool):
        profilo, bl = self.bloccati_di(lotto, pool)
        chiave = (lotto, round(ang, 1), profilo)
        if chiave in self.griglie:
            self.griglie.move_to_end(chiave)
            return self.griglie[chiave]
        lp = self.lotto_poly[lotto]
        vicini = [q for q in self.nuovi if q.distance(lp) < MARGINE_GRIGLIA + 5]
        if vicini:
            bl = shapely.union_all([bl] + vicini)
        g = Griglia(self.foto, self.strade, lp, ang, bl)
        self.griglie[chiave] = g
        if len(self.griglie) > 60:
            self.griglie.popitem(last=False)
        return g

    def spazio(self, lotto):
        """I m² di terreno libero (prato, campi, terra) del lotto lontani dai tetti, campionati ogni 4 m."""
        if lotto not in self._spazio:
            lp = self.lotto_poly[lotto]
            x0, y0, x1, y1 = lp.bounds
            X, Y = np.meshgrid(np.arange(x0 + 2, x1, 4.0), np.arange(y0 + 2, y1, 4.0))
            d = shapely.contains_xy(lp, X, Y)
            ok = d & self.foto.libero_array(X, Y) & ~self.foto.campiona('case', X, Y)
            self._spazio[lotto] = float(ok.sum()) * 16
        return self._spazio[lotto] - sum(q.intersection(self.lotto_poly[lotto]).area for q in self.nuovi
                                         if q.intersects(self.lotto_poly[lotto]))

    def occupa(self, poly):
        self.nuovi.append(poly)
        for g in self.griglie.values():
            if g.lp.distance(poly) < MARGINE_GRIGLIA + 5:
                g.occupa(poly)

    def candidati(self, pool):
        """I modelli per un tipo di edificio. Un supermercato di quartiere (600-1000 m²) è un edificio basso a tetto piano come
        quelli pubblici e per uffici: i supermercati della foto sono ipermercati."""
        if pool == 'supermercato':
            return self.donatori.get('supermercato', []) + [d for d in self.donatori.get('scuola', []) if d['piano'] and 450 <= d['area'] <= 1600]
        return self.donatori.get(pool, [])

    def scegli(self, pool, aree, ang, bersaglio, escludi=frozenset()):
        scelti, totale = [], 0.0
        for area in aree:
            best = None
            for d in self.candidati(pool):
                if d['id'] in ESCLUSI or d['id'] in escludi or any(d['id'] == s['d']['id'] for s in scelti):
                    continue
                rot = ((ang - d['ang'] + 45) % 90) - 45
                if not d['piano'] and abs(rot) > ROTAZIONE_MAX:
                    continue
                sc = min(SCALA_MAX, max(SCALA_MIN, math.sqrt(area / d['area'])))
                vicino = min([math.hypot(x - bersaglio[0], y - bersaglio[1]) for i, x, y in self.piazzati if i == d['id']] or [1e9])
                costo = ((abs(rot) / 45 * 0.4) if d['piano'] else (abs(rot) / ROTAZIONE_MAX * 0.5)) \
                    + 3 * abs(math.log(d['area'] * sc * sc / area)) + 1.5 * self.usati[d['id']] \
                    + (20 if self.usati[d['id']] >= USI_MAX else 0) + (6 if vicino < 400 else 1.5 if vicino < 1500 else 0) \
                    + 8 * max(0.0, d['ingombro'] - 1.1) \
                    - (1.5 if pool == 'scuola' and re.match(r'^(Scuola|Asilo|Liceo|Istituto|Polo scolastico|Aule)', d['nome']) else 0)
                if best is None or (costo, d['id']) < (best['costo'], best['d']['id']):
                    g0 = affinity.scale(affinity.rotate(d['g'], rot, origin=(0, 0)), sc, sc, origin=(0, 0))
                    best = {'d': d, 'rot': rot, 'sc': sc, 'g0': g0, 'costo': costo}
            if best is None:
                return None
            scelti.append(best)
            totale += best['costo']
        return scelti, totale

    def piazza(self, tipo, pool, nome, aree, bersaglio, lotti, angoli, raggio, entro=None):
        """Il posto migliore per un insediamento: un dizionario con lotto, telaio, edifici ed elementi, o None."""
        d_case0, d_altro = DISTANZA_CASE[pool], DISTANZA_ALTRO[pool]
        bp = Point(bersaglio)
        livello = next((s for s in SCUOLA_PARCHEGGIO if nome.startswith(s)), None) if tipo == 'scuola' else None
        if tipo == 'scuola':                            # due scuole dello stesso grado non stanno una accanto all'altra
            vicini = [(x, y, 350.0 if l == livello else 60.0, 400.0 if l == livello else 150.0) for x, y, l in self.scuole]
        elif tipo in ('agricolo', 'fabbrica'):          # né due aziende agricole con le loro strade parallele
            vicini = [(x, y, 180.0, 160.0) for x, y in self.aziende]
        else:
            vicini = []
        ordinati = sorted(lotti, key=lambda n: self.lotto_poly[n].distance(bp))
        scarti = collections.defaultdict(list)
        for f_case, alb_max, f_raggio in GRADI:
            lim = None if f_raggio is None else raggio * f_raggio
            for _ in range(4):                              # se la verifica esatta scarta il posto, si cerca ancora
                migliore = None
                for lotto in ordinati:
                    dl = self.lotto_poly[lotto].distance(bp)
                    if (lim is not None and dl > lim) or (migliore is not None and dl > migliore[0]):
                        break
                    if self.spazio(lotto) < 0.6 * sum(aree) * {'negozi': 6, 'scuola': 4, 'supermercato': 5}.get(tipo, 3):
                        continue
                    for ang in angoli(lotto):
                        combinazioni = [self.scegli(pool, aree, ang, bersaglio)]
                        if entro is not None and combinazioni[0]:
                            # messo a mano: anche altri modelli, se con i primi l'insediamento non entra nel posto voluto
                            usati = set()
                            for _ in range(4):
                                usati |= {m['d']['id'] for m in combinazioni[-1][0]}
                                altra = self.scegli(pool, aree, ang, bersaglio, frozenset(usati))
                                if not altra:
                                    break
                                combinazioni.append(altra)
                        for ci, sc in enumerate(combinazioni):
                            if not sc:
                                continue
                            modelli, costo_m = sc
                            g = self.griglia(lotto, ang, pool)
                            for k in range(4):
                                dims = [_dimensioni(m, k % 2, ang) for m in modelli]
                                for vi, disp in enumerate(varianti(tipo, nome, dims, 20 * costo_m)):
                                    res = cerca(g, disp, k, bersaglio, d_case0 * f_case, d_altro, alb_max,
                                                scarti[(lotto, round(ang, 1), k, vi, ci)], vicini, entro,
                                                4.0 if entro is not None else 0.0)
                                    if res and (migliore is None or res[0] < migliore[0]):
                                        migliore = (res[0], lotto, ang, k, (vi, ci), disp, modelli, res, pool)
                if migliore is None:
                    break
                esito = self._verifica(migliore)
                if esito:
                    esito['grado'] = (f_case, alb_max)
                    c0 = esito['edifici'][0][0].centroid
                    if livello:
                        self.scuole.append((c0.x, c0.y, livello))
                    if tipo in ('agricolo', 'fabbrica'):
                        self.aziende.append((c0.x, c0.y))
                    return esito
                _, lotto, ang, k, (vi, ci), _, _, res, _ = migliore
                r, c = res[1], res[2]
                scarti[(lotto, round(ang, 1), k, vi, ci)] += [(r + dr, c + dc) for dr in range(-4, 5) for dc in range(-4, 5)]
        return None

    def _verifica(self, m):
        """La verifica esatta del posto scelto sulla griglia: gli edifici sul terreno libero della foto, senza tetti."""
        punteggio, lotto, ang, k, vi, disp, modelli, res, pool = m
        g = self.griglia(lotto, ang, pool)
        _, r, c, info = res
        o, eu, ev = telaio(g, k, r, c)
        edifici = []
        for e in disp.elementi:
            if e.tipo != 'edificio':
                continue
            mo = modelli[e.edificio]
            g0 = mo['g0']
            pts = np.array(g0.exterior.coords)
            pu, pv = pts @ eu, pts @ ev
            buc, bvc = (pu.min() + pu.max()) / 2, (pv.min() + pv.max()) / 2
            centro = o + (e.u0 + e.w / 2) * eu + (e.v0 + e.h / 2) * ev
            t = centro - (buc * eu + bvc * ev)
            poly = affinity.translate(g0, t[0], t[1])
            x0, y0, x1, y1 = poly.bounds
            X, Y = np.meshgrid(np.arange(x0 + 0.5, x1, 1.0), np.arange(y0 + 0.5, y1, 1.0))
            dentro = shapely.contains_xy(poly, X, Y)
            X, Y = X[dentro], Y[dentro]
            if len(X) and (self.foto.libero_array(X, Y).mean() < 0.9 or self.foto.campiona('case', X, Y).mean() > 0.02):
                return None
            edifici.append((poly, mo))
        elementi = [(e.tipo, (e.u0, e.v0, e.u0 + e.w, e.v0 + e.h)) for e in disp.elementi if e.tipo not in ('edificio', 'margine')]
        for i, (u0, w) in enumerate(disp.ingressi):
            v_str = accesso(g, k, r, c, u0, w, 0)
            if disp.pista is not None and (u0, w) == disp.pista:
                elementi.append(('strada', (u0, v_str, u0 + w, 2.5)))
            elif disp.tipo == 'scuola' and i == 1:
                elementi.append(('vialetto', (u0, v_str, u0 + w, VERDE_STRADA + 0.5)))
            else:
                elementi.append(('accesso', (u0, v_str, u0 + w, VERDE_STRADA + MODULO / 2 + 1)))
        sito = shapely.union_all([rettangolo(o, eu, ev, *rc) for _, rc in elementi] + [p for p, _ in edifici])
        margine = rettangolo(o, eu, ev, 0, 0, disp.W, disp.H)
        for p, mo in edifici:
            self.usati[mo['d']['id']] += 1
            c0 = p.centroid
            self.piazzati.append((mo['d']['id'], c0.x, c0.y))
        self.occupa(shapely.union_all([sito, margine]).buffer(2))
        return {'lotto': lotto, 'k': k, 'o': o, 'eu': eu, 'ev': ev, 'edifici': edifici, 'elementi': elementi, 'punteggio': punteggio,
                'info': info, 'W': disp.W, 'H': disp.H}
