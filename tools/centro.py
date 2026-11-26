# Il Centro: 40 edifici da 4 a 15 piani, ognuno con la destinazione d'uso di ogni piano.
#
#   python3 tools/centro.py          scrive i contorni degli edifici del Centro in places.json e gli abitanti in lots.json
#                                    e quarters.json; poi si lanciano tools/censimento.py e tools/disegna_satellite.py
#   python3 tools/centro.py --prova  stampa edificio per edificio misure, abitanti e posti di lavoro, senza scrivere nulla
#
# PROGRAMMA dice cosa c'è in ogni edificio, piano per piano (dal piano terra, 0, in su), che impianto ha e com'è fatto
# (facciata e tetto, disegnati da tools/disegna_centro.py). Gli edifici sono isolati a filo del marciapiede che seguono la
# forma del lotto, come nei centri delle città: una manica di 12 m lungo le strade attorno a una corte, divisa in più
# corpi accostati di altezze, facciate e tetti diversi; oppure un blocco pieno; oppure una torre su un podio.
# Superfici, abitanti e posti di lavoro si calcolano dai coefficienti; gli uffici in affitto si dividono in aziende.
import json, math, os, random, re, sys

from shapely.geometry import LineString, Point, Polygon, box
from shapely import affinity
from shapely.ops import split, unary_union

ROOT = os.path.join(os.path.dirname(__file__), '..')
DATA = os.path.join(ROOT, 'public', 'data')
C0 = (1720.0, 800.0)              # centro di Piazza Grande
ALTEZZA_PIANO = 3.5               # metri
PROSPETTIVA = 0.27                # la foto è presa un po' da sud: un tetto alto h metri si vede spostato a nord di h × 0,27
STRADA = 5.0                      # i lotti arrivano a metà delle strade interne: mezza carreggiata (m)
MARCIAPIEDE = 3.0                 # gli edifici stanno a filo del marciapiede (m)
MANICA = 12.0                     # profondità dei corpi di fabbrica attorno alla corte (m)
CORPO = (26, 42)                  # lunghezza dei corpi di fabbrica in cui si divide un isolato (da, a, in metri)
TORRE = (30, 30)                  # misura massima del fusto di una torre (m)

# ------------------------------------------------------------------ coefficienti (valori medi italiani ed europei)
CASA = {'m2_per_alloggio': 85, 'alloggi_sfitti': 0.07, 'abitanti_per_alloggio': 2.1}
# Per le attività: metri quadri lordi per addetto, quota dei piani occupata, addetti per impresa
# (None = una sola impresa o ente per tutta l'attività, 'aziende' = uffici in affitto divisi in aziende). Il tipo è il
# secondo campo dei piani nel PROGRAMMA.
ATTIVITA = {
    'uffici':           dict(uso='ufficio', m2=20, occupazione=0.88, per_impresa='aziende'),
    'sede':             dict(uso='ufficio', m2=20, occupazione=1.0, per_impresa=None),
    'coworking':        dict(uso='ufficio', m2=12, occupazione=0.85, per_impresa=3),
    'sportelli':        dict(uso='servizio pubblico', m2=25, occupazione=1.0, per_impresa=None),
    'giustizia':        dict(uso='servizio pubblico', m2=35, occupazione=1.0, per_impresa=None),
    'cultura':          dict(uso='servizio pubblico', m2=150, occupazione=1.0, per_impresa=None),
    'biblioteca':       dict(uso='servizio pubblico', m2=120, occupazione=1.0, per_impresa=None),
    'scuola':           dict(uso='servizio pubblico', m2=60, occupazione=1.0, per_impresa=None),
    'negozi':           dict(uso='negozio', m2=45, occupazione=0.93, per_impresa=4),
    'grande_magazzino': dict(uso='negozio', m2=50, occupazione=1.0, per_impresa=None),
    'showroom':         dict(uso='negozio', m2=80, occupazione=1.0, per_impresa=None),
    'ristorante':       dict(uso='negozio', m2=25, occupazione=1.0, per_impresa=None),
    'benessere':        dict(uso='negozio', m2=60, occupazione=1.0, per_impresa=None),
    'hotel':            dict(uso='ricettivo', m2=130, occupazione=1.0, per_impresa=None),
    'osservatorio':     dict(uso='servizio pubblico', m2=150, occupazione=1.0, per_impresa=None),
    'laboratorio':      dict(uso='fabbrica', m2=40, occupazione=0.9, per_impresa='aziende'),
    'associazioni':     dict(uso='servizio pubblico', m2=30, occupazione=0.85, per_impresa='aziende'),
    'sanita':           dict(uso='servizio pubblico', m2=40, occupazione=1.0, per_impresa=None),
    'sicurezza':        dict(uso='servizio pubblico', m2=30, occupazione=1.0, per_impresa=None),
    'cinema':           dict(uso='negozio', m2=120, occupazione=1.0, per_impresa=None),
    'parcheggio':       dict(uso='parcheggio', m2=4000, occupazione=1.0, per_impresa=None),
    'culto':            dict(uso='servizio pubblico', m2=600, occupazione=1.0, per_impresa=None),
    'agricolo':         dict(uso='fabbrica', m2=400, occupazione=1.0, per_impresa=None),
}
M2_PER_STUDENTE = 30              # residenza per studenti: un posto letto ogni 30 m² lordi (camere e spazi comuni)
M2_PER_CAMERA = 45                # camere d'albergo: una ogni 45 m² lordi

# Aziende negli uffici in affitto: classi di dimensione (dipendenti da, a, probabilità) e rami di attività.
# Su un piano stanno le piccole e medie; una grande prende uno o più piani interi.
AZIENDE_PICCOLE = [(4, 12, 0.40), (13, 40, 0.40), (41, 90, 0.20)]
AZIENDA_GRANDE = 0.2              # probabilità che un piano libero vada a un'azienda grande, con 2-4 piani interi
RAMI = ['studio legale', 'studio di commercialisti', 'consulenza aziendale', 'software e servizi informatici',
        'agenzia assicurativa', 'società di ingegneria', "studio di architettura", 'agenzia di marketing',
        'società finanziaria', 'agenzia immobiliare', 'selezione del personale', 'studio notarile',
        'società di revisione', 'telecomunicazioni', 'energia', 'sede amministrativa di un gruppo logistico',
        'casa editrice', 'agenzia di viaggi']
