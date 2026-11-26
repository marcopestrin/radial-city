# Fogli Excel e CSV del censimento, dai JSON scritti da tools/censimento.py.
#
#   python3 tools/censimento.py        prima i JSON
#   python3 tools/censimento_xlsx.py   poi i fogli
#
# public/data/censimento_piani.xlsx   fogli "Edifici" (una riga per edificio), "Piani" (una riga per azienda di ogni piano:
#                                     linea spessa tra gli edifici, sottile tra i piani, piani e aziende indentati) e
#                                     "Spazi aperti"
# public/data/censimento_villette.xlsx  una riga per villetta (le villette non sono nel censimento principale)
# public/data/censimento.csv, censimento_piani.csv   gli stessi dati degli edifici e dei piani, in CSV
# Serve openpyxl (pip install openpyxl).
import csv, json, os

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'public', 'data')

COLONNE_PIANI = ['codice', 'nome', 'quartiere', 'zona', 'lotto', 'piano', 'attivita', 'destinazione_uso',
                 'superficie_m2', 'stato', 'alloggi', 'abitanti', 'camere', 'posti_totali', 'posti_occupati',
                 'posti_liberi', 'imprese', 'ramo_aziende', 'aziende_elenco', 'luogo']
LARGHEZZE_PIANI = [11, 34, 18, 18, 7, 7, 26, 18, 13, 22, 9, 9, 8, 12, 13, 11, 9, 40, 60, 8]
INTESTAZIONE = PatternFill('solid', fgColor='1F2937')
FASCE = [PatternFill('solid', fgColor='EAF1FB'), PatternFill('solid', fgColor='FFFFFF')]
STATO = {'libero': 'F8D7DA', 'parzialmente occupato': 'FFF3CD'}
SPESSA = Side(style='thick', color='000000')


def intestazione(ws, colonne, larghezze):
    ws.append(colonne)
    for c in ws[1]:
        c.font = Font(bold=True, color='FFFFFF')
        c.fill = INTESTAZIONE
        c.alignment = Alignment(vertical='center')
    for k, w in enumerate(larghezze, 1):
        ws.column_dimensions[get_column_letter(k)].width = w


def righe_piani(edifici):
    """Una riga per piano: (indice dell'edificio, riga)."""
    out = []
    for bi, x in enumerate(edifici):
        ramo = {(a['azienda'], pi): a['ramo'] for a in x['aziende'] for pi in a['piani']}
        for p in x['piani']:
            occ, lib = p['posti_di_lavoro'], p.get('posti_liberi', 0)
            stato = 'libero' if p['attivita'] == 'Spazio libero' else ('parzialmente occupato' if lib > 0 and occ > 0 else 'occupato')
            az = p.get('aziende', [])
            out.append((bi, [x['codice'], x['nome'], x['quartiere'], x['zona'], x['lotto'] or '', p['piano'], p['attivita'],
                             p['destinazione_uso'], p['superficie_m2'], stato, p['alloggi'],
                             p['abitanti'], p.get('camere', ''), occ + lib, occ, lib, p['imprese'],
                             ' | '.join(ramo.get((a['azienda'], p['piano'])) or p['attivita'] for a in az),
                             ' | '.join(f"{a['azienda']} ({a['dipendenti']})" for a in az),
                             ';'.join(map(str, x['luoghi']))]))
    return out


def riga_edificio(x, scalari):
    acts = []
    for p in x['piani']:
        if p.get('attivita') and p['attivita'] not in acts:
            acts.append(p['attivita'])
    az = x['aziende']
    return [x[k] if x[k] is not None else '' for k in scalari] + [
        ';'.join(map(str, x['luoghi'])), ' | '.join(acts), sum(p.get('camere', 0) for p in x['piani']),
        len(az), sum(a['dipendenti'] for a in az), ' | '.join(a['ramo'] or '' for a in az if a['ramo']),
        ' | '.join(f"{a['azienda']} ({a['ramo'] or '—'}, {a['dipendenti']})" for a in az)]


