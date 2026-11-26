# Perimetri sulla mappa per ogni attività del censimento. Lo chiama tools/censimento.py; scrive public/data/perimetri.json.
#
# La mappa (places.json) ha il contorno degli edifici; questo file aggiunge:
#   - "footprint": il contorno degli edifici censiti che non ne avevano (nuovi negozi, scuole, aziende agricole, palazzi con negozi),
#     messo nel loro lotto in un posto libero, con l'impronta del censimento;
#   - "activity": un perimetro per ogni attività (negozio, bar, ristorante, ufficio, studio...) di un edificio con più attività:
#     l'impronta dell'edificio è divisa tra le sue imprese in proporzione ai dipendenti. In un edificio con case (palazzi
#     residenziali con negozi) le attività stanno in una fascia lungo un lato, il resto resta dell'edificio.
#   - "pertinenza": il parcheggio di un insediamento nuovo (scuola, negozi, supermercato) o l'aia di un'azienda agricola nuova
#     (tools/siti.py), che il satellite disegna (tools/disegna_satellite.py);
# Un edificio con una sola attività ha già il suo contorno: quell'attività è l'edificio.
# A ogni impresa del censimento si aggiunge `luogo`: l'id del suo perimetro (in places.json o in perimetri.json).
import json, math, os, re, collections

import numpy as np
from shapely import affinity
from shapely.geometry import MultiPolygon, Polygon, box
from shapely.ops import unary_union

from foto import Foto
import siti

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'public', 'data')
OUT = os.path.join(DATA, 'perimetri.json')
SITI_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'siti.json')     # gli insediamenti, per tools/disegna_satellite.py

ASPETTO = {'servizio pubblico': 2.2, 'residenziale': 2.0, 'misto': 2.0, 'negozio': 1.6, 'ufficio': 1.8, 'fabbrica': 2.5,
           'agricolo': 2.0}
BLOCCANTI = ('Parcheggio', 'Parco', 'Giardino', 'Piazza', 'Campo', 'Pista', 'Skatepark', 'Palestra all', 'Anfiteatro', 'Orti',
             'Lago', 'Cava', 'Sagrato', 'Chiostro', 'Dehors', 'Piazzale')
CAMPI = ('Campi', 'Area di allevamento', 'Vigneti', 'Frutteto', 'Uliveto')     # contenitori dove un'azienda agricola si può mettere   # questi luoghi occupano il lotto anche se sono grandi: ci si costruisce solo se non c'è altro posto
LOTTI_VIETATI = {767, 578, 268}                     # lotti dove non si costruisce nulla di nuovo (rivisti a mano: case della foto, Belvedere, un parco)
DESTINAZIONI = {578: [744, 579, 581]}       # Belvedere (ville): le sue scuole vanno nei campi vuoti accanto
# insediamenti messi a mano: un edificio del gruppo -> (lotto, punto vicino a cui stare). I negozi di Lavanderia Costa stanno sulla
# strada tra il lotto 610 e il lotto 524 (Sant'Anna), un po' a nord dell'incrocio a sud
POSTI_A_MANO = {'Lavanderia Costa': (610, (1300.0, 3705.0))}
# lotti in cui i capannoni con più aziende sono divisi davvero: un corpo per azienda, separati da corsie di cemento
CAPANNONI_DIVISI_LOTTI = {294}
CORSIA_CAPANNONI = 6.0                      # larghezza delle corsie tra i corpi (metri)
DIVISIONI_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'divisioni.json')    # per tools/disegna_satellite.py
CONTENITORE = 0.3                         # un contorno più grande di questa parte del lotto è un contenitore (campo, complesso), non un ostacolo
FASCIA_MIN, FASCIA_MAX = 0.35, 0.6        # parte dell'impronta di un edificio con case occupata dalle attività
USO_CAT = {'negozio': 'com', 'ricettivo': 'com', 'ufficio': 'uff', 'servizio pubblico': 'pub', 'fabbrica': 'ind', 'deposito': 'ind',
           'parcheggio': 'ind', 'ferroviario': 'ind', 'impianto': 'ind', 'agricolo': 'agr', 'residenziale': 'res', 'misto': 'res'}


def poligono(path):
    """Il sottotracciato più grande di un contorno, come poligono."""
    best = None
    for sub in re.split(r'[MZ]', path):
        n = list(map(float, re.findall(r'-?\d+\.?\d*', sub)))
        p = list(zip(n[0::2], n[1::2]))
        if len(p) >= 3:
            g = Polygon(p).buffer(0)
            if not g.is_empty and (best is None or g.area > best.area):
                best = g
    if isinstance(best, MultiPolygon):
        best = max(best.geoms, key=lambda g: g.area)
    return best


