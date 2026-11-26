# La Cerchia: 100 edifici (99 e il Duomo, che resta com'è), ognuno con la destinazione d'uso di ogni piano e le imprese
# che li occupano; quello che avanza resta libero.
#
#   python3 tools/cerchia.py          scrive gli edifici di La Cerchia in places.json e gli abitanti in lots.json e
#                                     quarters.json; poi si lanciano tools/censimento.py e tools/disegna_satellite.py
#   python3 tools/cerchia.py --prova  stampa edificio per edificio misure, abitanti e posti di lavoro, senza scrivere nulla
#
# La Cerchia resta com'è nella foto satellitare: i suoi edifici sono gli edifici della foto. tools/cerchia_tetti.json ha
# i tetti della foto, ognuno col suo lotto e i piani che vengono dalla sua ombra (più è lunga, più l'edificio è alto).
# PROGRAMMA dice quali edifici ci sono in ogni lotto e cosa c'è ai loro piani; ogni edificio prende un gruppo di tetti
# vicini del suo lotto, ha tanti piani quanti il suo tetto più alto, e i piani del programma si ridistribuiscono su
# quell'altezza (il piano terra resta com'è). Le regole (coefficienti, imprese) sono quelle di tools/centro.py.
import json, math, os, sys

from shapely.geometry import Polygon
from shapely import affinity

import centro
from centro import E, CASA_NEGOZI, SOLO_CASA

QUARTIERE = 'La Cerchia'
ID_BASE = 3000
# luoghi che restano come sono: Biglietteria e pensiline della stazione, Duomo e sagrato, padiglioni e Cittadella dei
# servizi pubblici nel parco, i due parchi pubblici
RESTANO = {280, 786, 829, 830, 831, 344, 599, 552, 659, 1842, 1844}

FACCIATE_CASA = ['intonaco_caldo', 'intonaco_chiaro', 'mattone', 'intonaco_chiaro', 'pietra']
TETTI_CASA = ['ghiaia', 'chiaro', 'scuro', 'solare', 'ghiaia', 'verde']
_n = [0]


def CASA(lotto, parte, parti, piani, negozi=None, nome='Palazzo residenziale'):
    """Un palazzo residenziale: se ha `negozi` (una lista di nomi, anche vuota), il piano terra è di negozi."""
    i = _n[0]
    _n[0] += 1
    p = CASA_NEGOZI(piani) if negozi is not None else SOLO_CASA(piani)
    return E(lotto, parte, nome, 'res', 'palazzina', p, FACCIATE_CASA[i % 5], TETTI_CASA[i % 6], parti=parti,
             negozi=negozi or None)


def UFFICI(lotto, parte, parti, piani, uffici=None, negozi=None, facciata='vetro_grigio', tetto='chiaro',
           nome='Palazzo per uffici', forma='palazzina', dimensioni=(56, 26)):
    """Un palazzo per uffici: piano terra di negozi, sopra uffici (con le imprese `uffici`, o divisi in aziende)."""
    return E(lotto, parte, nome, 'uff', forma, [(1, 'negozi', 'Negozi e bar'), (piani - 1, 'uffici', 'Uffici')],
             facciata, tetto, parti=parti, uffici=uffici, negozi=negozi, dimensioni=dimensioni)


def PARCHEGGIO(lotto, parte, parti, piani=5):
    return E(lotto, parte, 'Parcheggio multipiano', 'com', 'palazzina', [(piani, 'parcheggio', 'Parcheggio multipiano')],
             'intonaco_chiaro', 'ghiaia', parti=parti, dimensioni=(50, 32))


