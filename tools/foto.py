# Il satellite come terreno: dove un nuovo edificio ci sta (prato, campo, terra) e dove no (asfalto, tetti, auto, acqua), e dove
# sono i tetti che la foto ha già. Lo usa tools/perimetri.py. Guarda le immagini di backup/base/tiles (satellite senza i tetti dei
# nuovi edifici: vedi tools/disegna_satellite.py, SENZA_NUOVI=1), altrimenti quelle originali di backup/tiles_originali.
import collections, json, math, os
import cv2
import numpy as np
import shapely
from PIL import Image
from shapely.geometry import Polygon

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
PX = 1.2                          # pixel per metro delle immagini
TETTO_MIN_M2 = 120                # un tetto più piccolo di così non è un edificio da mappare


def libero_rgb(a):
    """Prato, alberi, campi e terra nudo (a: immagine RGB). Non è libero l'asfalto, il pavimento chiaro, i tetti, le auto, l'acqua."""
    a = a.astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    verde = (g >= r + 3) & (g >= b + 8)
    terra = (np.abs(r - g) <= 28) & (g - b >= 12) & (r >= 110) & (g >= 100)
    return verde | terra


def tetto_rgb(a):
    """Tetti grigi chiari o bianchi e tetti di mattone."""
    a = a.astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    lum = a.mean(2)
    sat = a.max(2) - a.min(2)
    return ((lum > 135) & (sat < 16)) | ((lum > 185) & (sat < 28)) | ((r > g + 30) & (r > b + 40))


