# Scrive le note Obsidian di Città Radiale: una cartella per quartiere, una nota per quartiere e una per lotto,
# più le note "Città radiale", "Linee autobus", "Piani in Centro e La Cerchia",
# "Come sono stimati i lavoratori".
#
#   python3 tools/export_obsidian.py ["/percorso/Obsidian Vault/città radiale"]
#
# Rilanciarlo aggiorna le note: prima cancella solo i file che portano la riga "generato: tools/export_obsidian.py".
# I collegamenti usano il percorso completo dentro il vault (es. [[città radiale/Centro/Lotto 21|Lotto 21]])
# perché altre cartelle del vault hanno note con lo stesso nome ("Lotto 343").
import json, math, os, re, sys, collections
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(__file__))
from lavoratori import footprint
EMPLOYMENT_RATE = 0.45     # abitanti occupati / abitanti (valore medio italiano, indicativo)


def load(data_dir='public/data/'):
    return (json.load(open(data_dir + 'places.json', encoding='utf-8')), json.load(open(data_dir + 'lots.json', encoding='utf-8')))

ROOT = os.path.join(os.path.dirname(__file__), '..')
os.chdir(ROOT)
OUT = sys.argv[1] if len(sys.argv) > 1 else '/Users/marcopestrin/Documents/Obsidian Vault/città radiale'
VAULT_DIR = os.path.basename(OUT.rstrip('/'))          # nome della cartella dentro il vault
MARK = 'generato: tools/export_obsidian.py'
DATE = '2026-11-16'

places, lots = load()
quarters = json.load(open('public/data/quarters.json', encoding='utf-8'))
categories = {c['id']: c['label'] for c in json.load(open('public/data/categories.json', encoding='utf-8'))}
bus = json.load(open('public/data/bus.json', encoding='utf-8'))
from lavoratori import assign_all, centre_floors
W = assign_all(places)                               # lavoratori, piani e settore stimati (tools/lavoratori.py)
LOT_FLOORS, PLACE_FLOORS = centre_floors(lots, places, W)
for l in lots:
    if l['number'] in LOT_FLOORS:
        l['floors'] = LOT_FLOORS[l['number']]
for p in places:
    if p['id'] in PLACE_FLOORS:
        p['floors'] = PLACE_FLOORS[p['id']]

CAT_SHORT = {'com': 'commercio', 'ind': 'industria', 'art': 'artigianato', 'uff': 'uffici', 'pub': 'servizi-pubblici', 'agr': 'agricoltura', 'res': 'residenziale'}
USE_NAME = {'com': 'Commercio e ristorazione', 'ind': 'Industria e logistica', 'art': 'Artigianato', 'uff': 'Uffici',
            'pub': 'Servizi pubblici', 'agr': 'Agricoltura', 'res': 'Residenziale'}


def fmt(n):
    return f'{round(n):,}'.replace(',', '.')


def slug(s):
    s = s.lower().replace("'", '-').replace('à', 'a').replace('è', 'e').replace('é', 'e').replace('ì', 'i').replace('ò', 'o').replace('ù', 'u')
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')


def lot_link(n, quarter):
    return f'[[{VAULT_DIR}/{quarter}/Lotto {n}|Lotto {n}]]'


def quarter_link(q):
    return f'[[{VAULT_DIR}/{q}/{q}|{q}]]'


def note_link(title):
    return f'[[{VAULT_DIR}/{title}|{title}]]'


def yaml_str(s):
    return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"') + '"'


# ------------------------------------------------------------------ lotti confinanti (entro ~20 m, cioè dall'altra parte di una strada)
RES, X0, Y0, N = 2.5, -1000.0, -1500.0, 2800
index_of = {l['number']: i + 1 for i, l in enumerate(lots)}
img = Image.new('I', (N, N), 0)
d = ImageDraw.Draw(img)
for l in lots:
    for sub in re.split(r'[MZ]', l['path']):
        n = list(map(float, re.findall(r'-?\d+\.?\d*', sub)))
        if len(n) >= 6:
            d.polygon([((x - X0) / RES, (y - Y0) / RES) for x, y in zip(n[0::2], n[1::2])], fill=index_of[l['number']])