RAMI_GRANDI = ['software e servizi informatici', 'consulenza aziendale', 'agenzia assicurativa', 'società finanziaria',
               'telecomunicazioni', 'energia', 'società di revisione', 'sede amministrativa di un gruppo logistico']


# ------------------------------------------------------------------ il programma
# lotto, parte del lotto (0 = tutto; 1 e 2 = le due metà, in senso orario attorno alla piazza), nome, categoria della
# mappa, impianto (isolato = corpi attorno a una corte; pieno = senza corte; torre = podio di un piano e torre;
# palazzina = un blocco compatto in mezzo al lotto),
# piani: [(quanti piani, tipo di ATTIVITA o 'casa', cosa c'è)] dal piano terra in su, facciata, tetto.
# Facciate: intonaco_caldo, intonaco_chiaro, mattone, pietra, vetro_blu, vetro_verde, vetro_grigio.
# Tetti (piani, come nei centri delle città): chiaro (membrana bianca), ghiaia, scuro (guaina), solare, verde, piscina,
# eliporto, osservatorio, terrazza, lucernari.
# corte: cosa c'è nella corte (giardino, lastricato, vetrata, cupola); spazio_tetto: uno spazio pubblico sul tetto
# (va nel censimento tra gli spazi aperti); manica: profondità dei corpi, se diversa da MANICA.
# parti: in quanti isolati si divide il lotto (allora `parte` è il numero dell'isolato, da 1); uffici e negozi: le
# imprese che occupano i piani 'uffici' e 'negozi' (e laboratori, associazioni), con i loro nomi (senza, gli uffici si
# dividono in "Azienda 1, 2..."); quello che avanza resta libero;
# luogo: per un edificio che resta com'è (forma 'esistente'), il suo id in places.json; dimensioni: lunghezza e
# profondità massime (m) di una palazzina (forma 'palazzina': un blocco al centro del lotto, con giardino o piazza attorno).
def E(lotto, parte, nome, cat, forma, piani, facciata='pietra', tetto='ghiaia', corte=None, spazio_tetto=None, manica=None,
      parti=None, uffici=None, negozi=None, laboratori=None, associazioni=None, luogo=None, dimensioni=None):
    if corte is None:
        corte = 'giardino' if cat == 'res' else 'lastricato'
    return dict(lotto=lotto, parte=parte, nome=nome, cat=cat, forma=forma, piani=piani, facciata=facciata, tetto=tetto,
                corte=corte, spazio_tetto=spazio_tetto, manica=manica or MANICA, parti=parti, uffici=uffici, negozi=negozi,
                laboratori=laboratori, associazioni=associazioni, luogo=luogo, dimensioni=dimensioni or (46, 24))


def CASA_NEGOZI(n):
    return [(1, 'negozi', 'Negozi e bar'), (n - 1, 'casa', 'Abitazioni')]


def SOLO_CASA(n):
    return [(n, 'casa', 'Abitazioni')]