def main():
    d = json.load(open(os.path.join(DATA, 'censimento.json'), encoding='utf-8'))
    edifici = d['edifici']
    piani = righe_piani(edifici)

    scalari = [k for k, v in edifici[0].items() if not isinstance(v, (list, dict))]
    extra = ['luoghi', 'attivita_elenco', 'camere', 'n_aziende', 'dipendenti_aziende', 'ramo_aziende', 'aziende_elenco']
    with open(os.path.join(DATA, 'censimento.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(scalari + extra)
        for x in edifici:
            w.writerow(riga_edificio(x, scalari))
    with open(os.path.join(DATA, 'censimento_piani.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(COLONNE_PIANI)
        w.writerows(r for _, r in piani)

    wb = Workbook()
    # --- Edifici
    ws = wb.active
    ws.title = 'Edifici'
    intestazione(ws, scalari + extra, [11, 34, 18, 18, 7, 18, 24, 10, 13, 8, 10, 13, 9, 9, 9, 9, 9, 9, 9, 9, 9, 8, 9, 9, 8, 8, 14, 12, 40, 60, 60][:len(scalari) + len(extra)])
    for x in edifici:
        ws.append(riga_edificio(x, scalari))
    ws.freeze_panes = 'C2'
    ws.auto_filter.ref = ws.dimensions

    # --- Piani: edificio > piano > azienda. Una riga per azienda di ogni piano (i dati del piano stanno sulla prima riga
    # del piano); linea spessa tra gli edifici, sottile tra i piani; piano indentato di uno, azienda di due
    ws = wb.create_sheet('Piani')
    col = COLONNE_PIANI[:17] + ['ramo', 'azienda', 'dipendenti', 'luogo']
    intestazione(ws, col, LARGHEZZE_PIANI[:17] + [34, 34, 11, 8])
    sottile = Side(style='thin', color='7F7F7F')
    grigio = Font(color='9CA3AF')
    i = 1
    for bi, x in enumerate(edifici):
        ramo = {(a['azienda'], pi): a['ramo'] for a in x['aziende'] for pi in a['piani']}
        luogo = ';'.join(map(str, x['luoghi']))
        luogo_az = {az['azienda']: az.get('luogo') for az in x['aziende']}     # il perimetro di ogni impresa
        for pi_, p in enumerate(x['piani']):
            occ, lib = p['posti_di_lavoro'], p.get('posti_liberi', 0)
            stato = 'libero' if p['attivita'] == 'Spazio libero' else ('parzialmente occupato' if lib > 0 and occ > 0 else 'occupato')
            az = p.get('aziende', [])
            if not az and occ > 0:                         # piano con un'attività sola, senza imprese elencate (hotel, negozi...)
                az = [{'azienda': p['attivita'], 'dipendenti': occ, '_ramo': p['destinazione_uso']}]
            az = az or [None]
            for k, a in enumerate(az):
                i += 1
                prima_edificio, prima_piano = pi_ == 0 and k == 0, k == 0
                if prima_piano:
                    riga = [x['codice'], x['nome'], x['quartiere'], x['zona'], x['lotto'] or '', p['piano'], p['attivita'],
                            p['destinazione_uso'], p['superficie_m2'], stato, p['alloggi'],
                            p['abitanti'], p.get('camere', ''), occ + lib, occ, lib, p['imprese']]
                else:                                      # altra azienda dello stesso piano: solo i suoi dati
                    riga = [x['codice'], x['nome'], x['quartiere'], x['zona'], x['lotto'] or '', p['piano']] + [''] * 11
                riga += [(a.get('_ramo') or ramo.get((a['azienda'], p['piano'])) or p['attivita']) if a else '',
                         a['azienda'] if a else '', a['dipendenti'] if a else '',
                         (luogo_az.get(a['azienda']) if a and luogo_az.get(a['azienda']) is not None else luogo)]
                ws.append(riga)
                for c in ws[i]:
                    c.fill = FASCE[bi % 2]
                    if prima_edificio:
                        c.font = Font(bold=True)
                        c.border = Border(top=SPESSA)
                    elif prima_piano:
                        c.border = Border(top=sottile)
                if not prima_piano:                        # le celle ripetute per poter filtrare restano in grigio
                    for j in range(1, 7):
                        ws.cell(i, j).font = grigio
                ws.cell(i, 1).alignment = Alignment(indent=0 if prima_edificio else (1 if prima_piano else 2))
                ws.cell(i, 2).alignment = Alignment(indent=0 if prima_edificio else (1 if prima_piano else 2))
                ws.cell(i, 19).alignment = Alignment(indent=1)
                if prima_piano and stato in STATO:
                    ws.cell(i, 11).fill = PatternFill('solid', fgColor=STATO[stato])
    ws.freeze_panes = 'C2'
    ws.auto_filter.ref = ws.dimensions

    # --- Spazi aperti
    ws = wb.create_sheet('Spazi aperti')
    col = ['codice', 'nome', 'quartiere', 'lotto', 'luogo', 'tipo', 'superficie_m2', 'posti_di_lavoro', 'abitanti']
    intestazione(ws, col, [11, 34, 22, 7, 8, 26, 14, 15, 10])
    for s in d['spazi_aperti']:
        ws.append([s[k] if s.get(k) is not None else '' for k in col])
    ws.freeze_panes = 'C2'
    ws.auto_filter.ref = ws.dimensions
    wb.save(os.path.join(DATA, 'censimento_piani.xlsx'))

    # --- Villette
    v = json.load(open(os.path.join(DATA, 'censimento_villette.json'), encoding='utf-8'))
    wb = Workbook()
    ws = wb.active
    ws.title = 'Villette'
    col = ['codice', 'quartiere', 'zona', 'strada', 'lotto', 'destinazione_uso', 'piani_totali', 'superficie_impronta_m2',
           'superficie_lorda_m2', 'altezza_m', 'abitanti', 'alloggi']
    intestazione(ws, col, [12, 22, 22, 18, 7, 16, 11, 14, 14, 10, 10, 10, 9])
    for x in v['villette']:
        ws.append([x[k] if x.get(k) is not None else '' for k in col])
    ws.freeze_panes = 'B2'
    ws.auto_filter.ref = ws.dimensions
    ws = wb.create_sheet('Riepilogo')
    col = ['quartiere', 'villette', 'abitanti', 'alloggi', 'superficie_lorda_m2']
    intestazione(ws, col, [24, 10, 10, 10, 10, 18])
    for q, r in v['riepilogo'].items():
        ws.append([q] + [r[k] for k in col[1:]])
    wb.save(os.path.join(DATA, 'censimento_villette.xlsx'))
    print(f"edifici {len(edifici)} · piani {len(piani)} · spazi aperti {len(d['spazi_aperti'])} · villette {len(v['villette'])}")


if __name__ == '__main__':
    main()