PROGRAMMA = [
    # ------------------------------------------------ lotto 39: professioni, associazioni
    UFFICI(39, 1, 4, 5, nome='Palazzo delle professioni', facciata='pietra', negozi=['Cinema'],
           uffici=['Studio legale', 'Studio notarile', 'Studio legale associato', 'Commercialista',
                   'Studio commercialista', 'Ordine degli avvocati']),
    E(39, 2, 'Casa delle associazioni', 'pub', 'palazzina',
      [(1, 'associazioni', 'Associazioni'), (4, 'casa', 'Abitazioni')], 'intonaco_caldo', 'ghiaia', parti=4,
      associazioni=['Associazione dei consumatori', 'Casa delle associazioni', 'Associazione di volontariato']),
    CASA(39, 3, 4, 6),
    PARCHEGGIO(39, 4, 4),
    # ------------------------------------------------ lotti 40-44: case con negozi, cinema, teatro
    E(40, 0, 'Palazzo per uffici e abitazioni', 'res', 'palazzina',
      [(1, 'negozi', 'Negozi e bar'), (1, 'uffici', 'Uffici'), (3, 'casa', 'Abitazioni')], 'intonaco_chiaro', 'ghiaia'),
    CASA(41, 0, None, 5, negozi=['Banca', 'Farmacia', 'Gelateria', 'Enoteca', 'Bar', 'Libreria']),
    E(42, 1, 'Multisala e bowling', 'com', 'palazzina',
      [(1, 'negozi', 'Bowling, ristorante e bar'), (3, 'cinema', 'Cinema multisala')], 'pietra', 'chiaro', parti=2,
      dimensioni=(56, 30),
      negozi=['Sala bowling', 'Ristorante', 'Bar', 'Chiosco bar']),
    CASA(42, 2, 2, 5, negozi=['Libreria', 'Centro benessere', 'Libreria', 'Ristorante', 'Caffetteria', 'Pub']),
    E(43, 0, 'Teatro comunale', 'pub', 'palazzina',
      [(2, 'cultura', 'Teatro comunale: platea e palcoscenico'), (2, 'cultura', 'Teatro comunale: palchi e laboratori')],
      'pietra', 'scuro', dimensioni=(56, 32)),
    CASA(44, 1, 2, 5, negozi=['Ristorante', 'Sala giochi']),
    CASA(44, 2, 2, 6),
    # ------------------------------------------------ lotti 46-50
    UFFICI(46, 1, 2, 7, dimensioni=(60, 30)),
    CASA(46, 2, 2, 6),
    E(47, 1, 'Centro giovanile e palestra', 'pub', 'palazzina',
      [(2, 'cultura', 'Palestra'), (2, 'cultura', 'Centro giovanile')], 'intonaco_chiaro', 'verde', parti=5),
    UFFICI(47, 2, 5, 7, facciata='vetro_blu', dimensioni=(60, 30)),
    CASA(47, 3, 5, 6),
    CASA(47, 4, 5, 5),
    PARCHEGGIO(47, 5, 5),
    E(48, 1, 'Hotel', 'com', 'torre', [(1, 'hotel', 'Hall e ristorante'), (11, 'hotel', 'Hotel')], 'vetro_verde',
      'piscina', parti=3, dimensioni=(40, 34)),
    PARCHEGGIO(48, 2, 3),
    CASA(48, 3, 3, 6),
    UFFICI(49, 1, 2, 5, nome='Palazzo degli studi tecnici', facciata='pietra', tetto='solare',
           uffici=['Studio di progettazione navale', 'Studio di architettura', 'Studio di ingegneria acustica',
                   'Studio di progettazione stradale', 'Studio di interior design', 'Studio di rendering 3D',
                   'Studio geologico', 'Studio di topografia', 'Studio di progettazione elettrica',
                   'Studio di certificazione energetica', 'Studio di progettazione di giardini']),
    CASA(49, 2, 2, 6),
    E(50, 0, 'Palazzo per uffici e abitazioni', 'res', 'palazzina',
      [(1, 'negozi', 'Negozi'), (1, 'uffici', 'Uffici'), (3, 'casa', 'Abitazioni')], 'mattone', 'ghiaia',
      negozi=['Concept store']),
    # ------------------------------------------------ lotti 52-57: scuole, uffici comunali, polo tecnico-scientifico
    E(52, 0, 'Scuola primaria', 'pub', 'palazzina', [(4, 'scuola', 'Scuola primaria')], 'intonaco_caldo', 'solare',
      corte='giardino', dimensioni=(56, 28)),
    UFFICI(53, 0, None, 4, nome='Palazzina uffici', dimensioni=(30, 20)),
    E(54, 0, 'Uffici comunali di quartiere', 'pub', 'palazzina',
      [(1, 'sportelli', 'Uffici comunali: sportelli'), (2, 'sportelli', 'Uffici comunali'),
       (1, 'sportelli', 'Sale civiche')], 'pietra', 'chiaro', dimensioni=(54, 28)),
    E(55, 1, 'Centro tecnico-scientifico', 'uff', 'palazzina', [(7, 'sede', 'Centro tecnico-scientifico')], 'vetro_blu',
      'solare', parti=10, dimensioni=(60, 30)),
    UFFICI(55, 2, 2, 7, dimensioni=(60, 30)),
    UFFICI(56, 1, 3, 7, dimensioni=(60, 30)),
    CASA(56, 2, 3, 5, negozi=['Bistrot']),
    CASA(56, 3, 3, 5),
    E(57, 0, "Scuola dell'infanzia e scuole d'arte", 'pub', 'palazzina',
      [(2, 'scuola', "Scuola dell'infanzia"), (1, 'scuola', 'Scuola di musica'), (1, 'scuola', 'Scuola di danza')],
      'intonaco_caldo', 'verde', corte='giardino'),
    # ------------------------------------------------ lotti 58-63
    UFFICI(58, 1, 4, 7, facciata='vetro_verde', dimensioni=(60, 30)),
    CASA(58, 2, 4, 6),
    CASA(58, 3, 4, 5),
    CASA(58, 4, 4, 5),
    CASA(59, 0, None, 6),
    E(60, 0, 'Torre per uffici', 'uff', 'torre', [(1, 'negozi', 'Negozi e bar'), (9, 'uffici', 'Uffici')], 'vetro_blu',
      'solare', dimensioni=(40, 34)),
    UFFICI(61, 1, 3, 5, nome='Palazzo degli studi tecnici', facciata='vetro_grigio', tetto='solare',
           uffici=['Studio di ingegneria civile', 'Studio di architettura del paesaggio', 'Studio di design industriale',
                   'Studio di progettazione impianti', 'Studio di ingegneria strutturale', 'Studio di urbanistica']),
    CASA(61, 2, 3, 6),
    CASA(61, 3, 3, 5),
    E(62, 1, 'Laboratori artigiani', 'com', 'palazzina', [(3, 'laboratorio', 'Laboratori'), (1, 'uffici', 'Uffici tecnici')],
      'mattone', 'solare', parti=2, dimensioni=(54, 28), laboratori=['Minuteria metallica', 'Impianti elettrici'], uffici=['Uffici tecnici']),
    CASA(62, 2, 2, 5),
    E(63, 1, 'Fabbrica verticale', 'com', 'palazzina', [(4, 'laboratorio', 'Laboratori di produzione')], 'intonaco_chiaro',
      'solare', parti=3, dimensioni=(60, 30),
      laboratori=['Etichette e packaging', 'Caseificio industriale', 'Lavanderia industriale', 'Laboratorio prove']),
    E(63, 2, 'Palazzina uffici e showroom', 'uff', 'palazzina', [(1, 'showroom', 'Showroom'), (3, 'uffici', 'Uffici')],
      'vetro_grigio', 'chiaro', parti=3),
    CASA(63, 3, 3, 5),
    # ------------------------------------------------ lotti 65-69
    E(65, 1, 'Scuola media', 'pub', 'palazzina', [(4, 'scuola', 'Scuola media')], 'mattone', 'solare',
      corte='giardino', dimensioni=(60, 30)),
    CASA(66, 0, None, 4, negozi=['Bar']),
    E(67, 1, 'Cavi e cablaggi', 'com', 'palazzina', [(2, 'laboratorio', 'Produzione'), (2, 'laboratorio', 'Magazzino e uffici')],
      'intonaco_chiaro', 'ghiaia', parti=2, laboratori=['Cavi e cablaggi']),
    E(68, 1, 'Laboratori artigiani', 'com', 'palazzina',
      [(1, 'ristorante', 'Mensa aziendale'), (3, 'laboratorio', 'Laboratori')], 'mattone', 'ghiaia', parti=3,
      dimensioni=(54, 28),
      laboratori=['Arredo per ufficio', 'Ceramista', 'Officina moto', 'Serramentista', 'Laboratorio orafo',
                  'Studio di ingegneria idraulica']),
    CASA(68, 2, 3, 5),
    CASA(68, 3, 3, 6),
    CASA(69, 1, 3, 5, negozi=['Pasticceria']),
    CASA(69, 2, 3, 6),
    CASA(69, 3, 3, 5),
    # ------------------------------------------------ lotti 70-74
    UFFICI(70, 0, None, 5, facciata='pietra', negozi=['Profumeria', 'Agenzia di viaggi'],
           uffici=['Società di servizi finanziari', 'Centro di calcolo', 'Studio di grafica', 'Agenzia di traduzioni',
                   "Agenzia per l'energia"]),
    E(71, 1, 'Caserma dei vigili del fuoco', 'pub', 'palazzina', [(4, 'sicurezza', 'Vigili del fuoco')], 'mattone', 'ghiaia',
      parti=2, dimensioni=(50, 26), spazio_tetto='Torre di addestramento'),
    E(71, 2, 'Comando della Polizia locale', 'pub', 'palazzina', [(4, 'sicurezza', 'Polizia locale')], 'pietra', 'chiaro',
      parti=2, dimensioni=(50, 26)),
    CASA(72, 0, None, 5, negozi=['Libreria', 'Gioielleria']),
    E(73, 0, 'Accademia di belle arti', 'pub', 'palazzina',
      [(1, 'negozi', 'Caffè letterario'), (2, 'scuola', 'Accademia di belle arti'), (1, 'cultura', 'Sala prove musicali'),
       (2, 'studentato', 'Residenza per studenti')], 'mattone', 'verde', negozi=['Caffè letterario']),
    CASA(74, 1, 2, 5),
    UFFICI(74, 2, 2, 7, facciata='pietra', dimensioni=(60, 30)),
    # ------------------------------------------------ lotti 76-81
    UFFICI(76, 1, 2, 7, facciata='vetro_verde',
           uffici=['Uffici di una società di logistica', 'Studio di consulenza ambientale', 'Compagnia di navigazione',
                   'Società di ricerche di mercato', "Uffici di un'azienda di moda"]),
    CASA(76, 2, 2, 6),
    UFFICI(77, 1, 3, 7, dimensioni=(60, 30)),
    CASA(77, 2, 3, 5),
    CASA(77, 3, 3, 5),
    CASA(79, 0, None, 5),
    UFFICI(80, 0, None, 7, facciata='vetro_blu', dimensioni=(60, 30)),
    E(81, 1, 'Questura', 'pub', 'palazzina', [(5, 'sicurezza', 'Questura')], 'pietra', 'ghiaia', dimensioni=(60, 28)),
    # ------------------------------------------------ lotti 82-90
    UFFICI(82, 1, 2, 9, facciata='vetro_blu', tetto='solare',
           uffici=['Società di formazione', 'Agenzia di marketing', 'Studio di consulenza fiscale',
                   'Agenzia di lavoro interinale', 'Uffici di una compagnia aerea', 'Sede regionale di una banca',
                   'Agenzia di pratiche auto', 'Società di vigilanza', "Uffici di un'azienda farmaceutica"]),
    CASA(82, 2, 2, 6),
    UFFICI(83, 1, 4, 8, facciata='pietra',
           uffici=['Agenzia di assicurazioni', 'Società di trasporti', "Centro servizi per l'export",
                   'Uffici di una cooperativa', 'Sede di una catena di supermercati', 'Società di gestione immobiliare',
                   'Consulente del lavoro']),
    PARCHEGGIO(83, 2, 4),
    CASA(83, 3, 4, 5, negozi=['Agenzia immobiliare']),
    CASA(83, 4, 4, 5),
    UFFICI(84, 0, None, 5, facciata='pietra', negozi=["Galleria d'arte", 'Agenzia immobiliare'],
           uffici=['Banca', 'Assicurazioni', 'Sede di una casa editrice', 'Agenzia di traduzioni']),
    CASA(85, 0, None, 5, negozi=['Cioccolateria', 'Abbigliamento', 'Bar']),
    UFFICI(86, 1, 3, 8, facciata='vetro_verde',
           uffici=['Società energetica', 'Agenzia di stampa', 'Società di telecomunicazioni', 'Redazione di un quotidiano',
                   'Ufficio brevetti', 'Società di consulenza informatica', 'Sede di una banca']),
    E(86, 2, 'Palazzo residenziale', 'res', 'palazzina', [(1, 'cultura', 'Fondazione culturale'), (4, 'casa', 'Abitazioni')],
      'pietra', 'ghiaia', parti=3),
    CASA(86, 3, 3, 5),
    E(87, 0, 'Polo sanitario', 'pub', 'palazzina',
      [(1, 'negozi', 'Farmacia e studio dentistico'), (1, 'sanita', 'Centro cardiologico'),
       (1, 'sanita', 'Poliambulatorio specialistico'), (1, 'sanita', 'Centro oculistico e studio pediatrico')],
      'intonaco_chiaro', 'chiaro', negozi=['Farmacia', 'Studio dentistico']),
    E(88, 0, 'Centro diagnostico', 'pub', 'palazzina',
      [(1, 'sanita', 'Laboratorio analisi'), (1, 'sanita', 'Centro diagnostico per immagini'),
       (1, 'sanita', 'Poliambulatorio'), (1, 'sanita', 'Centro di fisioterapia')], 'intonaco_chiaro', 'solare'),
    E(89, 0, 'Palazzo per uffici', 'uff', 'palazzina', [(1, 'associazioni', 'Patronato e associazioni'), (5, 'uffici', 'Uffici')],
      'vetro_grigio', 'chiaro', associazioni=['Patronato', 'Associazione di categoria'], dimensioni=(56, 26),
      uffici=['Emittente radiofonica', 'Società di consulenza aziendale', 'Agenzia per il lavoro',
              'Centro elaborazione dati']),
    E(90, 0, 'Palazzo per uffici e abitazioni', 'res', 'palazzina',
      [(1, 'negozi', 'Negozi'), (3, 'uffici', 'Uffici'), (2, 'casa', 'Abitazioni')], 'intonaco_caldo', 'ghiaia',
      negozi=['Agenzia di viaggi'], uffici=['Studio fotografico', 'Società di revisione contabile']),
    # ------------------------------------------------ case nei lotti dove la foto ha più edifici del programma
    CASA(40, 9, None, 5), CASA(41, 9, None, 5), CASA(50, 9, None, 5), CASA(59, 9, None, 5), CASA(60, 9, None, 5),
    CASA(69, 9, None, 5), CASA(70, 9, None, 5), CASA(73, 9, None, 5), CASA(84, 9, None, 5), CASA(86, 9, None, 5),
    CASA(87, 9, None, 5), CASA(88, 9, None, 5), CASA(89, 9, None, 5),
    # ------------------------------------------------ il Duomo resta com'è
    E(64, 0, 'Duomo', 'pub', 'esistente', [(1, 'culto', 'Duomo')], luogo=599),
]