PROGRAMMA = [
    # ------------------------------------------------ istituzioni e cultura
    E(29, 0, 'Palazzo degli Uffici Pubblici', 'pub', 'torre', [
        (1, 'sportelli', 'Ufficio postale'), (1, 'sportelli', 'Anagrafe e stato civile'),
        (1, 'sportelli', "Centro per l'impiego"), (1, 'sportelli', 'Motorizzazione civile'),
        (1, 'sportelli', 'Agenzia delle entrate'), (1, 'sportelli', 'INPS'), (1, 'sportelli', 'Catasto'),
        (1, 'sportelli', 'Ispettorato del lavoro'), (1, 'sportelli', 'Camera di commercio'),
        (4, 'sportelli', 'Uffici comunali'), (1, 'sportelli', 'Prefettura'),
        (1, 'sportelli', 'Palazzo comunale: sindaco, giunta e sala del consiglio')], 'pietra', 'solare'),
    E(31, 0, 'Palazzo di Giustizia', 'pub', 'isolato', [
        (2, 'giustizia', 'Tribunale: aule delle udienze'), (2, 'giustizia', 'Tribunale: cancellerie e uffici dei giudici')],
      'pietra', 'ghiaia', manica=10),
    E(26, 1, 'Palazzo dei Musei', 'pub', 'isolato', [
        (2, 'cultura', 'Museo civico'), (1, 'cultura', 'Pinacoteca'), (1, 'cultura', 'Museo di storia naturale')],
      'pietra', 'chiaro', corte='cupola'),
    E(34, 0, "Museo d'arte contemporanea", 'pub', 'pieno', [
        (1, 'cultura', 'Centro culturale'), (2, 'cultura', "Museo d'arte contemporanea"),
        (1, 'cultura', "Fondazione per l'arte")], 'intonaco_chiaro', 'verde', spazio_tetto='Giardino pensile pubblico'),
    E(38, 0, 'Biblioteca civica', 'pub', 'isolato', [
        (1, 'biblioteca', 'Biblioteca dei ragazzi'), (3, 'biblioteca', 'Biblioteca civica')], 'mattone', 'lucernari',
      corte='giardino'),
    E(25, 2, 'Conservatorio e Casa della musica', 'pub', 'isolato', [
        (2, 'cultura', 'Casa della musica: auditorium'), (2, 'scuola', 'Conservatorio')], 'mattone', 'scuro'),
    E(13, 0, "Polo dell'impresa", 'uff', 'isolato', [
        (1, 'sportelli', 'Centro servizi per le imprese'), (1, 'scuola', 'Centro di formazione professionale'),
        (1, 'coworking', 'Incubatore di startup'), (1, 'coworking', 'Coworking')], 'vetro_grigio', 'solare',
      manica=10),
    # ------------------------------------------------ uffici
    E(9, 0, 'Grattacielo con osservatorio', 'uff', 'torre', [
        (1, 'negozi', 'Negozi e bar'), (13, 'uffici', 'Uffici'), (1, 'osservatorio', 'Osservatorio panoramico')],
      'vetro_blu', 'osservatorio'),
    E(8, 0, 'Torre per uffici', 'uff', 'torre', [(1, 'negozi', 'Negozi e bar'), (10, 'uffici', 'Uffici')],
      'vetro_verde', 'chiaro'),
    E(10, 0, 'Torre per uffici', 'uff', 'torre', [(1, 'negozi', 'Negozi e bar'), (10, 'uffici', 'Uffici')],
      'vetro_grigio', 'eliporto'),
    E(11, 0, 'Torre per uffici', 'uff', 'torre', [(1, 'negozi', 'Negozi e bar'), (9, 'uffici', 'Uffici')],
      'vetro_blu', 'solare'),
    E(15, 0, 'Torre per uffici', 'uff', 'torre', [(1, 'negozi', 'Negozi e bar'), (10, 'uffici', 'Uffici')],
      'vetro_verde', 'chiaro'),
    E(16, 0, 'Torre per uffici', 'uff', 'torre', [(1, 'negozi', 'Negozi e bar'), (9, 'uffici', 'Uffici')],
      'vetro_grigio', 'ghiaia'),
    E(5, 2, 'Palazzo della Finanza', 'uff', 'isolato', [
        (3, 'sede', 'Sede centrale di una banca'), (1, 'sede', 'Borsa merci')], 'pietra', 'chiaro', corte='vetrata',
      manica=9),
    E(1, 2, 'Palazzo delle Software house', 'uff', 'isolato', [
        (1, 'sede', 'Software house'), (1, 'sede', 'Seconda software house'),
        (1, 'sede', 'Agenzia di comunicazione digitale'), (1, 'sede', 'Agenzia pubblicitaria')], 'vetro_grigio', 'solare',
      manica=10),
    E(20, 0, 'Palazzo per uffici', 'uff', 'isolato', [(1, 'negozi', 'Negozi e bar'), (3, 'uffici', 'Uffici')],
      'vetro_blu', 'chiaro'),
    E(28, 0, 'Palazzo per uffici', 'uff', 'isolato', [(1, 'negozi', 'Negozi e bar'), (3, 'uffici', 'Uffici')],
      'vetro_grigio', 'solare'),
    E(32, 0, 'Palazzo per uffici', 'uff', 'isolato', [(1, 'negozi', 'Negozi e bar'), (3, 'uffici', 'Uffici')],
      'pietra', 'chiaro'),
    # ------------------------------------------------ commercio e alberghi
    E(3, 0, 'Grande magazzino', 'com', 'pieno', [
        (3, 'grande_magazzino', 'Grande magazzino'), (1, 'ristorante', 'Ristorante sul tetto')], 'pietra', 'terrazza'),
    E(4, 0, 'Galleria commerciale', 'com', 'isolato', [
        (3, 'negozi', 'Galleria commerciale'), (1, 'showroom', 'Showroom di design')], 'intonaco_caldo', 'ghiaia',
      corte='vetrata'),
    E(5, 1, 'Hotel Panorama', 'com', 'isolato', [
        (1, 'hotel', 'Ristorante e sale congressi'), (5, 'hotel', 'Hotel Panorama')], 'intonaco_chiaro', 'piscina',
      corte='giardino', manica=10),
    E(7, 0, 'Hotel con piscina', 'com', 'isolato', [(1, 'benessere', 'Spa urbana'), (4, 'hotel', 'Hotel con piscina')],
      'intonaco_chiaro', 'piscina'),
    E(1, 1, 'Hotel e Residence', 'com', 'isolato', [(3, 'hotel', 'Hotel'), (2, 'hotel', 'Residence')], 'intonaco_caldo',
      'piscina', corte='giardino'),
    # ------------------------------------------------ case
    E(2, 0, 'Palazzo residenziale', 'res', 'isolato', SOLO_CASA(5), 'intonaco_caldo', 'ghiaia'),
    E(12, 0, 'Palazzo residenziale', 'res', 'isolato', SOLO_CASA(5), 'mattone', 'scuro'),
    E(14, 0, 'Palazzo residenziale', 'res', 'isolato', CASA_NEGOZI(6), 'intonaco_chiaro', 'solare'),
    E(17, 0, 'Palazzo residenziale', 'res', 'isolato', SOLO_CASA(5), 'intonaco_caldo', 'ghiaia'),
    E(18, 0, 'Palazzo residenziale', 'res', 'isolato', SOLO_CASA(5), 'intonaco_chiaro', 'scuro'),
    E(19, 0, 'Palazzo residenziale', 'res', 'isolato', CASA_NEGOZI(6), 'mattone', 'ghiaia'),
    E(22, 0, 'Palazzo residenziale', 'res', 'isolato', CASA_NEGOZI(6), 'intonaco_caldo', 'ghiaia'),
    E(23, 0, 'Palazzo residenziale', 'res', 'isolato', CASA_NEGOZI(6), 'mattone', 'verde'),
    E(24, 0, 'Palazzo residenziale', 'res', 'isolato', SOLO_CASA(5), 'intonaco_chiaro', 'ghiaia'),
    E(25, 1, 'Palazzo residenziale', 'res', 'isolato', CASA_NEGOZI(6), 'intonaco_caldo', 'scuro'),
    E(26, 2, 'Palazzo residenziale', 'res', 'isolato', SOLO_CASA(5), 'mattone', 'ghiaia'),
    E(27, 0, 'Palazzo residenziale', 'res', 'isolato', CASA_NEGOZI(7), 'intonaco_chiaro', 'chiaro'),
    E(30, 0, 'Palazzo residenziale', 'res', 'isolato', SOLO_CASA(5), 'intonaco_caldo', 'ghiaia'),
    E(33, 0, 'Palazzo residenziale', 'res', 'isolato', CASA_NEGOZI(7), 'mattone', 'solare'),
    E(35, 0, 'Palazzo residenziale', 'res', 'isolato', SOLO_CASA(5), 'intonaco_chiaro', 'ghiaia'),
    E(36, 0, 'Palazzo residenziale', 'res', 'isolato', CASA_NEGOZI(6), 'mattone', 'scuro'),
    E(37, 0, 'Palazzo residenziale', 'res', 'isolato', SOLO_CASA(5), 'intonaco_caldo', 'scuro'),
]

# luoghi del Centro che restano come sono (spazi aperti)
RESTANO = {9, 1724, 1840}          # Piazza Grande, Piazza della Fontana, Parco pubblico
ID_BASE = 2000                     # id dei luoghi dei nuovi edifici in places.json (rilanciando restano gli stessi)