grid = np.array(img)
pairs = set()
for dx, dy in [(k, 0) for k in range(1, 9)] + [(0, k) for k in range(1, 9)]:
    a = grid[: N - dy, : N - dx]
    b = grid[dy:, dx:]
    m = (a > 0) & (b > 0) & (a != b)
    pairs |= set(zip(a[m].tolist(), b[m].tolist()))
number_of = {i: n for n, i in index_of.items()}
neighbours = collections.defaultdict(set)
for a, b in pairs:
    neighbours[number_of[a]].add(number_of[b])
    neighbours[number_of[b]].add(number_of[a])

# ------------------------------------------------------------------ dati per lotto
places_by_lot = collections.defaultdict(list)
for p in places:
    places_by_lot[p['lot']].append(p)
lot_by_n = {l['number']: l for l in lots}
stops_near = collections.defaultdict(list)
for s in bus['stops']:
    for l in lots:
        if math.dist((s['x'], s['y']), (l['label']['x'], l['label']['y'])) <= 400:
            stops_near[l['number']].append(s)
line_name = {l['id']: l['name'] for l in bus['lines']}
# media abitanti per villetta nei quartieri di villette (il centro ha palazzi, non villette)
houses = [l for l in lots if l['homes'] > 0 and l['quarter'] not in ('Centro', 'La Cerchia')]
villa_ratio = sorted(l['population'] / l['homes'] for l in houses)[len(houses) // 2]          # mediana per lotto
corti = [l for l in houses if l['quarter'] == 'Le Corti']
corti_ratio = sum(l['population'] for l in corti) / max(1, sum(l['homes'] for l in corti))


def lot_info(l):
    ps = places_by_lot.get(l['number'], [])
    workers = sum(W[p['id']][0] for p in ps)
    public = sum(W[p['id']][0] for p in ps if W[p['id']][2] == 'pubblico')
    by_cat = collections.Counter()
    for p in ps:
        by_cat[p['category']] += max(W[p['id']][0], 1)
    dominant = by_cat.most_common(1)[0][0] if by_cat else None
    if ps and (l['population'] > 0):
        use = f'Misto: residenziale e {USE_NAME[dominant].lower()}'
    elif ps:
        use = USE_NAME[dominant]
    elif l['population'] > 0:
        use = 'Residenziale (villette)' if l['homes'] > 0 else 'Residenziale (condomini)'
    else:
        use = "Senza destinazione d'uso"
    tags = ['citta-radiale', 'lotto', f"quartiere/{slug(l['quarter'])}"]
    if l['population'] > 0:
        tags.append('uso/residenziale')
    tags += [f'uso/{CAT_SHORT[c]}' for c in sorted(by_cat)]
    if use.startswith('Senza'):
        tags.append('senza-destinazione')
    if stops_near.get(l['number']):
        tags.append('servito-autobus')
    return dict(places=ps, workers=workers, public=public, use=use, tags=tags, by_cat=by_cat)


infos = {l['number']: lot_info(l) for l in lots}

# ------------------------------------------------------------------ pulizia delle note generate in precedenza
os.makedirs(OUT, exist_ok=True)
removed = 0
for dirpath, _, files in os.walk(OUT):
    for f in files:
        if f.endswith('.md'):
            fp = os.path.join(dirpath, f)
            with open(fp, encoding='utf-8') as fh:
                if MARK in fh.read(600):
                    os.remove(fp)
                    removed += 1


def write(rel, text):
    fp = os.path.join(OUT, rel)
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    with open(fp, 'w', encoding='utf-8') as fh:
        fh.write(text)


written = 0

# ------------------------------------------------------------------ note dei lotti
for l in lots:
    n, q = l['number'], l['quarter']
    info = infos[n]
    area = footprint(l['path'])
    fm = [
        '---', MARK, 'tipo: lotto', f'numero: {n}', f'quartiere: {yaml_str(quarter_link(q))}', f'uso: {yaml_str(info["use"])}',
        f'superficie_m2: {round(area)}', f'abitanti: {l["population"]}', f'edifici_residenziali: {l["homes"]}',
        f'edifici_con_funzione: {len(info["places"])}', f'lavoratori: {info["workers"]}', f'lavoratori_pubblici: {info["public"]}',
    ]
    if l.get('floors'):
        fm.append(f'piani_palazzi: {l["floors"]}')
    if stops_near.get(n):
        fm.append('fermate_autobus: [' + ', '.join(yaml_str(s['name']) for s in stops_near[n]) + ']')
    fm.append('tags: [' + ', '.join(info['tags']) + ']')
    fm.append('---')
    body = [f'# Lotto {n}', '',
            f'- **Quartiere:** {quarter_link(q)}',
            f'- **Destinazione d\'uso:** {info["use"]}',
            f'- **Superficie:** {fmt(area)} m²',
            f'- **Abitanti:** {fmt(l["population"])} · **edifici residenziali:** {l["homes"]}',
            f'- **Lavoratori (stima):** {fmt(info["workers"])}' + (f', di cui {fmt(info["public"])} dipendenti pubblici' if info['public'] else '')]
    if l.get('floors'):
        body.append(f'- **Piani dei palazzi abitati (stima):** {l["floors"]}')
    if info['places']:
        body += ['', '## Edifici', '', '| Edificio | Funzione | Piani | Lavoratori | Settore |', '|---|---|---:|---:|---|']
        for p in sorted(info['places'], key=lambda p: -W[p['id']][0]):
            w, fl, sec = W[p['id']]
            fl = p.get('floors', fl)
            name = p['name']
            body.append(f'| {name} | {categories[p["category"]]} | {fl} | {fmt(w)} | {sec} |')
    if stops_near.get(n):
        body += ['', '## Autobus entro 400 m', '']
        for s in stops_near[n]:
            body.append(f'- {s["name"]} · ' + ', '.join(line_name[i] for i in s['lines']))
    if neighbours.get(n):
        body += ['', '## Confina con', '']
        for m in sorted(neighbours[n]):
            body.append(f'- {lot_link(m, lot_by_n[m]["quarter"])}')
    write(f'{q}/Lotto {n}.md', '\n'.join(fm + [''] + body) + '\n')
    written += 1

# ------------------------------------------------------------------ note dei quartieri
qstats = {}
for qd in quarters:
    q = qd['name']
    ls = sorted((l for l in lots if l['quarter'] == q), key=lambda l: l['number'])
    workers = sum(infos[l['number']]['workers'] for l in ls)
    public = sum(infos[l['number']]['public'] for l in ls)
    pop = sum(l['population'] for l in ls)
    nplaces = sum(len(infos[l['number']]['places']) for l in ls)
    empty = [l for l in ls if infos[l['number']]['use'].startswith('Senza')]
    qstats[q] = dict(pop=pop, workers=workers, public=public, lots=len(ls), places=nplaces, rural=qd['rural'])
    fm = ['---', MARK, 'tipo: quartiere', f'nome: {yaml_str(q)}', f'abitanti: {pop}', f'lavoratori: {workers}',
          f'lavoratori_pubblici: {public}', f'lotti: {len(ls)}', f'edifici_residenziali: {sum(l["homes"] for l in ls)}',
          f'edifici_con_funzione: {nplaces}', f'lotti_senza_destinazione: {len(empty)}', f'rurale: {"true" if qd["rural"] else "false"}',
          f'tags: [citta-radiale, quartiere, quartiere/{slug(q)}' + (', campagna' if qd['rural'] else '') + ']', '---']
    ratio = f'{workers / pop:.2f}'.replace('.', ',') if pop else '—'
    body = [f'# {q}', '', f'- **Abitanti:** {fmt(pop)}', f'- **Lavoratori (stima):** {fmt(workers)} (dipendenti pubblici {fmt(public)})',
            f'- **Posti di lavoro per abitante:** {ratio}', f'- **Lotti:** {len(ls)} · **edifici con una funzione:** {nplaces}',
            f'- Torna a {note_link("Città radiale")}', '', '## Lotti', '',
            '| Lotto | Destinazione d\'uso | Abitanti | Lavoratori | Superficie m² |', '|---|---|---:|---:|---:|']
    for l in ls:
        i = infos[l['number']]
        use = i['use']
        body.append(f'| {lot_link(l["number"], q)} | {use} | {fmt(l["population"])} | {fmt(i["workers"])} | {fmt(footprint(l["path"]))} |')
    write(f'{q}/{q}.md', '\n'.join(fm + [''] + body) + '\n')
    written += 1

# ------------------------------------------------------------------ nota principale
tot_pop = sum(l['population'] for l in lots)
tot_jobs = sum(w for w, _, _ in W.values())                         # anche i 4 luoghi fuori dai lotti
tot_public = sum(w for w, _, s in W.values() if s == 'pubblico')
cat_count = collections.Counter(p['category'] for p in places)
cat_workers = collections.Counter()
for p in places:
    cat_workers[p['category']] += W[p['id']][0]
empty_now = [l for l in lots if infos[l['number']]['use'].startswith('Senza')]
fm = ['---', MARK, 'tipo: città', f'abitanti: {tot_pop}', f'lavoratori: {tot_jobs}', f'lavoratori_pubblici: {tot_public}',
      f'quartieri: {len(quarters)}', f'lotti: {len(lots)}', f'edifici_con_funzione: {len(places)}', f'aggiornato: {DATE}',
      'tags: [citta-radiale]', '---']
body = ['# Città radiale', '',
        f'Mappa di 7 × 7 km. Dati del progetto `citta-radiale-react`, aggiornati al {DATE}.', '',
        f'- **Abitanti:** {fmt(tot_pop)}',
        f'- **Posti di lavoro (stima):** {fmt(tot_jobs)}, di cui {fmt(tot_public)} dipendenti pubblici',
        f'- **Posti di lavoro per abitante:** {tot_jobs / tot_pop:.2f}'.replace('.', ','),
        f'- **Abitanti occupati (stima, {round(EMPLOYMENT_RATE * 100)}%):** {fmt(tot_pop * EMPLOYMENT_RATE)}',
        f'- **Lotti:** {len(lots)} · senza destinazione d\'uso: {len(empty_now)}',
        f'- **Edifici con una funzione:** {fmt(len(places))}', '',
        '## Note', '',
        f'- {note_link("Linee autobus")}', f'- {note_link("Piani in Centro e La Cerchia")}',
        f'- {note_link("Come sono stimati i lavoratori")}', '',
        '## Quartieri', '', '| Quartiere | Abitanti | Lavoratori | Posti per abitante | Lotti | Edifici |', '|---|---:|---:|---:|---:|---:|']
for q, s in sorted(qstats.items(), key=lambda kv: -kv[1]['pop']):
    ratio = f'{s["workers"] / s["pop"]:.2f}'.replace('.', ',') if s['pop'] else '—'
    body.append(f'| {quarter_link(q)} | {fmt(s["pop"])} | {fmt(s["workers"])} | {ratio} | {s["lots"]} | {s["places"]} |')
body += ['', '## Funzioni degli edifici', '', '| Categoria | Edifici | Lavoratori |', '|---|---:|---:|']
for c, label in categories.items():
    body.append(f'| {label} | {cat_count[c]} | {fmt(cat_workers[c])} |')
write('Città radiale.md', '\n'.join(fm + [''] + body) + '\n')
written += 1

# ------------------------------------------------------------------ linee autobus
stop_by_id = {s['id']: s for s in bus['stops']}
fm = ['---', MARK, 'tipo: trasporti', f'linee: {len(bus["lines"])}', f'fermate: {len(bus["stops"])}', 'tags: [citta-radiale, autobus]', '---']
body = ['# Linee autobus', '',
        f'{len(bus["lines"])} linee ad anello: partono dalla stazione centrale e ci tornano. '
        'Non ci sono stazioni di smistamento: le linee si incrociano alla stazione centrale e nelle fermate in comune. Frequenze e orari non sono stabiliti. I percorsi seguono le strade (vedi `tools/linee_autobus.py`).', '']
for line in bus['lines']:
    body += [f'## {line["name"]}', '', f'- **Percorso:** {line["description"]}', f'- **Lunghezza:** {line["lengthM"] / 1000:.1f} km'.replace('.', ','),
             f'- **Fermate:** {len(line["stops"])}', '']
    for k, sid in enumerate(line['stops'], 1):
        s = stop_by_id[sid]
        other = [line_name[i] for i in s['lines'] if i != line['id']]
        body.append(f'{k}. {s["name"]} · {quarter_link(s["quarter"])}' + (f' · cambio con {", ".join(other)}' if other else ''))
    body.append('')
write('Linee autobus.md', '\n'.join(fm + [''] + body) + '\n')
written += 1

# ------------------------------------------------------------------ piani in Centro e La Cerchia
def floor_stats(values):
    v = sorted(values)
    if not v:
        return '—'
    return f'{v[len(v) // 2]} (da {v[0]} a {v[-1]})'


fm = ['---', MARK, 'tipo: analisi', 'tags: [citta-radiale, piani]', '---']
body = ['# Piani in Centro e La Cerchia', '',
        "I dati della mappa danno l'altezza solo di 11 torri per uffici e di un hotel (è scritta nel nome). Tutti gli altri piani sono stime:", '',
        '- **Palazzi abitati:** piani = abitanti × 35 m² ÷ superficie costruibile del lotto (45% del lotto, meno metà degli edifici con una funzione), da 3 a 40.',
        '- **Negozi, bar, ristoranti:** stanno al piano terra di un palazzo abitato, che ha i piani delle case del suo lotto; '
        'grandi magazzini e gallerie 4 piani, parcheggi multipiano 5, hotel e torri dall\'altezza nel nome, altrimenti 1.', '',
        '| Quartiere | Palazzi abitati: piani (mediana, min–max) | Edifici commerciali: piani (mediana, min–max) | Edifici commerciali |', '|---|---|---|---:|']
for qn in ('Centro', 'La Cerchia'):
    res = [l['floors'] for l in lots if l['quarter'] == qn and l.get('floors')]
    com = [p['floors'] for p in places if p['quarter'] == qn and p['category'] == 'com' and p.get('floors')]
    body.append(f'| {quarter_link(qn)} | {floor_stats(res)} | {floor_stats(com)} | {len(com)} |')
body += ['', '## Palazzi abitati per lotto', '', '| Lotto | Quartiere | Abitanti | Piani (stima) |', '|---|---|---:|---:|']
for l in sorted((l for l in lots if l.get('floors')), key=lambda l: (l['quarter'], l['number'])):
    body.append(f'| {lot_link(l["number"], l["quarter"])} | {l["quarter"]} | {fmt(l["population"])} | {l["floors"]} |')
body += ['', '## Edifici commerciali', '', '| Edificio | Lotto | Quartiere | Piani |', '|---|---|---|---:|']
for p in sorted((p for p in places if p['quarter'] in ('Centro', 'La Cerchia') and p['category'] == 'com'), key=lambda p: (p['quarter'], -p.get('floors', 1), p['name'])):
    body.append(f'| {p["name"]} | {lot_link(p["lot"], p["quarter"]) if p["lot"] else "—"} | {p["quarter"]} | {p.get("floors", 1)} |')
write('Piani in Centro e La Cerchia.md', '\n'.join(fm + [''] + body) + '\n')
written += 1

# ------------------------------------------------------------------ metodo dei lavoratori
fm = ['---', MARK, 'tipo: metodo', 'tags: [citta-radiale]', '---']
body = ['# Come sono stimati i lavoratori', '',
        'I dati della mappa non hanno il numero di addetti. La stima, in `tools/lavoratori.py`, è:', '',
        '> lavoratori = impronta dell\'edificio × piani ÷ metri quadri per addetto', '',
        '- I piani dipendono dal tipo: le torri hanno l\'altezza nel nome (150 m ≈ 43 piani), gli uffici generici 2 piani (4 in Centro e La Cerchia), '
        'l\'ospedale 4, le scuole 2.',
        '- Metri quadri per addetto: uffici 15–18, uffici pubblici 20, ospedale 30, ristorazione 25, negozi 40, grande distribuzione 60, '
        'scuole 80, industria 70, logistica 120, data center 250.',
        '- Silos, serbatoi, tettoie, pensiline e campi sportivi non hanno addetti fissi; stadio, vigili del fuoco, depuratori hanno un numero fisso.',
        '- I complessi (campus, ospedale, fiera) contengono altri edifici: si conta solo la parte libera, e un quarto di quella.',
        '- **Dipendenti pubblici**: sanità, scuole, università, uffici statali e comunali, polizia, vigili del fuoco, dogana, uffici aeroportuali.', '',
        'Sono valori medi da manuale: il totale può variare di ±30% cambiando le ipotesi.']
write('Come sono stimati i lavoratori.md', '\n'.join(fm + [''] + body) + '\n')
written += 1

print(f'note scritte: {written} in {OUT} (rimosse {removed} generate in precedenza)')
print(f'abitanti per edificio: villette {villa_ratio:.2f}, Le Corti {corti_ratio:.0f}')