def di(nome):
    """'della Scuola primaria X', 'dell'Asilo nido Y', 'del Liceo Z': la preposizione articolata davanti a un nome."""
    w = nome.split()[0].lower()
    if w[0] in 'aeiou':
        return "dell'" + nome
    if w.endswith('a'):
        return 'della ' + nome
    if w.startswith(('z', 'gn', 'ps')) or (w[0] == 's' and w[1] not in 'aeiou'):
        return 'dello ' + nome
    return 'del ' + nome


def a_path(g):
    parti = g.geoms if isinstance(g, MultiPolygon) else [g]
    return ' '.join('M' + ' '.join(f'{round(x, 1)},{round(y, 1)}' for x, y in list(p.exterior.coords)[:-1]) + 'Z' for p in parti)


def angolo_lungo(g):
    """Angolo (gradi) del lato lungo del rettangolo orientato che racchiude g."""
    c = list(g.minimum_rotated_rectangle.exterior.coords)
    lati = [(math.hypot(c[i + 1][0] - c[i][0], c[i + 1][1] - c[i][1]), c[i], c[i + 1]) for i in range(2)]
    _, a, b = max(lati)
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def rettangolo(cx, cy, w, h, ang):
    return affinity.rotate(box(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2), ang, origin=(cx, cy))


def _taglia(g, frazione, aggancio=None):
    """Taglia la forma `g` con una retta (parallela a un lato del suo rettangolo che la contiene, perpendicolare al lato lungo)
    in due parti: la prima ha circa `frazione` dell'area. `aggancio(m, orizzontale, bounds)` può spostare un po' la retta."""
    minx, miny, maxx, maxy = g.bounds
    orizzontale = (maxx - minx) >= (maxy - miny)
    lo, hi = (minx, maxx) if orizzontale else (miny, maxy)
    target = g.area * frazione
    for _ in range(36):
        m = (lo + hi) / 2
        a = g.intersection(box(minx - 1, miny - 1, m, maxy + 1) if orizzontale else box(minx - 1, miny - 1, maxx + 1, m))
        if a.area < target:
            lo = m
        else:
            hi = m
    m = (lo + hi) / 2
    if aggancio is not None:
        m = aggancio(m, orizzontale, (minx, miny, maxx, maxy))
    a = g.intersection(box(minx - 1, miny - 1, m, maxy + 1) if orizzontale else box(minx - 1, miny - 1, maxx + 1, m))
    b = g.intersection(box(m, miny - 1, maxx + 1, maxy + 1) if orizzontale else box(minx - 1, m, maxx + 1, maxy + 1))
    return a, b


def tessere(regione, pesi, aggancio=None):
    """Divide `regione` in tante tessere quanti i pesi, di area proporzionale ai pesi (taglia la forma, quindi funziona anche per
    edifici irregolari). Restituisce i poligoni nell'ordine dei pesi; None per una tessera che non ha spazio. `aggancio(m,
    orizzontale, bounds, ang, centro)` può spostare ogni taglio (nel sistema girato di -ang attorno al centro)."""
    ang = angolo_lungo(regione)
    c = regione.centroid
    rot = affinity.rotate(regione, -ang, origin=(c.x, c.y))
    agg = None if aggancio is None else (lambda m, o, bb: aggancio(m, o, bb, ang, (c.x, c.y)))
    ordine = sorted(range(len(pesi)), key=lambda i: (-pesi[i], i))
    out = {}

    def dividi(g, idx):
        if len(idx) == 1 or g.is_empty:
            for i in idx:
                out[i] = g
            return
        tot = sum(pesi[i] for i in idx)
        acc, k = 0.0, 0
        for k, i in enumerate(idx[:-1]):
            acc += pesi[i]
            if acc >= tot / 2:
                break
        a, b = idx[:k + 1], idx[k + 1:]
        ga, gb = _taglia(g, sum(pesi[i] for i in a) / tot, agg)
        dividi(ga, a)
        dividi(gb, b)

    dividi(rot, ordine)
    res = []
    for i in range(len(pesi)):
        g = out.get(i)
        if g is None or g.is_empty or g.geom_type not in ('Polygon', 'MultiPolygon'):
            res.append(None)
            continue
        g = affinity.rotate(g, ang, origin=(c.x, c.y))
        if isinstance(g, MultiPolygon):                       # i pezzetti minuscoli si scartano
            g = MultiPolygon([q for q in g.geoms if q.area >= 0.25 * max(x.area for x in g.geoms)])
            if len(g.geoms) == 1:
                g = g.geoms[0]
        res.append(g)
    return res


def fascia(poly, frazione):
    """La fascia lungo un lato lungo di `poly` che occupa circa `frazione` della sua area."""
    ang = angolo_lungo(poly)
    c = poly.centroid
    rot = affinity.rotate(poly, -ang, origin=(c.x, c.y))
    minx, miny, maxx, maxy = rot.bounds
    f = rot.intersection(box(minx - 1, miny - 1, maxx + 1, miny + (maxy - miny) * frazione))
    if isinstance(f, MultiPolygon):
        f = max(f.geoms, key=lambda g: g.area)
    return affinity.rotate(f, ang, origin=(c.x, c.y))