# ------------------------------------------------------------------ geometria
def _coords(path):
    n = list(map(float, re.findall(r'-?\d+\.?\d*', path)))
    return list(zip(n[0::2], n[1::2]))


def poligono(path):
    subs = [Polygon(_coords(s)) for s in re.split(r'[MZ]', path) if len(_coords(s)) >= 3]
    return max(subs, key=lambda p: p.area).buffer(0)


def tangente(c):
    """Direzione delle strade ad anello nel punto c, ridotta tra -45° e 45° (i palazzi seguono la griglia radiale)."""
    a = math.atan2(c[1] - C0[1], c[0] - C0[0]) + math.pi / 2
    while a > math.pi / 4:
        a -= math.pi / 2
    while a <= -math.pi / 4:
        a += math.pi / 2
    return a


def rettangolo(c, w, h, ang):
    r = Polygon([(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)])
    return affinity.translate(affinity.rotate(r, ang, origin=(0, 0), use_radians=True), *c)


def meta(poly):
    """Le due metà del lotto, divise lungo la direzione radiale che passa per il baricentro, in senso orario."""
    c = poly.centroid
    a = math.atan2(c.y - C0[1], c.x - C0[0])
    d = 400
    line = LineString([(c.x - math.cos(a) * d, c.y - math.sin(a) * d), (c.x + math.cos(a) * d, c.y + math.sin(a) * d)])
    parts = sorted(split(poly, line).geoms, key=lambda g: -g.area)[:2]
    rel = lambda g: (math.atan2(g.centroid.y - C0[1], g.centroid.x - C0[0]) - a + math.pi) % (2 * math.pi) - math.pi
    return sorted(parts, key=rel)


_SUOLI = {}


def suolo(n):
    """Il lotto n senza la sua metà delle strade che lo separano dai lotti vicini: la parte da costruire e lastricare."""
    if not _SUOLI:
        lots = [l for l in json.load(open(os.path.join(DATA, 'lots.json'), encoding='utf-8'))]
        polys = {l['number']: poligono(l['path']) for l in lots}
        centro = [k for k, l in zip(polys, lots) if l['quarter'] in ('Centro', 'La Cerchia')]
        for k in centro:
            vicini = [q.buffer(STRADA) for j, q in polys.items() if j != k and q.distance(polys[k]) < 1.0]
            g = polys[k].difference(unary_union(vicini)) if vicini else polys[k]
            _SUOLI[k] = max(getattr(g, 'geoms', [g]), key=lambda x: x.area)
    return _SUOLI[n]


FACCIATE_SIMILI = {              # le facciate dei corpi accostati: varianti vicine a quella dell'edificio
    'pietra': ['pietra', 'intonaco_chiaro', 'intonaco_caldo'],
    'intonaco_chiaro': ['intonaco_chiaro', 'pietra', 'intonaco_caldo'],
    'intonaco_caldo': ['intonaco_caldo', 'pietra', 'mattone'],
    'mattone': ['mattone', 'intonaco_caldo', 'pietra'],
    'vetro_blu': ['vetro_blu', 'vetro_grigio', 'pietra'],
    'vetro_verde': ['vetro_verde', 'vetro_grigio', 'pietra'],
    'vetro_grigio': ['vetro_grigio', 'vetro_blu', 'intonaco_chiaro'],
}
TETTI_COMUNI = ['chiaro', 'chiaro', 'ghiaia', 'ghiaia', 'scuro']


def _principale(g):
    return max((p for p in getattr(g, 'geoms', [g]) if p.geom_type == 'Polygon'), key=lambda p: p.area)


def dividi(area, k):
    """Divide l'area in k isolati di superficie simile, tagliando ogni volta il lato più lungo; tra un isolato e l'altro
    resta il marciapiede di entrambi. In ordine: in senso orario attorno alla piazza, poi dal centro verso fuori."""
    if k <= 1:
        return [area]
    r = area.minimum_rotated_rectangle
    cs = list(r.exterior.coords)
    a, b = (cs[0], cs[1]) if math.dist(cs[0], cs[1]) >= math.dist(cs[1], cs[2]) else (cs[1], cs[2])
    ux, uy = (b[0] - a[0]) / math.dist(a, b), (b[1] - a[1]) / math.dist(a, b)
    k1 = k // 2
    c = area.centroid
    R = math.dist(a, b)

    def taglio(t):
        x, y = c.x + ux * t, c.y + uy * t
        return LineString([(x - uy * R * 2, y + ux * R * 2), (x + uy * R * 2, y - ux * R * 2)])

    lo, hi = -R, R
    for _ in range(30):                                  # la posizione del taglio che lascia k1/k dell'area da un lato
        mid = (lo + hi) / 2
        parts = [g for g in split(area, taglio(mid)).geoms] if area.intersects(taglio(mid)) else [area]
        left = sum(g.area for g in parts if (g.centroid.x - c.x) * ux + (g.centroid.y - c.y) * uy < mid)
        if left < area.area * k1 / k:
            lo = mid
        else:
            hi = mid
    parts = [g for g in split(area, taglio((lo + hi) / 2)).geoms]
    sx = lambda g: (g.centroid.x - c.x) * ux + (g.centroid.y - c.y) * uy
    A = unary_union([g for g in parts if sx(g) < (lo + hi) / 2])
    B = unary_union([g for g in parts if sx(g) >= (lo + hi) / 2])
    out = dividi(_principale(A), k1) + dividi(_principale(B), k - k1)
    ang = lambda g: (math.atan2(g.centroid.y - C0[1], g.centroid.x - C0[0]) + math.pi / 2) % (2 * math.pi)
    return sorted(out, key=lambda g: (round(ang(g), 1), math.dist((g.centroid.x, g.centroid.y), C0)))


def area_edificio(e):
    """Dove sta l'edificio: il suolo del lotto (o il suo isolato), senza gli spazi aperti, meno il marciapiede."""
    places = {p['id']: p for p in json.load(open(os.path.join(DATA, 'places.json'), encoding='utf-8'))
              if p['id'] in e['restano']}
    area = suolo(e['lotto'])
    for pid, p in places.items():
        if pid != 9 and p['lot'] == e['lotto']:
            area = area.difference(poligono(p['path']).buffer(4))
    if e['parti']:
        area = dividi(area, e['parti'])[e['parte'] - 1]
    elif e['parte']:
        area = meta(area)[e['parte'] - 1]
    g = area.buffer(-MARCIAPIEDE, join_style=2)
    return _principale(g).simplify(0.3)


