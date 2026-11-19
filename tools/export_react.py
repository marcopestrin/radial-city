# Esporta i dati della mappa interattiva per l'app React:
#   <cartella>/data/*.json  (quartieri, lotti, vie, luoghi, categorie, estensione della mappa)
#   <cartella>/tiles/*.jpg  (immagine satellitare tagliata in 4 x 4 riquadri)
# Riesegue la prima parte di names_html.py (stessa geometria, stessi nomi, stessi numeri) e scrive
# dati strutturati invece di stringhe SVG. Si lancia nella cartella del generatore della città:
#   python3 export_react.py percorso/del/progetto/public
import json, math, os, sys
EXPORT_DIR = sys.argv[1] if len(sys.argv) > 1 else 'react_export'
os.makedirs(f'{EXPORT_DIR}/data', exist_ok=True)
os.makedirs(f'{EXPORT_DIR}/tiles', exist_ok=True)

src = open('names_html.py').read()
src = src[:src.index('# ------------------------------------------------------------------ assemble')]
# il satellite qui si scrive in file separati, non in base64 dentro l'SVG
a = src.index("im = Image.open('world2_full.png')")
b = src.index('# ------------------------------------------------------------------ quarter tints')
src = src[:a] + src[b:]
exec(src)

from PIL import Image
Image.MAX_IMAGE_PIXELS = None

def r1(v):
    return round(float(v), 1)

# ------------------------------------------------------------------ riquadri del satellite
TILE_N = 4
im = Image.open('world2_full.png').convert('RGB').resize((7200, 7200), Image.LANCZOS)
tpx = 7200 // TILE_N
tm = SPAN / TILE_N
tiles = []
for j in range(TILE_N):
    for i in range(TILE_N):
        name = f'sat_{j}_{i}.jpg'
        im.crop((i * tpx, j * tpx, (i + 1) * tpx, (j + 1) * tpx)).save(f'{EXPORT_DIR}/tiles/{name}', 'JPEG', quality=80, optimize=True, progressive=True)
        tiles.append(dict(file=f'tiles/{name}', x=r1(WX0 + i * tm), y=r1(WY0 + j * tm), size=r1(tm)))

# ------------------------------------------------------------------ quartieri (colore, contorno, posizione del nome, abitanti)
quarters = []
for q, P in QP.items():
    r_, g_, b_ = hexc(PAL[col[q]])
    label_color = rgb(r_ * 0.55, g_ * 0.55, b_ * 0.55)
    big = max(geoms(P), key=lambda g: g.area)
    if q in VERT:
        sz = 70.0 / SC
        x_, y_ = VERT[q]
        label = dict(x=r1(x_), y=r1(y_), size=r1(sz), rotate=-90, spacing=r1(sz * 0.12))
    else:
        pl = polylabel(big.buffer(-20) if not big.buffer(-20).is_empty else big, 4)
        if q in QPOS:
            pl = Point(*QPOS[q])
        size = float(np.clip(math.sqrt(big.area) / 10.0, 40, 110)) / SC
        txt = q.upper()
        row = big.intersection(LineString([(WX0 - 10, pl.y), (WX1 + 10, pl.y)]))
        segs = [l for l in geoms(row) if l.geom_type == 'LineString']
        seg = min(segs, key=lambda l: l.distance(pl)) if segs else None
        avail = seg.length * 0.9 if seg is not None else 400
        if seg is not None:
            pl = Point((seg.bounds[0] + seg.bounds[2]) / 2 if q not in QPOS else pl.x, pl.y)
        tw = sum(a + size * 0.12 for a in adv(txt, size, True, 'DejaVu Serif'))
        if tw > avail:
            size *= avail / tw
            tw = avail
        size = max(size, 16.0 / SC)
        xm = min(max(pl.x, WX0 + tw / 2 + 12), WX1 - tw / 2 - 12)
        label = dict(x=r1(xm), y=r1(pl.y), size=r1(size), rotate=0, spacing=r1(size * 0.12))
    quarters.append(dict(id=QID[q], name=q, color=PAL[col[q]], labelColor=label_color, rural=q in RURAL,
                         population=int(POPQ.get(q, 0)), path=dpoly(P), label=label))