class Foto:
    def __init__(self):
        self.world = json.load(open(os.path.join(ROOT, 'public', 'data', 'world.json')))
        base = os.path.join(ROOT, 'backup', 'base')
        self.cartella = base if os.path.isdir(os.path.join(base, 'tiles')) else os.path.join(ROOT, 'backup', 'tiles_originali')
        self.disponibile = os.path.isdir(self.cartella)
        self._maschere = {}
        self._immagini = collections.OrderedDict()

    def _percorso(self, t):
        nome = os.path.basename(t['file'])
        p = os.path.join(self.cartella, 'tiles', nome)
        return p if os.path.exists(p) else os.path.join(self.cartella, nome)

    def _immagine(self, t):
        f = t['file']
        if f not in self._immagini:
            self._immagini[f] = np.array(Image.open(self._percorso(t)).convert('RGB'))
            if len(self._immagini) > 6:
                self._immagini.popitem(last=False)
        return self._immagini[f]

    def _originale(self, t):
        """L'immagine della foto di base, senza nessun disegno (backup/tiles_originali)."""
        f = 'orig:' + t['file']
        if f not in self._immagini:
            self._immagini[f] = np.array(Image.open(os.path.join(ROOT, 'backup', 'tiles_originali', os.path.basename(t['file']))).convert('RGB'))
            if len(self._immagini) > 6:
                self._immagini.popitem(last=False)
        return self._immagini[f]

    def ritoccato(self, poly):
        """Differenza media (0-255) tra la foto di base e quella con i disegni dentro un poligono: un luogo disegnato non è una foto
        vera e non si usa come modello."""
        x0, y0, x1, y1 = poly.bounds
        a = self.rgb(x0, y0, x1, y1).astype(np.int16)
        b = self.rgb(x0, y0, x1, y1, originale=True).astype(np.int16)
        m = np.zeros(a.shape[:2], np.uint8)
        cv2.fillPoly(m, [np.array([((x - x0) * PX, (y - y0) * PX) for x, y in poly.exterior.coords], np.int32)], 1)
        return float(np.abs(a - b).mean(2)[m > 0].mean()) if m.any() else 0.0

    def tetto_e_intorno(self, poly, anello=4.0):
        """Quanta parte del poligono è tetto, quanta è prato, e quanta dell'anello intorno è tetto (un tetto attaccato ad altri
        tetti è un pezzo di un edificio più grande, non un edificio a sé)."""
        g = poly.buffer(anello)
        x0, y0, x1, y1 = g.bounds
        a = self.rgb(x0, y0, x1, y1)
        h, w = a.shape[:2]

        def maschera(geom):
            m = np.zeros((h, w), np.uint8)
            cv2.fillPoly(m, [np.array([((x - x0) * PX, (y - y0) * PX) for x, y in geom.exterior.coords], np.int32)], 1)
            return m > 0
        dentro = maschera(poly)
        intorno = maschera(g) & ~maschera(poly.buffer(1.0))
        t, l = tetto_rgb(a), libero_rgb(a)
        return (float(t[dentro].mean()) if dentro.any() else 0.0, float(l[dentro].mean()) if dentro.any() else 0.0,
                float(t[intorno].mean()) if intorno.any() else 0.0)

    def _maschera(self, t):
        f = t['file']
        if f not in self._maschere:
            self._maschere[f] = libero_rgb(np.array(Image.open(self._percorso(t)).convert('RGB')))
        return self._maschere[f]

    # ------------------------------------------------------------ terreno libero
    def libero_array(self, X, Y):
        """Per ogni punto (metri) se è su prato o terra nella foto; fuori dalle immagini non lo è."""
        out = np.zeros(X.shape, dtype=bool)
        for t in self.world['tiles']:                      # le immagini dopo coprono quelle prima
            dentro = (X >= t['x']) & (X < t['x'] + t['size']) & (Y >= t['y']) & (Y < t['y'] + t['size'])
            if not dentro.any():
                continue
            m = self._maschera(t)
            i = np.clip(((X[dentro] - t['x']) * PX).astype(int), 0, m.shape[1] - 1)
            j = np.clip(((Y[dentro] - t['y']) * PX).astype(int), 0, m.shape[0] - 1)
            out[dentro] = m[j, i]
        return out

    def _maschera_tetti(self, t):
        f = 'tetti:' + t['file']
        if f not in self._maschere:
            a = np.array(Image.open(self._percorso(t)).convert('RGB'))
            r, g, b = (a[..., k].astype(np.int16) for k in range(3))
            acqua = (b > r + 15) & (b > g + 5)          # piscine, laghetti e campi da gioco blu: da qui si sta lontani
            lum = a.astype(np.int16).mean(2)
            sat = a.max(2).astype(np.int16) - a.min(2)
            vialetti = (lum > 170) & (sat < 55)         # vialetti dei parchi, ghiaia, piazzali chiari
            self._maschere[f] = tetto_rgb(a) | acqua | vialetti
        return self._maschere[f]

    def tetto_array(self, X, Y):
        """Per ogni punto (metri) se nella foto c'è un tetto, una riga bianca (le linee di un campo sportivo) o acqua e campi blu."""
        out = np.zeros(X.shape, dtype=bool)
        for t in self.world['tiles']:
            dentro = (X >= t['x']) & (X < t['x'] + t['size']) & (Y >= t['y']) & (Y < t['y'] + t['size'])
            if not dentro.any():
                continue
            m = self._maschera_tetti(t)
            i = np.clip(((X[dentro] - t['x']) * PX).astype(int), 0, m.shape[1] - 1)
            j = np.clip(((Y[dentro] - t['y']) * PX).astype(int), 0, m.shape[0] - 1)
            out[dentro] = m[j, i]
        return out

    def _maschera_di(self, nome, t):
        """Le maschere per gli insediamenti dei nuovi edifici (tools/siti.py), sull'immagine di base: 'case' (i tetti), 'alberi'
        (chiome scure), 'acqua' (piscine, laghetti, campi blu), 'scuro' (ombre profonde), 'asfalto' (strade, piazzali), 'vialetti' (percorsi chiari, ghiaia dei parchi)."""
        f = nome + ':' + t['file']
        if f not in self._maschere:
            a = np.array(Image.open(self._percorso(t)).convert('RGB'))
            r, g, b = (a[..., k].astype(np.int16) for k in range(3))
            lum = a.astype(np.int16).mean(2)
            sat = a.max(2).astype(np.int16) - a.min(2)
            if nome == 'case':
                m = tetto_rgb(a)
            elif nome == 'alberi':
                scuro = ((g >= r + 3) & (g >= b + 6) & (lum < 72)).astype(np.float32)
                k = max(3, int(3 * PX) | 1)                 # una chioma: tanti pixel verde scuro in 3 m
                m = cv2.blur(scuro, (k, k)) >= 0.3
            elif nome == 'acqua':
                m = (b > r + 15) & (b > g + 5)
            elif nome == 'scuro':                       # ombre lunghe dei palazzi alti, sottobosco: niente edifici nuovi lì sopra
                m = lum < 58
            elif nome == 'asfalto':                     # grigio; non le fasce della massicciata dei binari, più calde (b - r ≈ -20),
                # né i canali, grigio-verdi (g - r ≈ 14)
                caldo = ((b - r < -13) & (sat < 40) & (lum > 50) & (lum < 160)).astype(np.float32)
                verdastro = ((g - r >= 8) & (g - b >= 10) & (lum < 125)).astype(np.float32)
                k = int(5 * PX) | 1
                m = ((sat < 26) & (lum > 50) & (lum < 150) & ~(cv2.blur(caldo, (k, k)) > 0.45)
                     & ~(cv2.blur(verdastro, (k, k)) > 0.45))
            else:
                m = (lum > 170) & (sat < 55) & ~tetto_rgb(a)
            self._maschere[f] = m
        return self._maschere[f]

    def campiona(self, nome, X, Y):
        """Per ogni punto (metri) il valore della maschera `nome` (vedi _maschera_di); fuori dalle immagini False."""
        out = np.zeros(X.shape, dtype=bool)
        for t in self.world['tiles']:
            dentro = (X >= t['x']) & (X < t['x'] + t['size']) & (Y >= t['y']) & (Y < t['y'] + t['size'])
            if not dentro.any():
                continue
            m = self._maschera_di(nome, t)
            i = np.clip(((X[dentro] - t['x']) * PX).astype(int), 0, m.shape[1] - 1)
            j = np.clip(((Y[dentro] - t['y']) * PX).astype(int), 0, m.shape[0] - 1)
            out[dentro] = m[j, i]
        return out

    def tetti_dentro(self, poly, passo=0.8):
        """La parte di un poligono in cui la foto ha un tetto o una riga bianca (campionata ogni `passo` metri)."""
        x0, y0, x1, y1 = poly.bounds
        X, Y = np.meshgrid(np.arange(x0 + passo / 2, x1, passo), np.arange(y0 + passo / 2, y1, passo))
        dentro = shapely.contains_xy(poly, X, Y)
        if not dentro.any():
            return 0.0
        return float(self.tetto_array(X[dentro], Y[dentro]).mean())

    def frazione(self, poly, n=9, m=6):
        """La parte di un poligono che sta su terreno libero, campionata su una griglia nel suo rettangolo orientato."""
        c = list(poly.minimum_rotated_rectangle.exterior.coords)
        ox, oy = c[0]
        ux, uy = c[1][0] - ox, c[1][1] - oy
        vx, vy = c[3][0] - ox, c[3][1] - oy
        a = (np.arange(n) + 0.5) / n
        b = (np.arange(m) + 0.5) / m
        A, B = np.meshgrid(a, b)
        return float(self.libero_array(ox + ux * A + vx * B, oy + uy * A + vy * B).mean())

    # ------------------------------------------------------------ tetti
    def rgb(self, x0, y0, x1, y1, originale=False):
        """Un ritaglio della foto (in coordinate metri) alla risoluzione delle immagini."""
        w, h = int(math.ceil((x1 - x0) * PX)), int(math.ceil((y1 - y0) * PX))
        out = np.zeros((h, w, 3), np.uint8)
        for t in self.world['tiles']:
            ox0, oy0 = max(x0, t['x']), max(y0, t['y'])
            ox1, oy1 = min(x1, t['x'] + t['size']), min(y1, t['y'] + t['size'])
            if ox0 >= ox1 or oy0 >= oy1:
                continue
            im = self._originale(t) if originale else self._immagine(t)
            si, sj = int((ox0 - t['x']) * PX), int((oy0 - t['y']) * PX)
            di, dj = int((ox0 - x0) * PX), int((oy0 - y0) * PX)
            ww = min(int((ox1 - ox0) * PX), im.shape[1] - si, w - di)
            hh = min(int((oy1 - oy0) * PX), im.shape[0] - sj, h - dj)
            if ww > 0 and hh > 0:
                out[dj:dj + hh, di:di + ww] = im[sj:sj + hh, si:si + ww]
        return out

    def tetti(self, lotto, esclusi=None):
        """I tetti che la foto ha dentro un lotto e che nessun luogo mappato copre già: poligoni (rettangoli orientati se la forma
        è compatta, altrimenti la sagoma semplificata). `lotto` e `esclusi` sono geometrie shapely."""
        x0, y0, x1, y1 = lotto.bounds
        a = self.rgb(x0, y0, x1, y1)
        h, w = a.shape[:2]
        roof = tetto_rgb(a).astype(np.uint8)

        def maschera(geom):
            m = np.zeros((h, w), np.uint8)
            for g in getattr(geom, 'geoms', [geom]):
                if g.is_empty or g.geom_type != 'Polygon':
                    continue
                cv2.fillPoly(m, [np.array([((x - x0) * PX, (y - y0) * PX) for x, y in g.exterior.coords], np.int32)], 1)
            return m

        roof &= maschera(lotto.buffer(-1))
        if esclusi is not None and not esclusi.is_empty:
            roof &= (1 - maschera(esclusi.buffer(2)))
        roof = cv2.morphologyEx(roof, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))      # niente marciapiedi e strisce sottili
        roof = cv2.morphologyEx(roof, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
        n, lab, stat, _ = cv2.connectedComponentsWithStats(roof)
        out = []
        for k in range(1, n):
            if stat[k, cv2.CC_STAT_AREA] < TETTO_MIN_M2 * PX * PX:
                continue
            cont, _ = cv2.findContours((lab == k).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            c = max(cont, key=cv2.contourArea)
            c = cv2.approxPolyDP(c, 2.0, True)[:, 0, :]
            if len(c) < 3:
                continue
            p = Polygon([(x0 + px / PX, y0 + py / PX) for px, py in c]).buffer(0)
            if p.is_empty or p.geom_type != 'Polygon':
                continue
            r = p.minimum_rotated_rectangle
            if p.area < 0.65 * p.convex_hull.area or p.area > 6000:         # anelli di marciapiede, piazzali: non sono edifici
                continue
            if p.area >= 0.82 * r.area:
                p = r
            if p.area >= TETTO_MIN_M2:
                out.append(p)
        return out