def _corpi(ring, ang, rng):
    """Divide la manica in corpi di fabbrica lunghi 26-42 m con tagli perpendicolari alle strade; i pezzi troppo piccoli
    si uniscono al vicino."""
    (ux, uy), (vx, vy) = (math.cos(ang), math.sin(ang)), (-math.sin(ang), math.cos(ang))
    c = ring.centroid
    x0, y0, x1, y1 = ring.bounds
    R = math.hypot(x1 - x0, y1 - y0)
    pezzi = [ring]
    for (ax, ay), (bx, by) in (((ux, uy), (vx, vy)), ((vx, vy), (ux, uy))):
        k = -R + rng.uniform(0, CORPO[1])
        while k < R:
            line = LineString([(c.x + ax * k - bx * R, c.y + ay * k - by * R), (c.x + ax * k + bx * R, c.y + ay * k + by * R)])
            nuovi = []
            for p in pezzi:
                nuovi += [g for g in split(p, line).geoms] if p.intersects(line) else [p]
            pezzi = nuovi
            k += rng.uniform(*CORPO)
    pezzi = [p for p in pezzi if p.area > 1]
    piccoli = [p for p in pezzi if p.area < 160]
    grandi = [p for p in pezzi if p.area >= 160]
    for p in piccoli:                                    # al vicino con cui ha il confine più lungo
        if not grandi:
            grandi.append(p)
            continue
        j = max(range(len(grandi)), key=lambda i: grandi[i].buffer(0.05).intersection(p).area)
        grandi[j] = unary_union([grandi[j], p]).buffer(0.01).buffer(-0.01)
    return [_principale(g.buffer(0)) for g in grandi]


def _fusto(b, ang):
    """Il rettangolo più grande, fino a 30 × 30 m, girato come le strade, che sta nel podio a 4 m dal bordo."""
    inner = b.buffer(-4, join_style=2)
    c = inner.representative_point() if not inner.contains(inner.centroid) else inner.centroid
    for f in (1.0, 0.9, 0.8, 0.7, 0.6, 0.5):
        for asp in (1.0, 1.25, 0.8):
            w, h = TORRE[0] * f * asp ** 0.5, TORRE[1] * f / asp ** 0.5
            r = rettangolo((c.x, c.y), w, h, ang)
            if inner.contains(r):
                return r
    return rettangolo((c.x, c.y), 14, 14, ang)


def _rettangolo_in(b, ang, w, h, margine=4.0):
    """Il rettangolo w × h (girato come le strade, o di 90°) più grande che sta in b a `margine` m dal bordo; si
    rimpicciolisce se non ci sta."""
    inner = b.buffer(-margine, join_style=2)
    if inner.is_empty:
        inner = b
    inner = _principale(inner)
    c = inner.centroid if inner.contains(inner.centroid) else inner.representative_point()
    for f in (1.0, 0.92, 0.85, 0.78, 0.7, 0.62, 0.55, 0.48, 0.4):
        for ww, hh in ((w, h), (h, w)):
            for dx, dy in ((0, 0), (6, 0), (-6, 0), (0, 6), (0, -6)):
                r = rettangolo((c.x + dx, c.y + dy), ww * f, hh * f, ang)
                if inner.contains(r):
                    return r
    return rettangolo((c.x, c.y), 12, 10, ang)


def volumi(e):
    """I volumi dell'edificio: [{'da', 'a' (piani), 'z0', 'z1' (metri), 'forma', 'facciata', 'tetto', 'speciale' (il tetto
    con le cose dell'edificio: piscina, eliporto...), 'vano' (ha il vano scala sul tetto)}], più l'area, l'angolo e le
    corti."""
    n = sum(c for c, _, _ in e['piani'])
    rng = random.Random(e['lotto'] * 10 + e['parte'] + 7)
    if e['forma'] == 'foto':                            # gli edifici della foto: un volume per tetto, coi suoi piani
        vol = [dict(da=0, a=f - 1, z0=0, z1=f * ALTEZZA_PIANO, forma=g, facciata=e['facciata'], tetto=e['tetto'],
                    speciale=False, vano=False) for g, f in e['tetti']]
        b = unary_union([v['forma'] for v in vol])
        return vol, b, tangente((b.centroid.x, b.centroid.y)), []
    if e['forma'] == 'stimato':                         # senza contorno sulla mappa: un quadrato grande quanto l'impronta
        lato = max(4.0, e['impronta'] ** 0.5)
        b = box(-lato / 2, -lato / 2, lato / 2, lato / 2)
        return [dict(da=0, a=n - 1, z0=0, z1=n * ALTEZZA_PIANO, forma=b, facciata=e['facciata'], tetto=e['tetto'],
                     speciale=False, vano=False)], b, 0.0, []
    if e['forma'] == 'esistente':                       # resta com'è: la sua pianta è il contorno del luogo
        place = next(p for p in json.load(open(os.path.join(DATA, 'places.json'), encoding='utf-8')) if p['id'] == e['luogo'])
        b = poligono(place['path'])
        return [dict(da=0, a=n - 1, z0=0, z1=n * ALTEZZA_PIANO, forma=b, facciata=e['facciata'], tetto=e['tetto'],
                     speciale=False, vano=False)], b, tangente((b.centroid.x, b.centroid.y)), []
    b = area_edificio(e)
    ang = tangente((b.centroid.x, b.centroid.y))
    V = lambda g, da, a, fac, tet, spec, vano: dict(da=da, a=a, z0=da * ALTEZZA_PIANO, z1=(a + 1) * ALTEZZA_PIANO, forma=g,
                                                   facciata=fac, tetto=tet, speciale=spec, vano=vano)
    inner = b.buffer(-e['manica'], join_style=2)
    if e['forma'] == 'torre':                            # il podio gira attorno a una corte, come gli isolati vicini
        fusto = _fusto(b, ang)
        corte = inner.difference(fusto.buffer(8, join_style=2)) if not inner.is_empty else inner
        podio = b.difference(corte) if not corte.is_empty and corte.area >= 300 else b
        podio = _principale(podio.buffer(0))
        corona = fusto.buffer(-3.0, join_style=2)
        corti = [p for p in getattr(corte, 'geoms', [corte]) if p.geom_type == 'Polygon' and p.area >= 300]
        return [V(podio, 0, 0, 'pietra', 'ghiaia', False, False),
                V(fusto, 1, n - 2, e['facciata'], 'ghiaia', False, False),
                V(corona, n - 1, n - 1, e['facciata'], e['tetto'], True, True)], b, ang, corti
    if e['forma'] == 'palazzina':                        # un blocco compatto in mezzo al lotto, uno o due corpi
        ring, corti = _rettangolo_in(b, ang, *e['dimensioni']), []
    elif e['forma'] == 'pieno' or inner.is_empty or inner.area < 300:
        ring, corti = b, []
    else:
        ring = b.difference(inner)
        corti = [p for p in getattr(inner, 'geoms', [inner]) if p.geom_type == 'Polygon' and p.area >= 100]
    corpi = sorted(_corpi(ring, ang, rng), key=lambda g: -g.area)
    out = []
    for i, g in enumerate(corpi):
        top = n - 1 if i == 0 else max(3, n - 1 - rng.choice([0, 0, 1, 1, 2]))
        fac = e['facciata'] if i == 0 else rng.choice(FACCIATE_SIMILI[e['facciata']])
        tet = e['tetto'] if i == 0 or e['tetto'] in ('solare', 'verde') and rng.random() < 0.6 else rng.choice(TETTI_COMUNI)
        out.append(V(g, 0, top, fac, tet, i == 0, True))
    return out, b, ang, corti