C0 = centro.C0


def _ordine(c):
    """In senso orario attorno alla piazza, poi dal centro verso fuori (come le parti dei lotti)."""
    a = (math.atan2(c[1] - C0[1], c[0] - C0[0]) + math.pi / 2) % (2 * math.pi)
    return (round(a, 1), math.dist(c, C0))


def _gruppi(tetti, k):
    """Divide i tetti di un lotto in k gruppi di tetti vicini (k-medie sui centri, partendo dai più lontani tra loro);
    nessun gruppo resta vuoto."""
    pts = [t['c'] for t in tetti]
    centri = [max(pts, key=lambda p: math.dist(p, pts[0]))]
    while len(centri) < k:
        centri.append(max(pts, key=lambda p: min(math.dist(p, c) for c in centri)))
    for _ in range(20):
        g = [[] for _ in range(k)]
        for t in tetti:
            g[min(range(k), key=lambda i: math.dist(t['c'], centri[i]))].append(t)
        for i in range(k):                               # un gruppo vuoto prende il tetto più vicino di un gruppo grande
            if not g[i]:
                j = max(range(k), key=lambda j: len(g[j]))
                t = min(g[j], key=lambda t: math.dist(t['c'], centri[i]))
                g[j].remove(t)
                g[i].append(t)
        nuovi = [(sum(t['c'][0] for t in x) / len(x), sum(t['c'][1] for t in x) / len(x)) for x in g]
        if nuovi == centri:
            break
        centri = nuovi
    return sorted(g, key=lambda x: _ordine((sum(t['c'][0] for t in x) / len(x), sum(t['c'][1] for t in x) / len(x))))