def aggancio_corsie(foto, regione):
    """Per i capannoni divisi: ogni taglio si sposta (di 11 m al più) sulla corsia chiara più vicina tra i pannelli del tetto,
    così ogni corpo ha il suo tetto intero."""
    x0, y0, x1, y1 = regione.bounds
    img = foto.rgb(x0 - 2, y0 - 2, x1 + 2, y1 + 2).astype(float).mean(2)

    def lum(xs, ys):
        i = np.clip(((xs - x0 + 2) * 1.2).astype(int), 0, img.shape[1] - 1)
        j = np.clip(((ys - y0 + 2) * 1.2).astype(int), 0, img.shape[0] - 1)
        return img[j, i]

    def aggancia(m, orizzontale, bb, ang, centro):
        mnx, mny, mxx, mxy = bb
        cs, sn = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        lungo = np.linspace((mny if orizzontale else mnx) + 3, (mxy if orizzontale else mxx) - 3, 80)
        prove = np.arange(-11.0, 11.01, 0.5)
        medie = []
        for d in prove:
            u, v = (np.full_like(lungo, m + d), lungo) if orizzontale else (lungo, np.full_like(lungo, m + d))
            du, dv = u - centro[0], v - centro[1]
            medie.append(lum(centro[0] + du * cs - dv * sn, centro[1] + du * sn + dv * cs).mean())
        medie = np.array(medie)
        k = int(np.argmax(medie - 0.6 * np.abs(prove)))     # la corsia chiara più vicina
        return m + prove[k] if medie[k] - np.median(medie) >= 10 else m
    return aggancia


def dividi_corpi(tess):
    """Le tessere di un capannone diventano corpi separati: lungo ogni confine tra due tessere una corsia."""
    linee = []
    for i in range(len(tess)):
        for j in range(i + 1, len(tess)):
            if tess[i] is None or tess[j] is None:
                continue
            l = tess[i].boundary.intersection(tess[j].boundary)
            if not l.is_empty and l.length > 3:
                linee.append(l)
    if not linee:
        return tess, []
    corsia = unary_union([l.buffer(CORSIA_CAPANNONI / 2, cap_style='flat', join_style='mitre') for l in linee])
    corpi = []
    for t in tess:
        if t is None:
            corpi.append(None)
            continue
        q = t.difference(corsia)
        if isinstance(q, MultiPolygon):
            q = max(q.geoms, key=lambda g: g.area)
        corpi.append(q)
    regione = unary_union([t for t in tess if t is not None])
    c = corsia.intersection(regione)
    return corpi, [g for g in getattr(c, 'geoms', [c]) if g.area > 1]


def attivita_di(e):
    """Le attività di un edificio: nome -> {piani, dip, uso}, dai piani (una sola volta per nome)."""
    out = collections.OrderedDict()
    for f in e['piani']:
        for fa in f.get('aziende') or []:
            a = out.setdefault(fa['azienda'], {'piani': [], 'dip': 0, 'uso': f['destinazione_uso']})
            a['piani'].append(f['piano'])
            a['dip'] += fa['dipendenti']
    return out


def etichetta(g):
    if isinstance(g, MultiPolygon):
        g = max(g.geoms, key=lambda q: q.area)
    r = g.minimum_rotated_rectangle
    c = list(r.exterior.coords)
    lati = sorted([math.hypot(c[1][0] - c[0][0], c[1][1] - c[0][1]), math.hypot(c[2][0] - c[1][0], c[2][1] - c[1][1])])
    p = g.representative_point()
    ang = angolo_lungo(g)
    while ang > 90:
        ang -= 180
    while ang <= -90:
        ang += 180
    return {'x': round(p.x, 1), 'y': round(p.y, 1), 'size': round(max(1.2, min(lati[0] * 0.115, 8)), 1),
            'angle': round(ang if abs(ang) > 1 else 0.0, 1)}


def luoghi_dentro(base_poly, luogo_edificio, poly):
    """Gli altri luoghi di places.json dentro il contorno di un edificio (per esempio gli edifici di un campus): non si coprono."""
    out = []
    for i, g in base_poly.items():
        if i == luogo_edificio or g is None:
            continue
        if g.area < poly.area * 0.5 and poly.contains(g.representative_point()):
            out.append(g)
    return out


# ------------------------------------------------------------------ dove e come mettere un edificio nuovo
# Quartieri dove non vanno scuole e negozi nuovi (zone di lavoro, l'ospedale, il fiume, Belvedere che è un comprensorio di ville);
# un edificio resta comunque ammesso nel suo quartiere (le mense dei poli di lavoro), tranne Belvedere.
QUARTIERI_NON_RESIDENZIALI = {'Polo Logistico', 'Zona Industriale Sud', 'Zona Artigianale', 'Aeroporto', 'Stazione', 'Le Officine',
                              'Tecnopolo', 'San Luca', 'Stadio', 'Golena del Fiume', 'Belvedere'}