def contorni(e):
    """I contorni sulla mappa: per gli edifici della foto i loro tetti, per gli altri quello che si vede dall'alto."""
    if e['forma'] == 'foto':
        return [g for g, _ in e['tetti']]
    return [contorno(e['volumi']).simplify(0.4)]


def contorno(vol):
    """Il contorno sulla mappa: quello che dell'edificio si vede dall'alto (pianta e tetti spostati dalla prospettiva)."""
    parts = []
    for v in vol:
        for p in getattr(v['forma'], 'geoms', [v['forma']]):
            g = Polygon(p.exterior.coords)
            parts += [g, affinity.translate(g, 0, -v['z1'] * PROSPETTIVA)]
    u = unary_union([p.buffer(0.6, join_style=2) for p in parts]).buffer(-0.6, join_style=2)
    return _principale(u)


# ------------------------------------------------------------------ imprese con il loro nome
# Quanti addetti ha un'impresa, dal nome (da, a): la prima regola che corrisponde. Ai piani dei negozi valgono prima le
# taglie dei negozi (una banca al piano terra è una filiale, non una sede).
TAGLIE_NEGOZI = [
    (r'^(Bar|Caff|Chiosco|Pub|Gelateria|Pasticceria|Cioccolateria|Enoteca|Bistrot)', 2, 5), (r'^Ristorante', 4, 9),
    (r'^(Banca|Farmacia|Studio dentistico)', 4, 8), (r'^(Cinema|Centro benessere|Sala bowling|Sala giochi)', 4, 9),
    (r'.', 2, 4),
]
TAGLIE = [
    (r'^Uffici tecnici', 10, 25),
    (r'^(Bar|Caff|Chiosco|Pub|Gelateria|Pasticceria|Cioccolateria|Enoteca|Bistrot)', 3, 6),
    (r'^(Ristorante|Mensa)', 6, 14), (r'^Farmacia', 4, 8), (r'^Studio dentistico', 4, 8),
    (r'^(Cinema|Centro benessere|Sala bowling|Sala giochi)', 5, 12),
    (r'^(Libreria|Gioielleria|Profumeria|Abbigliamento|Concept store|Galleria d.arte|Agenzia (immobiliare|di viaggi))', 2, 5),
    (r'^(Associazione|Patronato|Ordine|Casa delle associazioni)', 3, 12), (r'^Consulente', 3, 8),
    (r'^(Commercialista|Studio (notarile|fotografico|di topografia|geologico|di rendering))', 4, 12),
    (r'^Studio legale associato', 18, 35), (r'^Studio', 6, 22), (r'^(Agenzia|Ufficio brevetti)', 8, 30),
    (r'^(Officina|Serramentista|Ceramista|Laboratorio orafo)', 3, 9),
    (r'^(Minuteria|Impianti|Etichette|Caseificio|Lavanderia|Cavi|Arredo|Laboratorio prove)', 15, 45),
    (r'^(Banca|Assicurazioni)$', 15, 30),
    (r'^(Società|Compagnia|Sede|Uffici|Banca|Redazione|Emittente|Centro di calcolo|Centro elaborazione|Centro servizi)', 35, 110),
]
_TAGLIE = [(re.compile(rx), lo, hi) for rx, lo, hi in TAGLIE]
_TAGLIE_NEGOZI = [(re.compile(rx), lo, hi) for rx, lo, hi in TAGLIE_NEGOZI]


def taglia(nome, rng, tipo='uffici'):
    for rx, lo, hi in (_TAGLIE_NEGOZI if tipo == 'negozi' else _TAGLIE):
        if rx.search(nome):
            return rng.randint(lo, hi)
    return rng.randint(5, 20)


