# I materiali degli insediamenti dei nuovi edifici (tools/siti.py), presi dalla foto di base (backup/tiles_originali): parcheggi veri
# con le loro file di auto, asfalto, pavimentazione chiara, ghiaia delle aie, siepi. Li usa tools/disegna_satellite.py: ogni
# parcheggio, accesso, marciapiede o aia nuova è un pezzo di foto vera, girato e ritagliato sulla sua forma.
import numpy as np

# Parcheggi a pettine della foto: (nome, x0, x1, y0, y1, asse delle file). Le file di auto corrono lungo l'asse; attraverso le file
# si alternano doppie file di auto (schiena contro schiena, spesso con alberi in mezzo) e corsie.
PARCHEGGI = [
    ('A', 1745, 1875, 4245, 4370, 'x'),
    ('B', 1736, 1820, 3276, 3392, 'x'),
    ('C', 3512, 3628, 3998, 4068, 'x'),
    ('D', 4128, 4200, 812, 868, 'x'),
    ('E', 1838, 1905, 3560, 3640, 'y'),
    ('F', 1648, 1712, 3664, 3722, 'x'),
]
# Finestre di materiale uniforme: (centro x, centro y, mezzo lato) in metri
MATERIALI = {
    'asfalto': [(5701, 690, 10), (1566, 5170, 10), (1694, 5285, 10), (1756, 3743, 10), (1473, 5069, 10), (1693, 3415, 10)],
    'chiaro': [(2533, 2865, 10), (2601, 2868, 10), (2582, 2436, 10), (2412, 2468, 10), (-177, 3849, 10), (-467, 3786, 10)],
    'ghiaia': [(3847, -1440, 9), (622, -660, 9)],
    # cemento dei piazzali industriali (il piazzale dei capannoni del lotto 294): le corsie tra i corpi dei capannoni divisi
    'cemento': [(1488, 2564, 7), (1498, 2606, 7)],
    # prati con alberi sparsi (giardini delle scuole)
    'prato': [(-645, 4759, 11), (-681, -250, 11), (2042, 316, 11), (-514, -380, 11)],
}
# Campetti da basket veri (centro approssimato): il campo blu si ritrova nella foto (la macchia blu più grande lì intorno)
CAMPI = [(4454.6, 142.9), (5288.3, 510.1), (5334.6, 510.4), (374.6, 2261.2)]
# Bordi d'aia veri: una fila di arbusti tra la ghiaia (dentro) e il prato (fuori). (x della fila, y0, y1): la fila corre lungo y,
# la ghiaia sta a x minori
SIEPI = [(3910, -1450, -1370)]
PX = 1.2


def profilo(a, asse):
    """Quanto ogni riga (attraverso le file) non è asfalto: auto, alberi, aiuole."""
    a = a.astype(np.int16)
    lum = a.mean(2)
    sat = a.max(2) - a.min(2)
    asf = (sat < 22) & (lum > 60) & (lum < 140)
    non = 1.0 - asf
    p = non.mean(1) if asse == 'x' else non.mean(0)
    k = np.ones(3) / 3
    return np.convolve(p, k, mode='same')


def cuciture(a, asse, v0):
    """Le linee lungo le file dove si può tagliare un parcheggio senza tagliare auto: il centro di una doppia fila (tra le due file
    schiena contro schiena) o il bordo esterno di una fila singola al margine. `a`: il ritaglio (righe = y), `v0`: la coordinata
    (metri) del suo primo pixel attraverso le file. Restituisce i metri."""
    p = profilo(a, asse)
    fasce = []
    dentro, inizio = False, 0
    for i, v in enumerate(list(p) + [0.0]):
        if v > 0.2 and not dentro:
            dentro, inizio = True, i
        elif v <= 0.2 and dentro:
            dentro = False
            if i - inizio >= 3:
                fasce.append((inizio, i))
    # fasce vicine (un'auto mancante) si uniscono
    unite = []
    for f in fasce:
        if unite and f[0] - unite[-1][1] <= 2:
            unite[-1] = (unite[-1][0], f[1])
        else:
            unite.append(f)
    out = []
    for j, (s, e) in enumerate(unite):
        largh = (e - s) / PX
        if largh >= 8.0:
            out.append(v0 + (s + e) / 2 / PX)
        elif j == 0:
            out.append(v0 + s / PX)
        elif j == len(unite) - 1:
            out.append(v0 + e / PX)
    return out


def campo(a, x0, y0):
    """Il campo blu in un ritaglio `a` (righe = y) che comincia in (x0, y0): (centro, asse lungo, lunghezza, larghezza) in metri."""
    import cv2
    r, g, b = (a[..., k].astype(np.int16) for k in range(3))
    m = ((b > r + 20) & (b > g)).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    h, w = m.shape
    k = lab[h // 2, w // 2] or (1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA])))
    cont, _ = cv2.findContours((lab == k).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    pts = max(cont, key=cv2.contourArea)[:, 0, :].astype(np.float64)
    pts = np.column_stack([x0 + pts[:, 0] / PX, y0 + pts[:, 1] / PX])
    c = pts.mean(0)
    u, s, vt = np.linalg.svd(pts - c, full_matrices=False)
    asse = vt[0]
    lungo = np.ptp((pts - c) @ asse)
    largo = np.ptp((pts - c) @ np.array([-asse[1], asse[0]]))
    return c, asse, lungo, largo


def moduli(cuc, n=1):
    """Coppie di cuciture distanti n moduli (13-20 m l'uno): (inizio, fine)."""
    out = []
    for i in range(len(cuc) - n):
        d = cuc[i + n] - cuc[i]
        if 13 * n <= d <= 20 * n and all(13 <= cuc[i + j + 1] - cuc[i + j] <= 20 for j in range(n)):
            out.append((cuc[i], cuc[i + n]))
    return out