RAGGIO = {'scuola': 800, 'supermercato': 700, 'negozio': 500, 'agricolo': 2000, 'fabbrica': 2000}   # metri dal posto previsto
NUCLEO_DENSO = {'Centro', 'La Cerchia'}       # qui gli spazi aperti sono cortili, giardinetti e campi: niente edifici nuovi
SPORT_E_SCUOLE = r'^(Palestra|Centro giovanile|Campo|Stadio|Piscin|Scuola|Liceo|Istituto|Polo scolastico|Asilo|Bocciodromo|Pista)'

FRONTE_MAX = ('scuola', 'supermercato', 'negozio')      # i tipi che stanno nei quartieri abitati, sul fronte di una strada


def pool_edificio(e):
    """Che tipo di edificio della foto fa da modello a un edificio nuovo."""
    n, u = e['nome'], e['destinazione_uso']
    if re.match(r'^(Asilo|Scuola|Liceo|Istituto)', n):
        return 'scuola'
    if n.startswith('Supermercato'):
        return 'supermercato'
    if u == 'agricolo':
        return 'agricolo'
    if u in ('fabbrica', 'impianto'):
        return 'fabbrica'
    return 'negozio'


def quartiere_ammesso(pool, q, q_orig):
    if q == 'Belvedere' or q in NUCLEO_DENSO:
        return False
    if pool in ('agricolo', 'fabbrica'):
        return q == q_orig or q.startswith('Campagna') or q == 'Golena del Fiume'
    return q == q_orig or q not in QUARTIERI_NON_RESIDENZIALI


MODELLI_SCUOLA = (r'^(Scuola|Asilo|Liceo|Istituto|Polo scolastico|Biblioteca|Centro civico|Centro giovanile|Casa delle associazioni|'
                  r'Aule studio|Aula|Facoltà|Dipartimento|Laboratori universitari|Uffici comunali|Municipio|Anagrafe|Centro anziani|'
                  r'Casa di quartiere|Ludoteca)')
MODELLI_NEGOZIO = (r'^(Bar|Ristorante|Pizzeria|Trattoria|Osteria|Gelateria|Pasticceria|Caff|Negozi|Farmacia|Banca|Libreria|'
                   r'Abbigliamento|Calzature|Ferramenta|Telefonia|Ottica|Edicola|Tabaccheria|Panetteria|Macelleria|Fiorista|Estetista|'
                   r'Parrucchiere|Profumeria|Sushi|Pub|Enoteca|Mobili|Agenzia|Studio|Elettronica|Giocattoli|Casalinghi|Lavanderia|'
                   r'Alimentari|Frutta|Pescheria|Fast food|Paninoteca|Birreria|Wine|Steakhouse|Cartoleria|Copisteria|Assicurazioni|'
                   r'Animali|Articoli|Gioielleria|Erboristeria|Mensa|Tavola calda)')
SPECIALI = (r'^(Chiesa|Cappella|Campanile|Duomo|Stadio|Tribuna|Piscin|Cimitero|Ospedale|Pronto|Stazione|Torre|Castello|Monastero|'
            r'Spogliatoi|Palazzetto|Teatro|Museo|Planetario|Terminal|Hangar|Depuratore|Acquedotto|Discarica|Vigili|Caserma|Carcere|'
            r'Cardiologia|Oncologia|Pediatria|Ematologia|Radioterapia|Neonatologia|Maternit|Neurologia|Riabilitazione|Chirurgia|'
            r'Medicina|Ortopedia|Radiologia|Day hospital|Amministrazione ospedale|Accesso ambulanze|Ingresso|Padiglione|Eliporto|'
            r'Centro congressi|Fiera|Palestra|Campo|Bocciodromo|Grattacielo|Torre per uffici|Hotel|Parcheggio|Cabina|Centrale)')
LATO_MIN = {'scuola': 12, 'supermercato': 12, 'negozio': 7, 'agricolo': 8, 'fabbrica': 10}
ALLUNGAMENTO_MAX = 6


def pool_donatore(p, area):
    n = p['name']
    if re.match(MODELLI_SCUOLA, n) and 400 <= area <= 9000:
        return 'scuola'
    if p['category'] in ('pub', 'uff') and 400 <= area <= 5000 and not re.match(SPECIALI, n):
        return 'scuola'                                 # edifici pubblici e uffici bassi: dall'alto sono come una scuola
    if re.match(r'^(Supermercato|Discount|Ipermercato)', n):
        return 'supermercato'
    if p['category'] == 'com' and 50 <= area <= 700 and re.match(MODELLI_NEGOZIO, n):
        return 'negozio'
    if p['category'] == 'agr' and 150 <= area <= 3000 and not re.match(r'^(Silo|Serbatoio|Campi|Area|Vigneti|Orti|Serra|Tettoia|Pensilina)', n):
        return 'agricolo'
    if p['category'] in ('ind', 'art') and 200 <= area <= 3000 and not re.match(r'^(Tettoia|Pensilina|Cumuli|Vasche|Box)', n):
        return 'fabbrica'
    return None