# ------------------------------------------------------------------ lotti (contorno, numero, abitanti, edifici residenziali)
lots_out = []
for L in lots:
    p, pl = L['poly'], L['pt']
    rad = p.exterior.distance(pl)
    txt = str(L['n'])
    size = float(np.clip(rad * 0.75, 7.5, 15.0))
    while sum(adv(txt, size, True)) > rad * 1.9 and size > 6.0:
        size -= 0.5
    lots_out.append(dict(number=L['n'], quarter=L['q'], path=dpoly(p), label=dict(x=r1(pl.x), y=r1(pl.y), size=r1(size)),
                         population=int(POPL.get(L['n'], 0)), homes=int(RESN.get(L['n'], 0))))
lots_out.sort(key=lambda l: l['number'])

# ------------------------------------------------------------------ nomi delle vie: ogni etichetta è un breve percorso lungo cui scorre il testo
streets = []
def street_label(name, ln, s0, size, color, kind):
    tw = sum(adv(name, size, True))
    if tw > ln.length - 4:
        return
    a = max(2.0, min(ln.length - tw - 2, s0 - tw / 2))
    pa, pb = ln.interpolate(a), ln.interpolate(a + tw)
    if pb.x < pa.x - 0.01:                      # si legge sempre da sinistra a destra
        ln = LineString(list(ln.coords)[::-1])
        a = ln.length - (a + tw)
    sub = LineString([ln.interpolate(s) for s in np.linspace(max(0, a - 6), min(ln.length, a + tw + 6), 40)])
    streets.append(dict(id=f'street-{len(streets)}', name=name, kind=kind, size=r1(size), color=color, path=dline(sub)))
for name, (gl, imp) in named.items():
    size, color = STY[imp]
    kind = 'main' if imp else 'minor'
    if name.startswith('Strada'):
        size, color, kind = 10.0, rgb(0.25, 0.22, 0.12), 'country'
    merged = linemerge(unary_union(gl)) if len(gl) > 1 else gl[0]
    for ln in sorted(geoms(merged), key=lambda l: -l.length):
        if ln.geom_type != 'LineString' or ln.length < 120:
            continue
        n_ = max(1, int(ln.length // 700.0))
        for k in range(n_):
            street_label(name, ln, ln.length * (k + 0.5) / n_, size, color, kind)
rl = N['rail']
street_label('Ferrovia', rl, rl.length * 0.62, 10.5, rgb(0.30, 0.20, 0.30), 'rail')
rc = N['river_c']
for f_ in (0.12, 0.42, 0.72):
    street_label('Fiume Lento', rc, rc.length * f_, 12.5, rgb(0.10, 0.30, 0.55), 'river')

# ------------------------------------------------------------------ luoghi: ogni edificio con una funzione e i luoghi con un nome
places = []
for i_, (g_, t_, cat_) in enumerate(sorted(HOV, key=lambda h: -h[0].area)):     # prima le forme grandi, sopra quelle piccole
    n_, q_ = lot_of(g_.representative_point())
    x_, y_, ang_, sz_ = FL.place(g_, t_, _badv, smax=(12.0 if g_.area > 20000 else 9.0), smin=1.0)
    places.append(dict(id=i_, name=t_, category=cat_, lot=n_ if n_ else None, quarter=q_,
                       bbox=[r1(v) for v in g_.bounds], path=dpoly(g_),
                       label=dict(x=r1(x_), y=r1(y_), size=r1(sz_), angle=r1(ang_))))

categories = [dict(id=k, label=v[0], color=v[1]) for k, v in FL.CATS.items()]
world = dict(x=WX0, y=WY0, width=SPAN, height=WY1 - WY0, tiles=tiles,
             minZoom=dict(streets=0.28, lotNumbers=0.55))

def dump(name, obj):
    with open(f'{EXPORT_DIR}/data/{name}.json', 'w', encoding='utf-8') as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
dump('world', world)
dump('quarters', quarters)
dump('lots', lots_out)
dump('streets', streets)
dump('places', places)
dump('categories', categories)
print('export', len(quarters), 'quarters', len(lots_out), 'lots', len(streets), 'street labels', len(places), 'places',
      'population', sum(q['population'] for q in quarters))