def riscala(piani, n):
    """I piani del programma ridistribuiti su n piani: il piano terra (se è un piano solo) resta, gli altri gruppi si
    allungano o si accorciano in proporzione, almeno un piano ciascuno."""
    fisso = piani[:1] if len(piani) > 1 and piani[0][0] == 1 else []
    resto = piani[len(fisso):]
    m = n - len(fisso)
    tot = sum(c for c, _, _ in resto)
    quote = [c * m / tot for c, _, _ in resto]
    conti = [max(1, math.floor(q)) for q in quote]
    while sum(conti) < m:                                # i piani che mancano ai gruppi con il resto più grande
        i = max(range(len(conti)), key=lambda i: quote[i] - conti[i])
        conti[i] += 1
    while sum(conti) > m:
        i = max((i for i in range(len(conti)) if conti[i] > 1), key=lambda i: conti[i] - quote[i])
        conti[i] -= 1
    return fisso + [(c, t, w) for c, (_, t, w) in zip(conti, resto)]


def programma():
    """Il PROGRAMMA con gli edifici della foto: ogni edificio prende i suoi tetti e i suoi piani."""
    dati = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cerchia_tetti.json'), encoding='utf-8'))
    per_lotto = {}
    for t in dati['tetti']:
        g = Polygon(t['contorno'])
        base = affinity.translate(g, 0, t['piani'] * centro.ALTEZZA_PIANO * centro.PROSPETTIVA)
        per_lotto.setdefault(t['lotto'], []).append(dict(t, g=g, c=(base.centroid.x, base.centroid.y)))
    out = []
    lotti = {}
    for e in PROGRAMMA:
        lotti.setdefault(e['lotto'], []).append(e)
    for n, es in lotti.items():
        nuovi = [e for e in es if e['forma'] != 'esistente']
        out += [e for e in es if e['forma'] == 'esistente']
        if not nuovi:
            continue
        tetti = per_lotto.get(n, [])
        if len(tetti) < len(nuovi):
            raise SystemExit(f'lotto {n}: {len(nuovi)} edifici nel programma ma solo {len(tetti)} tetti nella foto')
        # il gruppo di tetti più grande all'edificio che ne ha più bisogno: prima quelli con imprese da sistemare (più
        # imprese, prima), poi gli altri edifici con una funzione, per ultime le case
        gruppi = sorted(_gruppi(tetti, len(nuovi)), key=lambda g: -sum(t['g'].area * t['piani'] for t in g))
        bisogno = lambda e: (sum(len(e[k] or []) for k in ('uffici', 'negozi', 'laboratori', 'associazioni')),
                             e['cat'] != 'res', -e['parte'])
        coppie = sorted(zip(sorted(nuovi, key=bisogno, reverse=True), gruppi), key=lambda c: _ordine(
            (sum(t['c'][0] for t in c[1]) / len(c[1]), sum(t['c'][1] for t in c[1]) / len(c[1]))))
        for i, (e, g) in enumerate(coppie):
            piani = max(t['piani'] for t in g)
            out.append(dict(e, parte=i + 1 if len(nuovi) > 1 else 0, parti=None, forma='foto',
                            tetti=[(t['g'], t['piani']) for t in g], piani=riscala(e['piani'], piani)))
    return out


def edifici():
    return centro.edifici(programma(), QUARTIERE, ID_BASE, RESTANO)


if __name__ == '__main__':
    if '--prova' in sys.argv:
        centro.prova(edifici())
    else:
        centro.scrivi(edifici(), QUARTIERE, RESTANO)