def lati(g):
    c = list(g.minimum_rotated_rectangle.exterior.coords)
    a, b = math.dist(c[0], c[1]), math.dist(c[1], c[2])
    return min(a, b), max(a, b)


def catalogo_donatori(places, base_poly, foto):
    """Gli edifici veri della foto che possono fare da modello: un tetto a sé (non un pezzo di un tetto più grande), che coincide
    con il suo contorno, non ridisegnato (fuori dal Centro, che è disegnato)."""
    out = collections.defaultdict(list)
    for p in places:
        g = base_poly.get(p['id'])
        if g is None or p['quarter'] == 'Centro':
            continue
        k = pool_donatore(p, g.area)
        if not k:
            continue
        corto, lungo = lati(g)
        if corto < LATO_MIN[k] or lungo > ALLUNGAMENTO_MAX * corto:
            continue
        tetto, prato, anello = foto.tetto_e_intorno(g)
        if tetto < 0.55 or prato > 0.15 or anello > 0.35 or foto.ritoccato(g) > 4:
            continue
        out[k].append({'id': p['id'], 'poly': g, 'ang': angolo_lungo(g) % 180, 'area': g.area, 'nome': p['name']})
    return out


def angoli_lotto(lp):
    """Gli angoli dei due lati più lunghi del lotto (a meno di 90°): le strade su cui si affaccia."""
    c = list(lp.exterior.coords)
    acc = collections.Counter()
    for a, b in zip(c, c[1:]):
        acc[round(math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 90)] += math.hypot(b[0] - a[0], b[1] - a[1])
    out, primo = [], None
    for ang, lung in acc.most_common():
        primo = primo or lung
        if lung < 0.35 * primo:
            break
        if all(min((ang - t) % 90, (t - ang) % 90) > 4 for t in out):
            out.append(float(ang))
        if len(out) == 2:
            break
    return out or [angolo_lungo(lp)]