def assegna_imprese(e, piani, tipo, nomi, rng):
    """Mette le imprese `nomi`, ognuna grande quanto il suo tipo, sui piani `tipo` dell'edificio, in ordine: un'impresa che
    non sta nello spazio rimasto su un piano va al piano dopo; una più grande di un piano ne occupa più d'uno. Quello che
    avanza resta libero (posti_liberi); un piano senza imprese è "Spazio libero"."""
    idx = [i for i, p in enumerate(piani) if p.get('_tipo') == tipo]
    if not idx:
        return []
    caps = {i: piani[i]['posti_di_lavoro'] for i in idx}
    usati = {i: [] for i in idx}
    out = []
    k = 0
    for nome in nomi:
        s = taglia(nome, rng, tipo)
        out.append({'azienda': nome, 'ramo': None, 'dipendenti': s, 'piani': []})
        while s > 0:
            if k >= len(idx):                            # piani finiti: va dove resta più spazio, grande quanto c'è
                i = max(idx, key=lambda j: caps[j] - sum(n for _, n in usati[j]))
                rem = caps[i] - sum(n for _, n in usati[i])
                if rem < 2:
                    print(f"  attenzione: {e['nome']} (lotto {e['lotto']}) non ha posto per {nome}")
                    out.pop()
                    break
                s = min(s, rem)
                usati[i].append((nome, s))
                out[-1]['piani'].append(piani[i]['piano'])
                out[-1]['dipendenti'] = sum(n for p_ in usati.values() for a, n in p_ if a == nome)
                break
            i = idx[k]
            rem = caps[i] - sum(n for _, n in usati[i])
            if s <= rem:
                usati[i].append((nome, s))
                out[-1]['piani'].append(piani[i]['piano'])
                s = 0
            elif rem == caps[i]:                         # piano vuoto e impresa più grande: lo prende tutto
                usati[i].append((nome, rem))
                out[-1]['piani'].append(piani[i]['piano'])
                s -= rem
                k += 1
            else:                                        # non ci sta: il resto del piano resta libero
                k += 1
    for i in idx:
        p = piani[i]
        n = sum(x for _, x in usati[i])
        p['aziende'] = [{'azienda': a, 'dipendenti': x} for a, x in usati[i]]
        p['posti_liberi'] = max(0, caps[i] - n)
        p['posti_di_lavoro'] = n
        p['imprese'] = sum(1 for a in out if a['piani'] and a['piani'][0] == p['piano'])
        if not usati[i]:
            p['attivita'] = 'Spazio libero'
    return out


# ------------------------------------------------------------------ aziende negli uffici in affitto
def dividi_in_aziende(e, piani):
    """Divide i piani 'uffici' dell'edificio in aziende. Riempie piano per piano: un piano intero può andare a un'azienda
    grande (che ne prende 2-4 di fila), gli altri si dividono tra aziende piccole e medie; quello che avanza (meno di 4
    posti) resta libero. Scrive su ogni piano l'elenco delle aziende e restituisce l'elenco delle aziende dell'edificio."""
    rng = random.Random(e['lotto'] * 10 + e['parte'])
    idx = [i for i, p in enumerate(piani) if p.get('_tipo') == 'uffici']
    aziende = []

    def nuova(ramo):
        aziende.append({'azienda': f'Azienda {len(aziende) + 1}', 'ramo': ramo, 'dipendenti': 0, 'piani': []})
        return aziende[-1]

    k = 0
    while k < len(idx):
        i = idx[k]
        left = len(idx) - k
        if left >= 2 and rng.random() < AZIENDA_GRANDE:
            span = rng.randint(2, min(4, left))
            a = nuova(rng.choice(RAMI_GRANDI))
            for j in idx[k:k + span]:
                cap = piani[j]['posti_di_lavoro']
                piani[j]['aziende'] = [{'azienda': a['azienda'], 'dipendenti': cap}]
                piani[j]['posti_liberi'] = 0
                a['dipendenti'] += cap
                a['piani'].append(piani[j]['piano'])
            k += span
            continue
        cap = piani[i]['posti_di_lavoro']
        rem, here = cap, []
        while rem >= 4:
            r, acc = rng.random(), 0
            for lo, hi, pr in AZIENDE_PICCOLE:
                acc += pr
                if r <= acc:
                    break
            s = min(rng.randint(lo, hi), rem)
            if 0 < rem - s < 4:                   # non lasciare un avanzo troppo piccolo per un'altra azienda
                s = rem
            a = nuova(rng.choice(RAMI))
            a['dipendenti'] = s
            a['piani'].append(piani[i]['piano'])
            here.append({'azienda': a['azienda'], 'dipendenti': s})
            rem -= s
        piani[i]['aziende'] = here
        piani[i]['posti_di_lavoro'] = cap - rem   # gli ultimi posti restano liberi
        piani[i]['posti_liberi'] = rem
        k += 1
    for p in piani:
        if 'aziende' in p:
            p['imprese'] = sum(1 for a in aziende if a['piani'][0] == p['piano'])
    return aziende


# ------------------------------------------------------------------ numeri
def edifici(programma=None, quartiere='Centro', id_base=None, restano=None):
    """Gli edifici di un quartiere rifatto (il Centro se non si dice altro) con volumi, piani, superfici, abitanti, posti
    di lavoro e imprese (per il censimento, la mappa e il disegno del satellite)."""
    programma = PROGRAMMA if programma is None else programma
    id_base = ID_BASE if id_base is None else id_base
    restano = RESTANO if restano is None else restano
    out = []
    for e in programma:
        e = dict(e, quartiere=quartiere, restano=restano)
        vol, b, ang, corti = volumi(e)
        area_piano = {}
        for v in vol:
            for k in range(v['da'], v['a'] + 1):
                area_piano[k] = area_piano.get(k, 0) + v['forma'].area
        if e['forma'] == 'torre':                        # il fusto sta sopra il podio: ai piani alti conta solo lui
            for k in range(vol[1]['da'], vol[2]['a'] + 1):
                area_piano[k] = sum(v['forma'].area for v in vol[1:] if v['da'] <= k <= v['a'])
        x0, y0, x1, y1 = affinity.rotate(b, -ang, origin='centroid', use_radians=True).bounds
        d = dict(centro=[round(b.centroid.x, 2), round(b.centroid.y, 2)], larghezza=round(x1 - x0, 2),
                 profondita=round(y1 - y0, 2), angolo=round(ang, 5))
        terra = unary_union([v['forma'] for v in vol if v['z0'] == 0])
        piani, titolari = [], set()
        for count, tipo, cosa in e['piani']:
            for _ in range(count):
                sup = area_piano.get(len(piani), 0)
                p = dict(piano=len(piani), attivita=cosa, superficie_m2=round(sup))
                if tipo == 'studentato':
                    p.update(destinazione_uso='residenziale', alloggi=0,
                             abitanti=round(sup / M2_PER_STUDENTE), posti_di_lavoro=0, imprese=0)
                elif tipo == 'casa':
                    alloggi = round(sup / CASA['m2_per_alloggio'])
                    occupati = round(alloggi * (1 - CASA['alloggi_sfitti']))      # gli alloggi non sfitti
                    p.update(destinazione_uso='residenziale', alloggi=alloggi,
                             abitanti=round(occupati * CASA['abitanti_per_alloggio']), posti_di_lavoro=0, imprese=0)
                else:
                    a = ATTIVITA[tipo]
                    jobs = max(1, round(sup * a['occupazione'] / a['m2']))
                    if a['per_impresa'] == 'aziende':
                        imprese = 0
                    elif a['per_impresa'] is None:            # un solo titolare per tutti i suoi piani
                        imprese = 0 if cosa in titolari else 1
                        titolari.add(cosa)
                    else:
                        imprese = max(1, round(jobs / a['per_impresa']))
                    p.update(destinazione_uso=a['uso'], alloggi=0, abitanti=0,
                             posti_di_lavoro=jobs, imprese=imprese)
                    if tipo == 'hotel':
                        p['camere'] = round(sup / M2_PER_CAMERA)
                p['_tipo'] = tipo
                piani.append(p)
        rng = random.Random(e['lotto'] * 10 + e['parte'])
        aziende = dividi_in_aziende(e, piani) if e['uffici'] is None else assegna_imprese(e, piani, 'uffici', e['uffici'], rng)
        for tipo, nomi in (('negozi', e['negozi']), ('laboratorio', e['laboratori']), ('associazioni', e['associazioni'])):
            if nomi is not None:
                aziende += assegna_imprese(e, piani, tipo, nomi, rng)
        for p in piani:
            p.pop('_tipo')
        out.append(dict(e, id=id_base + len(out), disposizione=d, volumi=vol, corti=corti, impronta_m2=round(terra.area),
                        altezza_m=round(len(piani) * ALTEZZA_PIANO, 1), piani_dettaglio=piani, aziende=aziende))
    return out


def totali(es):
    return (sum(p['abitanti'] for e in es for p in e['piani_dettaglio']),
            sum(p['posti_di_lavoro'] for e in es for p in e['piani_dettaglio']))


# ------------------------------------------------------------------ scrittura dei dati della mappa
def scrivi(es, quartiere, restano):
    """Scrive gli edifici del quartiere in places.json (al posto dei vecchi, tranne quelli che restano) e gli abitanti in
    lots.json e quarters.json."""
    places = json.load(open(os.path.join(DATA, 'places.json'), encoding='utf-8'))
    lots = json.load(open(os.path.join(DATA, 'lots.json'), encoding='utf-8'))
    quarters = json.load(open(os.path.join(DATA, 'quarters.json'), encoding='utf-8'))

    # gli altri luoghi restano nel loro ordine; i nuovi edifici vanno in fondo (disegnati sopra), dal più grande
    keep = [p for p in places if p['quarter'] != quartiere or p['id'] in restano]
    for e in sorted(es, key=lambda e: -e['impronta_m2']):
        if e['forma'] == 'esistente':                    # il suo luogo resta quello che c'era
            continue
        d = e['disposizione']
        polys = [list(g.exterior.coords)[:-1] for g in contorni(e)]
        xs, ys = [x for q in polys for x, _ in q], [y for q in polys for _, y in q]
        top = e['volumi'][0] if e['forma'] != 'torre' else e['volumi'][-1]
        if e['forma'] == 'foto':                         # il nome sul tetto più grande
            tc = max((g for g, _ in e['tetti']), key=lambda g: g.area).representative_point()
        else:
            tc = affinity.translate(top['forma'].representative_point(), 0, -top['z1'] * PROSPETTIVA)
        w = min(d['larghezza'], d['profondita'])
        size = round(max(1.2, min(9.0, d['larghezza'] * 0.85 / (0.6 * len(e['nome'])), w * 0.3)), 1)
        keep.append({'id': e['id'], 'name': e['nome'], 'category': e['cat'], 'lot': e['lotto'], 'quarter': quartiere,
                     'bbox': [round(min(xs), 1), round(min(ys), 1), round(max(xs), 1), round(max(ys), 1)],
                     'path': ''.join('M' + ' '.join(f'{round(x, 1):g},{round(y, 1):g}' for x, y in q) + 'Z' for q in polys),
                     'label': {'x': round(tc.x, 1), 'y': round(tc.y, 1), 'size': size,
                               'angle': round(math.degrees(d['angolo']), 1)}})
    with open(os.path.join(DATA, 'places.json'), 'w', encoding='utf-8') as f:
        json.dump(keep, f, ensure_ascii=False, indent=1)

    for l in lots:
        if l['quarter'] != quartiere:
            continue
        mine = [e for e in es if e['lotto'] == l['number']]
        homes = [e for e in mine if any(p['abitanti'] for p in e['piani_dettaglio'])]
        l['population'] = sum(p['abitanti'] for e in mine for p in e['piani_dettaglio'])
        l['homes'] = len(homes)
        if homes:
            l['floors'] = round(sum(len(e['piani_dettaglio']) for e in homes) / len(homes))
        else:
            l.pop('floors', None)
    with open(os.path.join(DATA, 'lots.json'), 'w', encoding='utf-8') as f:
        json.dump(lots, f, ensure_ascii=False, indent=1)

    ab, jobs = totali(es)
    for q in quarters:
        if q['name'] == quartiere:
            q['population'] = ab
    with open(os.path.join(DATA, 'quarters.json'), 'w', encoding='utf-8') as f:
        json.dump(quarters, f, ensure_ascii=False, indent=1)
    print(f'{quartiere}: {len(es)} edifici · {ab} abitanti · {jobs} posti di lavoro')


def prova(es):
    for e in es:
        ab = sum(p['abitanti'] for p in e['piani_dettaglio'])
        j = sum(p['posti_di_lavoro'] for p in e['piani_dettaglio'])
        lib = sum(p.get('posti_liberi', 0) for p in e['piani_dettaglio'])
        az = f" imprese {len(e['aziende'])} liberi {lib}" if e['aziende'] else ''
        print(f"{e['lotto']:>3} {e['parte']} {e['nome'][:30]:30} {e['forma']:9} {len(e['piani_dettaglio']):>2}p "
              f"corpi {len(e['volumi']):>2} imp {e['impronta_m2']:5} ab {ab:5} lav {j:5}{az}")
    print('totale %d edifici, abitanti %d, posti di lavoro %d' % ((len(es),) + totali(es)))


def main():
    scrivi(edifici(), 'Centro', RESTANO)


if __name__ == '__main__':
    if '--prova' in sys.argv:
        prova(edifici())
    else:
        main()