def applica(edifici, places, lots):
    """Aggiunge `luogo` a ogni impresa, `luoghi` agli edifici senza contorno e scrive perimetri.json. Restituisce un riassunto."""
    base = {p['id']: p for p in places}
    base_poly = {i: poligono(p['path']) for i, p in base.items()}
    lotto_poly = {l['number']: poligono(l['path']) for l in lots}
    lotto_q = {l['number']: l['quarter'] for l in lots}
    occupato_lotto = collections.defaultdict(list)
    for i, p in base.items():
        if p['lot'] is not None and base_poly[i] is not None:
            occupato_lotto[p['lot']].append((base_poly[i], p['name']))
    contatore = [max(base) + 1]
    nuovi = {'footprint': [], 'activity': [], 'pertinenza': []}
    r = collections.Counter()

    def crea(kind, nome, cat, lotto, quartiere, g, codice, piani=None, origine=None):
        x0, y0, x1, y1 = g.bounds
        p = {'id': contatore[0], 'name': nome, 'category': cat, 'lot': lotto, 'quarter': quartiere,
             'bbox': [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)], 'path': a_path(g), 'label': etichetta(g),
             'kind': kind, 'edificio': codice}
        if origine:
            p['origine'] = origine                    # 'foto': il contorno è un tetto che la foto ha già (non si ridisegna)
        if piani:
            p['floors'] = piani                       # per l'ombra del tetto sul satellite (tools/disegna_satellite.py)
        contatore[0] += 1
        nuovi[kind].append((g.area, p))
        return p

    # ---- 1. il contorno degli edifici che non ne hanno
    foto = Foto()
    foto = foto if foto.disponibile else None
    foot = {}
    centro_lotto = {n: g.centroid for n, g in lotto_poly.items() if g is not None}

    senza = [e for e in edifici if not e['luoghi']]
    palazzi = [e for e in senza if e['nome'] == 'Palazzo residenziale']
    nuovi_edifici = [e for e in senza if e['nome'] != 'Palazzo residenziale' and attivita_di(e)]

    # 1a. i palazzi residenziali ci sono già nella foto, senza contorno nei dati: il contorno è il loro tetto nella foto
    if foto:
        per_lotto = collections.defaultdict(list)
        for e in palazzi:
            per_lotto[e['lotto']].append(e)
        for lotto, es in sorted(per_lotto.items(), key=lambda kv: kv[0] or 0):
            lp = lotto_poly.get(lotto)
            if lp is None:
                continue
            esistenti = unary_union([g for g, _ in occupato_lotto[lotto]]) if occupato_lotto[lotto] else None
            tetti = foto.tetti(lp, esistenti)
            for e in sorted(es, key=lambda e: (not attivita_di(e), e['codice'])):     # prima quelli con negozi
                if not tetti:
                    break
                k = min(range(len(tetti)), key=lambda i: abs(tetti[i].area - e['superficie_impronta_m2']))
                g = tetti.pop(k)
                p = crea('footprint', e['nome'], USO_CAT.get(e['destinazione_uso'], 'res'), lotto, lotto_q[lotto], g, e['codice'],
                         e['piani_totali'], origine='foto')
                e['luoghi'] = [p['id']]
                foot[p['id']] = g
                occupato_lotto[lotto].append((g, e['nome']))
                r['palazzi_dalla_foto'] += 1
    nuovi_edifici += [e for e in palazzi if not e['luoghi'] and attivita_di(e)]

    # 1b. gli edifici nuovi (negozi, scuole, supermercati, mense, aziende agricole), con quello che gli serve intorno: ogni gruppo è un
    # insediamento (tools/siti.py) — i negozi di un nucleo in fila con il parcheggio davanti, una scuola con il parcheggio, il
    # vialetto e il giardino, un'azienda agricola con l'aia e la strada d'accesso — su terreno libero, lontano dalle case,
    # affacciato su una strada. Ogni edificio è la copia di un edificio vero della foto dello stesso tipo (stessa luce, stessi
    # dettagli): il suo contorno è quello di quell'edificio, girato e messo in scala.
    donatori = catalogo_donatori(places, base_poly, foto) if foto else {}
    r['donatori'] = {k: len(v) for k, v in donatori.items()}
    spostamenti = []
    siti_out = []

    def bloccati_di(lotto, pool):
        lp = lotto_poly[lotto]
        residenziale = lotto_q[lotto] not in QUARTIERI_NON_RESIDENZIALI
        profilo = 'agricolo' if pool in ('agricolo', 'fabbrica') else ('urbano' if residenziale else 'polo')

        def ostacolo(g, n):
            if g.area <= CONTENITORE * lp.area or n.startswith(BLOCCANTI) or n == 'nuovo':
                return True
            if profilo == 'agricolo':
                return not n.startswith(CAMPI)
            return profilo != 'polo'
        parti = [g for g, n in occupato_lotto[lotto] if ostacolo(g, n)]
        # i luoghi dei lotti vicini che sconfinano in questo lotto
        parti += [g for g, n in vicini_di(lotto) if g.intersects(lp) and g.area <= CONTENITORE * lp.area]
        if profilo == 'urbano':
            parti += [g.buffer(30) for g, n in occupato_lotto[lotto] if re.match(SPORT_E_SCUOLE, n)]
        return profilo, unary_union(parti or [Polygon()])

    _vicini = {}

    def vicini_di(lotto):
        """I luoghi (contorno, nome) degli altri lotti che toccano il lotto."""
        if lotto not in _vicini:
            lp = lotto_poly[lotto].buffer(1)
            _vicini[lotto] = [(g, n) for l, gs in occupato_lotto.items() if l != lotto for g, n in gs if g.intersects(lp)]
        return _vicini[lotto]

    def lotto_ammesso(pool, lotto):
        nomi = [n for _, n in occupato_lotto[lotto]]
        if pool in FRONTE_MAX and lotto_q[lotto] not in QUARTIERI_NON_RESIDENZIALI and any(re.match(SPORT_E_SCUOLE, n) for n in nomi):
            return False                            # c'è già una scuola o una palestra: i prati intorno sono i suoi campi
        if pool == 'scuola' and any(re.match(r'^(Università|Facoltà|Dipartimento)', n) for n in nomi):
            return False                            # un campus universitario (bar e mense invece ci stanno)
        return True

    def angoli_lotto_di(lotto):
        return angoli_lotto(lotto_poly[lotto])

    ins = siti.Insediatore(foto, lotto_poly, bloccati_di, donatori) if foto else None
    gruppi = []
    nuclei = collections.defaultdict(list)
    for e in nuovi_edifici:
        k = pool_edificio(e)
        if k == 'negozio':
            nuclei[e['lotto']].append(e)
        else:
            gruppi.append({'tipo': k, 'pool': k, 'edifici': [e]})
    for lotto, es in nuclei.items():                    # un nucleo di negozi: in file di 4 al massimo
        es.sort(key=lambda e: e['codice'])
        parti = math.ceil(len(es) / 4)
        misure = [len(es) // parti + (1 if i < len(es) % parti else 0) for i in range(parti)]
        i = 0
        for m in misure:
            gruppi.append({'tipo': 'negozi', 'pool': 'negozio', 'edifici': es[i:i + m]})
            i += m
    PRIORITA = {'supermercato': 0, 'scuola': 1, 'negozi': 2, 'fabbrica': 3, 'agricolo': 4}
    gruppi.sort(key=lambda g: (PRIORITA[g['tipo']], -sum(e['superficie_impronta_m2'] for e in g['edifici']), g['edifici'][0]['codice']))
    for n_sito, gr in enumerate(gruppi, 1):
        es, pool = gr['edifici'], gr['pool']
        orig = es[0]['lotto']
        esito = None
        if ins and orig in lotto_poly:
            bersaglio = (centro_lotto[orig].x, centro_lotto[orig].y)
            q0 = lotto_q[orig]
            vicini = sorted((n for n in centro_lotto if n not in LOTTI_VIETATI), key=lambda n: centro_lotto[orig].distance(centro_lotto[n]))
            lotti = [n for n in vicini if quartiere_ammesso(pool, lotto_q[n], q0) and lotto_ammesso(pool, n)]
            aree = [e['superficie_impronta_m2'] for e in es]
            a_mano = next((v for k, v in POSTI_A_MANO.items() if any(e['nome'] == k for e in es)), None)
            if a_mano:                                  # messo a mano: in quel lotto, il più vicino possibile al punto dato
                esito = ins.piazza(gr['tipo'], pool, es[0]['nome'], aree, a_mano[1], [a_mano[0]], angoli_lotto_di, RAGGIO[pool],
                                   entro=80.0)
                r['messi_a_mano' if esito else 'a_mano_senza_posto'] += 1
            if esito is None and orig in DESTINAZIONI:  # lotti scelti a mano: prima questi
                esito = ins.piazza(gr['tipo'], pool, es[0]['nome'], aree, bersaglio, DESTINAZIONI[orig], angoli_lotto_di, RAGGIO[pool])
            if esito is None:
                esito = ins.piazza(gr['tipo'], pool, es[0]['nome'], aree, bersaglio, lotti, angoli_lotto_di, RAGGIO[pool])
        if esito is None:                               # nessun posto: nel suo lotto, senza modello (non dovrebbe succedere)
            for e in es:
                r['senza_posto'] += 1
                lp = lotto_poly.get(e['lotto'])
                if lp is None:
                    r['senza_lotto'] += 1
                    continue
                aspetto = ASPETTO.get(e['destinazione_uso'], 1.8)
                q = math.sqrt(e['superficie_impronta_m2'] / aspetto) * 0.4
                g = rettangolo(lp.centroid.x, lp.centroid.y, q * aspetto, q, angolo_lungo(lp))
                p = crea('footprint', e['nome'], USO_CAT.get(e['destinazione_uso'], 'com'), e['lotto'], lotto_q[e['lotto']], g, e['codice'],
                         e['piani_totali'])
                e['luoghi'] = [p['id']]
                foot[p['id']] = g
            continue
        lotto = esito['lotto']
        r['insediamenti_' + gr['tipo']] += 1
        r['grado_%s_%s' % esito['grado']] += 1
        codici = []
        for e, (g, mo) in zip(es, esito['edifici']):
            occupato_lotto[lotto].append((g, 'nuovo'))
            if e['lotto'] in centro_lotto:
                spostamenti.append((round(g.centroid.distance(centro_lotto[e['lotto']])), e['nome']))
            if lotto != e['lotto']:
                r['spostati'] += 1
                vecchio = lotto_q.get(e['lotto'])
                e['quartiere'] = lotto_q[lotto]
                if e.get('zona') == vecchio:
                    e['zona'] = lotto_q[lotto]
                e['lotto'] = lotto
            # l'impronta del censimento è quella del contorno disegnato
            e['superficie_impronta_m2'] = round(g.area)
            for f in e['piani']:
                f['superficie_m2'] = round(g.area)
            e['superficie_lorda_m2'] = round(g.area) * len(e['piani'])
            p = crea('footprint', e['nome'], USO_CAT.get(e['destinazione_uso'], 'com'), lotto, lotto_q[lotto], g, e['codice'], e['piani_totali'])
            c = g.centroid
            p['donatore'] = {'id': mo['d']['id'], 'rot': round(mo['rot'], 2), 'scala': round(mo['sc'], 3), 'centro': [round(c.x, 2), round(c.y, 2)]}
            e['luoghi'] = [p['id']]
            foot[p['id']] = g
            codici.append(e['codice'])
            r['footprint'] += 1
        # il parcheggio e l'aia sono luoghi della mappa anche loro (si scelgono col mouse), sotto gli edifici
        o_, eu_, ev_ = esito['o'], esito['eu'], esito['ev']
        for tipo_el, rc in esito['elementi']:
            if tipo_el not in ('parcheggio', 'aia'):
                continue
            nomi_ed = [e['nome'] for e in es]
            if len(nomi_ed) > 1:
                titolo = 'Parcheggio di ' + ', '.join(nomi_ed[:-1]) + ' e ' + nomi_ed[-1]
            else:
                titolo = ('Parcheggio ' if tipo_el == 'parcheggio' else 'Aia ') + di(nomi_ed[0])
            g_el = siti.rettangolo(o_, eu_, ev_, *rc)
            crea('pertinenza', titolo, USO_CAT.get(es[0]['destinazione_uso'], 'com'), lotto, lotto_q[lotto], g_el, es[0]['codice'])
            r['pertinenze'] += 1
        siti_out.append({'id': n_sito, 'tipo': gr['tipo'], 'lotto': lotto, 'edifici': codici,
                         'o': [round(float(v), 2) for v in esito['o']], 'u': [round(float(v), 5) for v in esito['eu']],
                         'v': [round(float(v), 5) for v in esito['ev']],
                         'elementi': [{'tipo': t, 'rect': [round(float(v), 2) for v in rc]} for t, rc in esito['elementi']]})
    with open(SITI_OUT, 'w', encoding='utf-8') as f:
        f.write(json.dumps(siti_out, ensure_ascii=False, separators=(',', ':')))

    if spostamenti:
        spostamenti.sort()
        r['distanza_dal_posto_previsto_mediana_m'] = spostamenti[len(spostamenti) // 2][0]
        r['distanze_maggiori'] = spostamenti[-6:]

    # ---- 2. un perimetro per ogni attività
    divisioni = []

    for e in edifici:
        att = attivita_di(e)
        if not att:
            continue
        luogo_edificio = e['luoghi'][0] if e['luoghi'] else None
        poly = foot.get(luogo_edificio) or (base_poly.get(luogo_edificio) if luogo_edificio is not None else None)
        da_nome = {a['azienda']: a for a in e['aziende']}
        if len(att) == 1 or poly is None:
            for nome in att:
                if nome in da_nome:
                    da_nome[nome]['luogo'] = luogo_edificio
            r['una_attivita' if len(att) == 1 else 'senza_poligono'] += len(att)
            continue
        altri = luoghi_dentro(base_poly, luogo_edificio, poly)
        regione = poly.difference(unary_union(altri)) if altri else poly
        if regione.is_empty:
            regione = poly
        if isinstance(regione, MultiPolygon):
            regione = max(regione.geoms, key=lambda g: g.area)
        con_case = any(f['abitanti'] > 0 or f['destinazione_uso'] == 'residenziale' for f in e['piani'])
        if con_case:
            lorda = sum(f['superficie_m2'] for f in e['piani'])
            comm = sum(f['superficie_m2'] for f in e['piani'] if f.get('aziende'))
            frazione = min(FASCIA_MAX, max(FASCIA_MIN, comm / lorda if lorda else FASCIA_MIN))
            regione = fascia(regione, frazione)
        nomi = sorted(att, key=lambda n: (min(att[n]['piani']), n))
        massimo = max(1, int(regione.area // 6))       # tessere minuscole non servono: le attività in più restano senza perimetro proprio
        pesi = [att[n]['dip'] + 2 for n in nomi[:massimo]]
        diviso = (e['lotto'] in CAPANNONI_DIVISI_LOTTI and e['destinazione_uso'] in ('fabbrica', 'deposito') and foto is not None
                  and luogo_edificio in base_poly)
        tess = tessere(regione, pesi, aggancio_corsie(foto, regione) if diviso else None)
        if diviso:                                      # un corpo per azienda: tra i corpi una corsia larga CORSIA_CAPANNONI
            tess, corsie = dividi_corpi(tess)
            divisioni.append({'luogo': luogo_edificio, 'edificio': e['codice'], 'corsie': [a_path(c) for c in corsie],
                              'corpi': [a_path(t) for t in tess if t is not None]})
            r['capannoni_divisi'] += 1
        for i, n in enumerate(nomi):
            g = tess[i] if i < len(tess) else None
            if n not in da_nome:
                continue
            if g is None or g.area < 2:
                da_nome[n]['luogo'] = luogo_edificio
                r['senza_tessera'] += 1
                continue
            p = crea('activity', n, USO_CAT.get(att[n]['uso'], 'com'), e['lotto'], e['quartiere'], g, e['codice'])
            da_nome[n]['luogo'] = p['id']
            r['activity'] += 1

    with open(DIVISIONI_OUT, 'w', encoding='utf-8') as f:
        f.write(json.dumps(divisioni, ensure_ascii=False, separators=(',', ':')))
    elenco = ([p for _, p in sorted(nuovi['pertinenza'], key=lambda t: -t[0])] + [p for _, p in sorted(nuovi['footprint'], key=lambda t: -t[0])]
              + [p for _, p in sorted(nuovi['activity'], key=lambda t: -t[0])])
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(json.dumps(elenco, ensure_ascii=False, separators=(',', ':')))
    return dict(r)
