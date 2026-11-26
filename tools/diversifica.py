# Diversificazione delle imprese del censimento. Lo chiama tools/censimento.py sui record già costruiti.
#
#   - ogni impresa ha un ramo specifico (non "industria" o "servizi") e un nome proprio (non "Azienda 7");
#   - notai e studi legali scendono a 10 ciascuno; al loro posto altri rami del terziario (più vari);
#   - i rami generici del terziario (consulenza, software, energia...) si dividono in rami più precisi;
#   - alcuni capannoni si dividono in più aziende (i posti di lavoro dell'edificio restano gli stessi);
#   - bar e ristoranti nei quartieri che non ne hanno, due cliniche private in La Cerchia, aziende agricole nuove;
#   - i dipendenti di sanità e istruzione crescono del 20%.
#
# Tutto è deterministico (seme fisso): rilanciando si ottengono gli stessi nomi.
import collections, random, re

SEED = 2611
SANITA_ISTRUZIONE = 1.2

COGNOMI = ['Rossi', 'Ferrari', 'Russo', 'Bianchi', 'Romano', 'Gallo', 'Costa', 'Fontana', 'Conti', 'Esposito', 'Ricci',
           'Bruno', 'Rizzo', 'Moretti', 'De Luca', 'Marino', 'Greco', 'Barbieri', 'Lombardi', 'Giordano', 'Colombo',
           'Mancini', 'Longo', 'Leone', 'Martini', 'Serra', 'Santoro', 'Marchetti', 'Galli', 'Caruso', 'Ferri', 'Testa',
           'Pellegrini', 'Fabbri', 'Bernardi', 'Villa', 'Monti', 'Cattaneo', 'Sala', 'Farina', 'Valentini', 'Ferraro',
           'Silvestri', 'Piras', 'Rinaldi', 'Orlando', 'Bellini', 'Guidi', 'Parisi', 'Basile', 'Palumbo', 'Mariani',
           'Rota', 'Sanna', 'Grassi', 'Negri', 'Pagano', 'Carbone', 'Vitale', 'Bianco', 'Morelli', 'Sartori', 'Neri',
           'Zanetti', 'Cassano', 'Brambilla', 'Perrone', 'Boschetti', 'Bozzi', 'Radice', 'Tosi', 'Visconti', 'Dalla Torre']

# ------------------------------------------------------------------ rami nuovi e come si chiamano le imprese
# ramo -> modello del nome ({A}, {B} = cognomi, {R} = il ramo)
TEMPLATE = {
    'studio notarile': 'Studio notarile {A}', 'studio legale': 'Studio legale {A} e {B}',
    'studio di commercialisti': 'Studio commercialisti {A} e {B}', 'studio di architettura': 'Studio di architettura {A}',
    'agenzia immobiliare': 'Agenzia immobiliare {A}', 'agenzia di viaggi': 'Agenzia viaggi {A}',
    'casa editrice': 'Edizioni {A}', 'selezione del personale': 'Selezione del personale {A}',
    # terziario nuovo (al posto di notai e studi legali)
    'cybersecurity': '{A} Cyber Security', 'data analytics e intelligenza artificiale': '{A} Data & AI',
    'agenzia pubblicitaria e PR': 'Agenzia {A} pubblicità e PR', 'studio di geometri e perizie': 'Studio geometri {A} e {B}',
    'fintech e pagamenti digitali': '{A} Pay', 'studio di design industriale': '{A} Design Studio',
    'produzione video e fotografia': '{A} Film e Foto', 'consulenti del lavoro': 'Studio consulenti del lavoro {A}',
    'gestione patrimoni (SGR)': '{A} SGR', 'sviluppo videogiochi': '{A} Games', 'cloud e hosting': '{A} Cloud',
    'brevetti e marchi': 'Studio brevetti {A}', 'traduzioni e interpretariato': 'Traduzioni {A}',
    'broker assicurativo': 'Broker {A} assicurazioni', 'scuola di lingue': 'Scuola di lingue {A}',
    'formazione aziendale': '{A} Formazione', 'coworking': 'Coworking {A}',
    # nelle zone dei trasporti e dell'agricoltura
    'spedizioniere doganale': 'Spedizioni doganali {A}', 'agenzia di handling e cargo aereo': '{A} Air Cargo Handling',
    'assicurazioni sui trasporti': 'Assicurazioni trasporti {A}', 'leasing e noleggio di aeromobili': '{A} Aircraft Leasing',
    'consulenza sulla logistica': '{A} Logistics Consulting', 'software per la logistica': '{A} Logistics Software',
    'consulenza agronomica': 'Studio agronomico {A}', 'assicurazioni agricole': 'Assicurazioni agricole {A}',
    'assistenza contabile agricola': 'Centro assistenza agricola {A}',
}

# nuovi rami per le imprese tolte a notai e studi legali (peso = quante ogni 47)
NUOVI_RAMI = [('cybersecurity', 4), ('data analytics e intelligenza artificiale', 4), ('agenzia pubblicitaria e PR', 4),
              ('studio di geometri e perizie', 4), ('fintech e pagamenti digitali', 3), ('studio di design industriale', 3),
              ('produzione video e fotografia', 3), ('consulenti del lavoro', 3), ('gestione patrimoni (SGR)', 3),
              ('sviluppo videogiochi', 2), ('cloud e hosting', 2), ('brevetti e marchi', 2),
              ('traduzioni e interpretariato', 2), ('broker assicurativo', 2), ('scuola di lingue', 2),
              ('formazione aziendale', 2), ('coworking', 2)]
# nelle zone dei trasporti o dell'agricoltura gli uffici hanno altri bisogni
RAMI_ZONA = [
    ({'Aeroporto'}, ['spedizioniere doganale', 'agenzia di handling e cargo aereo', 'assicurazioni sui trasporti',
                     'leasing e noleggio di aeromobili']),
    ({'Polo Logistico', 'Stazione', 'Le Officine', 'Zona Industriale Sud', 'Zona Artigianale', 'Borgo Nazionale', 'Tecnopolo'},
     ['spedizioniere doganale', 'assicurazioni sui trasporti', 'consulenza sulla logistica', 'software per la logistica']),
    ({'Campagna Est', 'Campagna Nord', 'Campagna Ovest', 'Campagna Sud', 'Campagna di Levante', 'Golena del Fiume'},
     ['consulenza agronomica', 'assicurazioni agricole', 'assistenza contabile agricola']),
]
# dove restano i 10 notai e i 10 studi legali: a turno nel centro, in La Cerchia e sulle strade principali
ZONE_PROFESSIONI = ['Centro', 'La Cerchia', 'Corso Garibaldi', 'Corso Nazionale', 'Viale Roma']
MASSIMO_PROFESSIONI = 10

# rami generici da dividere in rami precisi: ramo -> [(ramo preciso, peso, modello del nome)]
DIVIDI = {
    'consulenza aziendale': [('consulenza strategica', 10, '{A} Strategy'),
                             ('consulenza fiscale e societaria', 8, 'Consulenza fiscale e societaria {A}'),
                             ('consulenza energetica e ambientale', 7, '{A} Ambiente ed Energia'),
                             ('consulenza sulla sicurezza sul lavoro', 6, '{A} Sicurezza sul lavoro')],
    'software e servizi informatici': [('software gestionale ed ERP', 12, '{A} Software gestionale'),
                                       ('sviluppo di app mobili', 8, '{A} Mobile Apps'),
                                       ('piattaforme e-commerce', 8, '{A} Commerce Platform'),
                                       ('sistemi embedded e IoT', 10, '{A} Embedded Systems')],
    'energia': [('installazione di impianti fotovoltaici', 9, '{A} Solare'), ('biometano e biogas', 6, '{A} Biometano'),
                ('accumulo a batterie', 9, '{A} Storage'), ('idrogeno', 4, '{A} Idrogeno'),
                ('efficienza energetica', 5, '{A} Efficienza energetica')],
    'telecomunicazioni': [('telefonia e fibra ottica', 12, '{A} Telecom'),
                          ('infrastrutture di rete mobile', 10, '{A} Reti mobili'),
                          ('connettività e cloud per le imprese', 13, '{A} Business Connect')],
    'società di revisione': [('revisione e certificazione di bilancio', 25, '{A} Revisione'),
                             ('due diligence e consulenza contabile', 15, '{A} Audit & Advisory')],
    'agenzia assicurativa': [('assicurazioni auto e danni', 16, 'Agenzia {A} auto e danni'),
                             ('assicurazioni vita e previdenza', 12, 'Agenzia {A} vita e previdenza'),
                             ('assicurazioni per le imprese', 8, 'Agenzia {A} assicurazioni imprese')],
    'società finanziaria': [('credito al consumo', 8, '{A} Credito'), ('leasing e factoring', 8, '{A} Leasing e Factoring'),
                            ('mutui e finanziamenti', 8, '{A} Mutui')],
    'società di ingegneria': [('ingegneria civile e strutturale', 10, '{A} Ingegneria strutturale'),
                              ('ingegneria impiantistica', 10, '{A} Impianti'),
                              ('ingegneria ambientale', 8, '{A} Ingegneria ambientale')],
    'studio di architettura': [('progettazione residenziale', 14, 'Studio {A} architetti'),
                               ('restauro e recupero', 12, 'Studio di restauro {A}'),
                               ('urbanistica e paesaggio', 12, 'Studio di urbanistica {A}')],
    'agenzia di marketing': [('marketing digitale e social media', 12, '{A} Digital Marketing'),
                             ('branding e comunicazione', 10, '{A} Branding'), ('ricerche di mercato', 8, '{A} Ricerche')],
    'agenzia immobiliare': [('agenzia immobiliare residenziale', 22, 'Agenzia immobiliare {A}'),
                            ('immobiliare commerciale e uffici', 12, '{A} Immobili commerciali')],
    'selezione del personale': [('somministrazione di lavoro', 13, '{A} Lavoro temporaneo'),
                                ('ricerca e selezione di dirigenti', 10, '{A} Executive Search')],
    'casa editrice': [('editoria scolastica e universitaria', 12, 'Edizioni {A} scolastiche'),
                      ('editoria di narrativa', 12, 'Edizioni {A}'), ('editoria periodica', 10, '{A} Periodici')],
    'agenzia di viaggi': [('agenzia di viaggi per privati', 15, 'Agenzia viaggi {A}'),
                          ('viaggi d\'affari', 9, '{A} Business Travel'), ('tour operator', 9, '{A} Tour Operator')],
    'sede amministrativa di un gruppo logistico': [
        ('sede di gruppo: trasporto merci su strada', 15, 'Gruppo {A} Trasporti'),
        ('sede di gruppo: corrieri ed e-commerce', 10, 'Gruppo {A} Corrieri'),
        ('sede di gruppo: logistica del freddo', 10, 'Gruppo {A} Cold Chain')],
}
for _r, _l in DIVIDI.items():
    for _sub, _w, _t in _l:
        TEMPLATE[_sub] = _t

# ------------------------------------------------------------------ ramo dal nome dell'impresa
# i rami troppo generici (o mancanti) si specificano dal nome; la prima regola che corrisponde
GENERICI = {None, 'ristorazione', 'commercio', 'industria', 'artigianato', 'logistica e magazzino', 'servizio pubblico',
            'servizi e uffici', 'servizi alle imprese e terziario', 'sanità', 'istruzione'}
NAME_RAMO = [(re.compile(rx, re.I), ramo) for rx, ramo in [
    (r'^(Bar|Caffetteria|Caffè|Caff|Chiosco bar|Bar pasticceria|Bar tavola calda|Bar e minimarket)\b', 'bar e caffetteria'),
    (r'^(Pub|Birreria|Wine bar|Enoteca)', 'pub, birreria ed enoteca'),
    (r'^Pizzeria', 'pizzeria'),
    (r'^(Ristorante|Steakhouse|Sushi)', 'ristorante'),
    (r'^(Trattoria|Osteria)', 'trattoria e osteria'),
    (r'^(Fast food|Paninoteca|Tavola calda)', 'fast food e paninoteca'),
    (r'^(Gelateria|Pasticceria|Laboratorio di pasticceria)', 'gelateria e pasticceria'),
    (r'^(Panetteria|Panificio|Pasta fresca)', 'panetteria e panificio'),
    (r'^Mensa', 'mensa'),
    (r'^Banca', 'filiale bancaria'),
    (r'^Farmacia', 'farmacia'),
    (r'^(Poliambulator|Centro analisi|Laboratorio analisi|Centro prelievi)', 'poliambulatorio e analisi cliniche'),
    (r'^Studio dentistico', 'odontoiatria'),
    (r'^(Pronto soccorso|Accesso ambulanze|Day hospital|Oncologia|Pediatria|Ematologia|Radioterapia|Neonatologia|Maternit|'
     r'Neurologia|Riabilitazione|Cardiologia|Chirurgia|Medicina interna|Ortopedia|Radiologia|Amministrazione ospedale|'
     r'Casa di riposo|Casa della salute)', 'ospedale e sanità territoriale'),
    (r'^Ospedale', 'ospedale'),
    (r'^Scuola dell.infanzia|^Asilo', 'scuola dell\'infanzia e asilo nido'),
    (r'^Scuola primaria', 'scuola primaria'),
    (r'^Scuola media', 'scuola secondaria di primo grado'),
    (r'^Liceo', 'liceo'),
    (r'^Istituto (tecnico|professionale)', 'istruzione tecnica e professionale'),
    (r'^Scuola di volo', 'scuola di volo'),
    (r'^Università', 'università e ricerca'),
    (r'^Coworking', 'coworking'),
    (r'^Studio notarile', 'studio notarile'),
    (r'^Ordine degli avvocati', 'ordine professionale'),
    (r'^Studio legale', 'studio legale'),
    (r'^(Commercialista|Studio commercialista)', 'studio di commercialisti'),
    (r'^Studio di architettura', 'studio di architettura'),
    (r'^Studio di (ingegneria|progettazione)$', 'società di ingegneria'),
    (r'^Studio di interior design', 'interior design'),
    (r'^Studio di rendering', 'rendering 3D'),
    (r'^Studio geologico', 'studio geologico'),
    (r'^Studio di ingegneria acustica', 'ingegneria acustica'),
    (r'^Studio di progettazione (navale|stradale)', 'progettazione specialistica'),
    (r'^Agenzia pubblicitaria', 'agenzia pubblicitaria e PR'),
    (r'^Agenzia per il lavoro', 'selezione del personale'),
    (r'^Agenzia di traduzioni', 'traduzioni e interpretariato'),
    (r'^Agenzia (di )?viaggi', 'agenzia di viaggi'),
    (r'^Agenzia immobiliare', 'agenzia immobiliare'),
    (r'^(Assicurazioni|Agenzia di assicurazioni)', 'agenzia assicurativa'),
    (r'^Software house', 'software e servizi informatici'),
    (r'^(Sede sindacale|Casa delle associazioni|Associazione)', 'associazioni e sindacati'),
    (r'^(Libreria|Cartoleria|Edicola)', 'libri, cartoleria ed edicola'),
    (r'^(Abbigliamento|Calzature|Negozi di abbigliamento)', 'abbigliamento e calzature'),
    (r'^(Mobili e arredamento|Casalinghi|Articoli per la casa)', 'arredamento e casalinghi'),
    (r'^(Elettrodomestici|Elettronica|Telefonia)$', 'elettronica e telefonia'),
    (r'^(Giocattoli|Animali e accessori)', 'giocattoli e animali'),
    (r'^(Giardinaggio|Garden center|Fiorista|Fioraio)', 'giardinaggio e fiori'),
    (r'^(Profumeria|Parrucchiere|Estetista|Centro benessere)', 'cura della persona e benessere'),
    (r'^Ottica', 'ottica'),
    (r'^(Ferramenta|Bricolage)$', 'ferramenta e fai da te'),
    (r'^(Supermercato|Discount)', 'grande distribuzione alimentare'),
    (r'^(Macelleria|Pescheria|Frutta e verdura|Vendita frutta e verdura|Alimentari)', 'alimentari e prodotti freschi'),
    (r'^Tabaccheria', 'tabacchi e ricevitoria'),
    (r'^(Lavanderia|Lavaggio auto)', 'lavanderia e servizi alla persona'),
    (r'^(Concessionaria auto|Negozio di biciclette)', 'auto e biciclette'),
    (r'^(Palestra|Centro yoga|Articoli sportivi|Piscine|Club house)', 'sport e fitness'),
    (r'^(Cinema|Sala bowling|Sala giochi|Go-kart|Luna park|Planetario|Museo|Galleria d.arte)', 'cultura e intrattenimento'),
    (r'^(Chiesa|Canonica|Oratorio|Casa parrocchiale|Monastero)', 'culto e attività parrocchiali'),
    (r'^(Ingresso fiera|Padiglione fieristico|Centro congressi)', 'fiere e congressi'),
    (r'^(Facoltà|Dipartimento|Aula|Biblioteca universitaria|Laboratori universitari)', 'università e ricerca'),
    (r'^(Centro ricerca|Laboratori di ricerca|Laboratorio prove)', 'ricerca e sviluppo'),
    (r'^Incubatore', 'incubatore di startup'),
    (r'^Sala controllo', 'controllo e gestione delle reti'),
    (r'^Centro servizi autotrasporto', 'servizi per l\'autotrasporto'),
    (r'^Polizia di frontiera', 'sicurezza e controllo di frontiera'),
    (r'^Autonoleggio', 'autonoleggio'),
    (r'^Ufficio postale', 'servizi postali'),
    (r'^Uffici comunali', 'uffici comunali'),
    # industria, artigianato, logistica
    (r'(Hangar|Mezzi di rampa|Carburante avio|Catering aereo|Eliporto|Deposito bagagli)', 'servizi aeroportuali e manutenzione aeromobili'),
    (r'(Carpenteria|Stampaggio lamiere|Costruzione stampi|Lavorazioni meccaniche|Taglio laser|Tornitura|Rettific|Minuteria|'
     r'Quadri elettrici|Pompe idrauliche|Stabilimento metalmeccanico|Saldatura|Lavorazione alluminio)', 'metalmeccanica'),
    (r'(Stampaggio materie plastiche|vetroresina)', 'materie plastiche e vetroresina'),
    (r'(Pannelli in legno|Mobilificio|Falegnameria|Torneria del legno|Mobili su misura|Rivendita di legnami)', 'legno e arredo'),
    (r'(Infissi|Vetreria|Serramenti)', 'infissi e vetro'),
    (r'(Biscottificio|Pastificio|Torrefazione|Birrificio|Panificio artigianale)', 'industria alimentare'),
    (r'(Calzaturificio|tessile|Sartoria|Pelletteria|Stamperia tessile|Calzolaio)', 'tessile, abbigliamento e calzature'),
    (r'(Tipografia|Etichette|Stampa digitale|Serigrafia|Legatoria|Copisteria)', 'stampa e packaging'),
    (r'(Cementeria|Fornace|Ciminiera|inerti|calcestruzzo|Cumuli|Vasche di decantazione|Pesa |Ceramiche e pavimenti|Marmista|'
     r'Marmi e graniti|Deposito del clinker|Deposito di argilla)', 'materiali da costruzione'),
    (r'(Idraulico|Elettricista|Lattoniere|Impianti|Termoidraulica|Idraulica|climatizzazione|Insegne)', 'impiantistica e installazioni'),
    (r'(Fabbro|Corniciaio|Tappezzeria|Ceramista|Liuteria|orafo|Incisioni|Coltelleria|Restauro mobili|Laboratorio di ceramica)',
     'artigianato artistico e su misura'),
    (r'(Gommista|Autocarrozzeria|Riparazione|Restauro auto|Centro revisioni|Autolavaggio|Verniciatura|Lavanderia industriale)',
     'riparazioni e manutenzione'),
    (r'(Logistica farmaceutica|Deposito materiale sanitario)', 'logistica farmaceutica'),
    (r'(del freddo|Magazzino alimentare|ortofrutta|Distribuzione alimentari)', 'logistica del freddo e alimentare'),
    (r'(Corriere|Smistamento|Spedizion|Cargo|Centro servizi|Centro distribuzione|Noleggio furgoni)', 'corrieri e spedizioni'),
    (r'(Deposito carburante|Deposito gas|Bombole)', 'deposito di carburanti e gas'),
    (r'Container', 'terminal container'),
    (r'e-commerce', 'logistica per l\'e-commerce'),
    (r'(Deposito|Magazzino) (di )?(bevande|vini?)', 'distribuzione di bevande e vino'),
    (r'(edile|edili|legnami|pallet|serramenti)', 'magazzini per l\'edilizia'),
    (r'(Ricambi|Ferramenta|Materiale|Distribuzione|Prodotti per la pulizia|Noleggio|Idraulica e termosanitari|Vernici)',
     'commercio all\'ingrosso e noleggio'),
    (r'^(Magazzino|Deposito)', 'magazzini all\'ingrosso'),
]]

SAN = re.compile(r'^(Ospedale|Pronto soccorso|Poliambulatorio|Casa della salute|Casa di riposo|Laboratorio analisi|Centro analisi|'
                 r'Centro oculistico|Studio pediatrico|Centro cardiologico|Day hospital)')
IST = re.compile(r'^(Scuola|Liceo|Istituto|Polo scolastico|Università|Facoltà|Dipartimento|Laboratori universitari|'
                 r'Biblioteca universitaria|Asilo)')

# ------------------------------------------------------------------ capannoni da dividere: codice -> (nome, [(nome impresa, ramo, peso)])
# nome impresa None = l'impresa che c'era; {A} = un cognome
CAPANNONI = {
    'ZI-001': ('Pannelli in legno', [(None, 'pannelli in legno', 3), ('Falegnameria su misura {A}', 'falegnameria su misura', 1),
                                     ('Pallet e imballaggi {A}', 'pallet e imballaggi in legno', 1)]),
    'ZI-003': ('Infissi in PVC', [(None, 'infissi in PVC', 3), ('Serramenti in alluminio {A}', 'serramenti in alluminio', 1),
                                  ('Vetrocamera {A}', 'vetrocamera e lavorazione del vetro', 1)]),
    'ZI-033': ('Stabilimento metalmeccanico', [(None, 'metalmeccanica', 3), ('Tornitura CNC {A}', 'tornitura CNC', 1),
                                               ('Trattamenti termici {A}', 'trattamenti termici dei metalli', 1)]),
    'ZI-035': ('Stampaggio materie plastiche', [(None, 'stampaggio di materie plastiche', 3),
                                                ('Imballaggi alimentari {A}', 'imballaggi alimentari in plastica', 1),
                                                ('Riciclo plastiche {A}', 'riciclo delle materie plastiche', 1)]),
    'ZI-051': ('Tipografia', [(None, 'tipografia offset', 3), ('Prototipi e stampa 3D {A}', 'stampa 3D e prototipazione', 1),
                              ('Packaging in cartone {A}', 'packaging in cartone', 1)]),
    'ZI-053': ('Biscottificio', [(None, 'biscottificio', 3), ('Panificio industriale {A}', 'panificio industriale', 1),
                                 ('Pasta fresca {A}', 'pasta fresca', 1)]),
    'BN-014': ('Lavorazione alluminio', [(None, 'fonderia di alluminio', 3), ('Estrusione profili {A}', 'estrusione di profili', 1),
                                         ('Verniciatura a polvere {A}', 'verniciatura a polvere', 1)]),
    'BN-023': ('Calzaturificio (scarpe sportive)', [(None, 'calzaturificio', 3), ('Pelletteria {A}', 'pelletteria', 1),
                                                    ('Suole e componenti {A}', 'suole e componenti per calzature', 1)]),
    'PLO-008': ('Deposito bevande', [(None, 'distribuzione di bevande', 2), ('Birre e bibite {A}', 'distribuzione di birra e bibite', 1),
                                     ('Vino all\'ingrosso {A}', 'vino all\'ingrosso', 1)]),
    'PLO-011': ('Magazzino tessile', [(None, 'tessile per la casa', 3), ('Abbigliamento all\'ingrosso {A}', 'abbigliamento all\'ingrosso', 2)]),
    'PLO-083': ('Smistamento pacchi', [(None, 'corriere espresso', 3), ('Corriere locale {A}', 'consegne dell\'ultimo miglio', 1)]),
    'PLO-085': ('Magazzino abbigliamento', [(None, 'logistica della moda', 3), ('Fulfillment e-commerce {A}', 'logistica per l\'e-commerce', 2)]),
    'PLO-086': ('Deposito materiale sanitario', [(None, 'logistica farmaceutica', 3), ('Dispositivi medici {A}', 'distribuzione di dispositivi medici', 2)]),
    'PLO-087': ('Magazzino all\'ingrosso', [(None, 'ortofrutta all\'ingrosso', 2), ('Surgelati {A}', 'logistica del freddo', 2),
                                            ('Farmaci {A}', 'logistica farmaceutica', 1)]),
    'PLO-093': ('Magazzino mobili', [(None, 'logistica dell\'arredo', 3), ('Logistica automotive {A}', 'logistica automotive', 2),
                                     ('Fulfillment e-commerce {A}', 'logistica per l\'e-commerce', 2)]),
    'VR-220': ('Laboratori artigiani', [('Fabbro {A}', 'fabbro e lavorazione del ferro', 1), ('Falegnameria {A}', 'falegnameria', 1),
                                        ('Restauro mobili {A}', 'restauro di mobili', 1), ('Vetro artistico {A}', 'vetro artistico', 1),
                                        ('Ceramiche {A}', 'ceramica', 1), ('Tappezzeria {A}', 'tappezzeria e imbottiti', 1)]),
    'CS-062': ('Laboratori artigiani', [(t + ' {A}', r, 1) for t, r in [
        ('Falegnameria su misura', 'falegnameria su misura'), ('Ceramica artistica', 'ceramica artistica'),
        ('Forgiatura artistica', 'forgiatura artistica'), ('Vetro soffiato', 'vetro soffiato'), ('Liuteria', 'liuteria'),
        ('Restauro mobili antichi', 'restauro di mobili antichi'), ('Tappezzeria', 'tappezzeria'),
        ('Pelletteria artigiana', 'pelletteria artigiana'), ('Oreficeria', 'oreficeria'), ('Sartoria su misura', 'sartoria su misura'),
        ('Tessitura a mano', 'tessitura a mano'), ('Lavorazione del marmo', 'lavorazione del marmo'),
        ('Tornitura del legno', 'tornitura del legno'), ('Cornici e doratura', 'cornici e doratura'),
        ('Legatoria', 'legatoria e rilegatura'), ('Modellismo e stampi', 'modellismo e stampi')]]),
}

# ------------------------------------------------------------------ bar e ristoranti
# tipo: (ramo, addetti, modello, m² di impronta se è un edificio a sé)
LOCALI = {
    'bar': ('bar e caffetteria', 5, 'Bar {A}', 140), 'caffetteria': ('bar e caffetteria', 5, 'Caffetteria {A}', 140),
    'pasticceria': ('gelateria e pasticceria', 5, 'Bar pasticceria {A}', 160), 'gelateria': ('gelateria e pasticceria', 4, 'Gelateria {A}', 120),
    'trattoria': ('trattoria e osteria', 9, 'Trattoria {A}', 260), 'osteria': ('trattoria e osteria', 8, 'Osteria {A}', 240),
    'pizzeria': ('pizzeria', 8, 'Pizzeria {A}', 240), 'ristorante': ('ristorante', 12, 'Ristorante {A}', 360),
    'pesce': ('ristorante', 12, 'Ristorante di pesce {A}', 360), 'tavola': ('fast food e paninoteca', 7, 'Tavola calda {A}', 200),
    'panino': ('fast food e paninoteca', 4, 'Paninoteca {A}', 110),
}
# (zona, lotto, tipi). I lotti di Le Corti sono palazzi: i locali stanno al piano terra (2 per palazzo, nei primi palazzi del
# lotto); negli altri quartieri sono edifici a sé.
LOCALI_PALAZZI = [('Le Corti', 208, ['caffetteria', 'trattoria', 'pizzeria', 'gelateria', 'pasticceria', 'bar']),
                  ('Le Corti', 204, ['ristorante', 'pesce', 'pizzeria', 'osteria', 'bar', 'gelateria'])]
LOCALI_NUOVI = [('Borgo Nuovo', 691, ['bar', 'trattoria', 'pizzeria', 'ristorante', 'gelateria']),
                ('San Michele', 708, ['caffetteria', 'pizzeria', 'tavola', 'panino']),
                ('Le Grazie', 455, ['bar', 'ristorante', 'pizzeria', 'trattoria'])]

# ------------------------------------------------------------------ cliniche private nei piani liberi di La Cerchia
# (edificio, nome atteso, [(piani, nome del piano, modello impresa, ramo, addetti per piano)])
CLINICHE = [
    ('LC-001', 'Palazzo delle professioni', [
        ([2, 3], 'Clinica polispecialistica', 'Clinica {A}', 'clinica privata polispecialistica', 45),
        ([4], 'Diagnostica per immagini', 'Centro diagnostico {A}', 'diagnostica per immagini', 30),
        ([5], 'Fisioterapia e riabilitazione', 'Fisioterapia {A}', 'fisioterapia e riabilitazione', 30),
        ([6], 'Studi medici associati', 'Studi medici associati {A}', 'studi medici associati', 30)]),
    ('LC-098', 'Palazzo per uffici', [
        ([4], 'Clinica odontoiatrica', 'Clinica odontoiatrica {A}', 'odontoiatria', 38),
        ([5], 'Day surgery', 'Day surgery {A}', 'chirurgia ambulatoriale', 38)]),
]

# ------------------------------------------------------------------ aziende agricole nuove (edifici senza contorno)
# (zona, lotto, nome, ramo, uso, addetti, impronta m², piani)
AGRICOLE = [
    ('Campagna Est', 749, 'Mulino e pastificio {A}', 'molitura e pastificio', 'fabbrica', 14, 1800, 2),
    ('Campagna Est', 749, 'Birrificio agricolo {A}', 'birrificio agricolo', 'fabbrica', 7, 900, 1),
    ('Campagna Est', 749, 'Azienda cerealicola {A}', 'coltivazione di cereali', 'agricolo', 6, 1200, 1),
    ('Campagna Nord', 562, 'Riseria e molino {A}', 'riseria e molitura del riso', 'fabbrica', 12, 1600, 2),
    ('Campagna Nord', 562, 'Apicoltura {A}', 'apicoltura e miele', 'agricolo', 4, 400, 1),
    ('Campagna Nord', 562, 'Azienda risicola {A}', 'coltivazione del riso', 'agricolo', 6, 1100, 1),
    ('Campagna Ovest', 590, 'Frutteto {A}', 'frutticoltura (mele e pere)', 'agricolo', 10, 1100, 1),
    ('Campagna Ovest', 590, 'Vivaio {A}', 'florovivaismo', 'agricolo', 9, 900, 1),
    ('Campagna di Levante', 573, 'Caseificio ovicaprino {A}', 'caseificio di latte ovino e caprino', 'fabbrica', 12, 1100, 1),
    ('Campagna di Levante', 573, 'Stagionatura formaggi {A}', 'stagionatura di formaggi', 'agricolo', 5, 700, 1),
    ('Campagna di Levante', 573, 'Allevamento ovicaprino {A}', 'allevamento ovicaprino', 'agricolo', 6, 1300, 1),
    ('Campagna Sud', 902, 'Impianto agrivoltaico {A}', 'agrivoltaico', 'impianto', 4, 600, 1),
    ('Campagna Sud', 804, 'Pioppeto e vivaio forestale {A}', 'pioppicoltura e legname', 'agricolo', 5, 800, 1),
    ('Golena del Fiume', 602, 'Acquacoltura {A}', 'acquacoltura (trote)', 'agricolo', 8, 1500, 1),
    ('Golena del Fiume', 602, 'Pescheria e spaccio del pescato {A}', 'pesca e vendita del pescato', 'negozio', 3, 300, 1),
]


# ------------------------------------------------------------------ utilità
def arrotonda(x):
    return int(x + 0.5)


def quote(pesi, n):
    """`n` diviso in parti intere in proporzione ai pesi (il resto va ai resti più grandi)."""
    tot = sum(pesi)
    parti = [n * p / tot for p in pesi]
    base = [int(x) for x in parti]
    for i in sorted(range(len(pesi)), key=lambda i: (-(parti[i] - base[i]), i))[:n - sum(base)]:
        base[i] += 1
    return base


class Nomi:
    """Nomi di imprese che non si ripetono."""

    def __init__(self, rng):
        self.rng, self.usati = rng, set()

    def nome(self, ramo=None, modello=None):
        modello = modello or TEMPLATE.get(ramo) or '{R} {A}'
        for _ in range(500):
            a, b = self.rng.sample(COGNOMI, 2)
            n = modello.format(A=a, B=b, R=(ramo or '')[:1].upper() + (ramo or '')[1:])
            if n not in self.usati:
                self.usati.add(n)
                return n
        raise RuntimeError('nomi finiti per ' + modello)


class Codici:
    """Il prossimo codice libero di una sigla (CEA-185 -> CEA-186)."""

    def __init__(self, edifici):
        self.ultimo = {}
        for e in edifici:
            sig, _, num = e['codice'].rpartition('-')
            if num.isdigit():
                self.ultimo[sig] = max(self.ultimo.get(sig, 0), int(num))

    def nuovo(self, sigla):
        self.ultimo[sigla] = self.ultimo.get(sigla, 0) + 1
        return f'{sigla}-{self.ultimo[sigla]:03d}'


def sul_piano(a, f):
    return not a['piani'] or f['piano'] in a['piani']


def rinomina(e, a, nuovo):
    """Cambia il nome di un'impresa dell'edificio, sui piani e (se l'edificio è tutto suo, senza forma sulla mappa) sull'edificio."""
    vecchio = a['azienda']
    for f in e['piani']:
        for fa in f.get('aziende', []):
            if fa['azienda'] == vecchio and sul_piano(a, f):
                fa['azienda'] = nuovo
                break                              # due imprese con lo stesso nome sullo stesso piano: una per volta
    if len(e['aziende']) == 1 and e['nome'] == vecchio and not e['luoghi']:
        e['nome'] = nuovo
        for f in e['piani']:
            if f['attivita'] == vecchio:
                f['attivita'] = nuovo
    a['azienda'] = nuovo


def ricalcola(e):
    """Totali dell'edificio e delle sue imprese dai piani."""
    for a in e['aziende']:
        voci = [fa['dipendenti'] for f in e['piani'] for fa in f.get('aziende', []) if fa['azienda'] == a['azienda'] and sul_piano(a, f)]
        if voci:
            a['dipendenti'] = sum(voci)
    fl = e['piani']
    e['posti_di_lavoro'] = sum(f['posti_di_lavoro'] for f in fl)
    e['posti_liberi'] = sum(f.get('posti_liberi', 0) for f in fl)
    e['attivita'] = sum(f.get('imprese', 0) for f in fl)
    e['abitanti'] = sum(f['abitanti'] for f in fl)
    e['alloggi'] = sum(f['alloggi'] for f in fl)


def scala(e, fattore):
    """Moltiplica i dipendenti di ogni piano e impresa."""
    senza_piani = [a for a in e['aziende']
                   if not any(fa['azienda'] == a['azienda'] for f in e['piani'] for fa in f.get('aziende', []))]
    for f in e['piani']:
        if f.get('aziende'):
            for fa in f['aziende']:
                fa['dipendenti'] = arrotonda(fa['dipendenti'] * fattore)
            f['posti_di_lavoro'] = sum(fa['dipendenti'] for fa in f['aziende'])
        else:
            f['posti_di_lavoro'] = arrotonda(f['posti_di_lavoro'] * fattore)
    for a in senza_piani:
        a['dipendenti'] = arrotonda(a['dipendenti'] * fattore)
    ricalcola(e)


def edificio_nuovo(codice, nome, zona, lotto, uso, categoria, impronta, piani, ramo, addetti, altezza_piano=3.5):
    """Un edificio con una sola impresa (senza contorno sulla mappa)."""
    parti = [addetti // piani + (1 if i < addetti % piani else 0) for i in range(piani)]
    fl = [{'piano': i, 'attivita': nome, 'superficie_m2': impronta, 'destinazione_uso': uso, 'alloggi': 0, 'abitanti': 0,
           'posti_di_lavoro': parti[i], 'imprese': 1 if i == 0 else 0,
           'aziende': [{'azienda': nome, 'dipendenti': parti[i]}] if parti[i] else [], 'posti_liberi': 0} for i in range(piani)]
    return {'codice': codice, 'nome': nome, 'quartiere': zona, 'zona': zona, 'lotto': lotto, 'luoghi': [],
            'destinazione_uso': uso, 'categoria': categoria, 'superficie_impronta_m2': impronta, 'piani_totali': piani,
            'superficie_lorda_m2': impronta * piani, 'altezza_m': piani * altezza_piano, 'abitanti': 0, 'alloggi': 0,
            'attivita': 1, 'posti_di_lavoro': addetti, 'posti_liberi': 0, 'unita': [], 'piani': fl,
            'aziende': [{'azienda': nome, 'ramo': ramo, 'dipendenti': addetti, 'piani': list(range(piani))}]}


# ------------------------------------------------------------------ i passi
def specifica_rami(edifici):
    """Il ramo di ogni impresa con ramo mancante o generico, dal nome."""
    n = 0
    for e in edifici:
        for a in e['aziende']:
            if a['ramo'] in GENERICI:
                for rx, ramo in NAME_RAMO:
                    if rx.search(a['azienda']):
                        a['ramo'] = ramo
                        n += 1
                        break
                else:
                    if a['ramo'] is None:
                        a['ramo'] = a['azienda'].lower()
                        n += 1
    return n


def riduci_professioni(edifici, rng, nomi):
    """Notai e studi legali a 10 ciascuno. Restano gli studi con la forma sulla mappa e poi, a turno, quelli delle zone principali;
    gli altri diventano imprese di rami nuovi (nelle zone dei trasporti e dell'agricoltura, di rami adatti a quelle zone)."""
    res, generali, giro = {}, [], {}
    for tipo in ('studio notarile', 'studio legale'):
        cand = [(e, a) for e in edifici for a in e['aziende'] if a['ramo'] == tipo]
        fissi = [x for x in cand if len(x[0]['aziende']) == 1 and x[0]['luoghi']]
        mobili = [x for x in cand if x not in fissi]
        servono = max(0, MASSIMO_PROFESSIONI - len(fissi))
        per_zona = {z: [x for x in mobili if x[0]['zona'] == z] for z in ZONE_PROFESSIONI}
        for v in per_zona.values():
            rng.shuffle(v)
        tenuti = []
        while len(tenuti) < servono and any(per_zona.values()):
            for z in ZONE_PROFESSIONI:
                if per_zona[z] and len(tenuti) < servono:
                    tenuti.append(per_zona[z].pop(0))
        da_convertire = [x for x in mobili if x not in tenuti]
        res[tipo] = {'prima': len(cand), 'dopo': len(fissi) + len(tenuti), 'convertite': len(da_convertire)}
        for e, a in da_convertire:
            rami = next((r for zone, r in RAMI_ZONA if e['zona'] in zone), None)
            if rami is None:
                generali.append((e, a))
                continue
            k = giro[e['zona']] = giro.get(e['zona'], -1) + 1
            a['ramo'] = rami[k % len(rami)]
            rinomina(e, a, nomi.nome(a['ramo']))
    rng.shuffle(generali)
    assegnati = [r for (r, _), k in zip(NUOVI_RAMI, quote([w for _, w in NUOVI_RAMI], len(generali))) for _ in range(k)]
    for (e, a), ramo in zip(generali, assegnati):
        a['ramo'] = ramo
        rinomina(e, a, nomi.nome(ramo))
    res['convertite_generali'] = len(generali)
    return res


def dividi_rami(edifici, rng):
    """I rami generici del terziario diventano rami precisi, nelle proporzioni di DIVIDI."""
    n = 0
    for ramo, subs in DIVIDI.items():
        lista = [a for e in edifici for a in e['aziende'] if a['ramo'] == ramo]
        rng.shuffle(lista)
        it = iter(lista)
        for (sub, _, _), k in zip(subs, quote([w for _, w, _ in subs], len(lista))):
            for _ in range(k):
                next(it)['ramo'] = sub
                n += 1
    return n


# imprese di questi rami con un nome da categoria ("Bar", "Libreria") prendono un cognome ("Bar Rota")
RAMI_CON_COGNOME = {
    'bar e caffetteria', 'pub, birreria ed enoteca', 'pizzeria', 'ristorante', 'trattoria e osteria', 'fast food e paninoteca',
    'gelateria e pasticceria', 'panetteria e panificio', 'filiale bancaria', 'farmacia', 'poliambulatorio e analisi cliniche',
    'odontoiatria', 'coworking', 'studio notarile', 'studio legale', 'studio di commercialisti', 'studio di architettura',
    'società di ingegneria', 'agenzia pubblicitaria e PR', 'selezione del personale', 'traduzioni e interpretariato',
    'agenzia di viaggi', 'agenzia immobiliare', 'agenzia assicurativa', 'software e servizi informatici', 'libri, cartoleria ed edicola',
    'abbigliamento e calzature', 'arredamento e casalinghi', 'elettronica e telefonia', 'giocattoli e animali', 'giardinaggio e fiori',
    'cura della persona e benessere', 'ottica', 'ferramenta e fai da te', 'alimentari e prodotti freschi', 'tabacchi e ricevitoria',
    'lavanderia e servizi alla persona', 'auto e biciclette', 'grande distribuzione alimentare'}


def nomi_specifici(edifici, nomi):
    """Le imprese chiamate "Azienda N" prendono un nome dal loro ramo; quelle con un nome da categoria ("Bar", che compare più
    volte) un cognome. Non si toccano gli edifici con la loro forma sulla mappa: il nome è quello della mappa."""
    ripetuti = {}
    for e in edifici:
        for a in e['aziende']:
            ripetuti[a['azienda']] = ripetuti.get(a['azienda'], 0) + 1
    n = 0
    for e in edifici:
        prima = n
        for a in e['aziende']:
            if re.fullmatch(r'Azienda \d+', a['azienda']):
                rinomina(e, a, nomi.nome(a['ramo']))
                n += 1
            elif (ripetuti[a['azienda']] > 1 and a['ramo'] in RAMI_CON_COGNOME and len(a['azienda'].split()) <= 4
                  and not (len(e['aziende']) == 1 and e['luoghi'])):
                rinomina(e, a, nomi.nome(a['ramo'], a['azienda'] + ' {A}'))
                n += 1
        if n > prima:
            ricalcola(e)                            # i nomi ora sono distinti: i totali tornano dai piani
    return n


def aumenta_sanita_istruzione(edifici):
    """+20% dei dipendenti di ogni struttura sanitaria e scolastica: restituisce (aumento sanità, aumento istruzione)."""
    s = i = 0
    for e in edifici:
        prima = e['posti_di_lavoro']
        if SAN.search(e['nome']):
            scala(e, SANITA_ISTRUZIONE)
            s += e['posti_di_lavoro'] - prima
        elif IST.search(e['nome']):
            scala(e, SANITA_ISTRUZIONE)
            i += e['posti_di_lavoro'] - prima
    return s, i


def dividi_capannoni(edifici, nomi):
    """Un'impresa per volta diventa più imprese: l'edificio mantiene i suoi posti di lavoro."""
    per_codice = {e['codice']: e for e in edifici}
    nuove = 0
    for codice, (nome, parti) in CAPANNONI.items():
        e = per_codice[codice]
        assert e['nome'] == nome, (codice, e['nome'], nome)
        vecchio = e['aziende'][0]['azienda'] if e['aziende'] else None
        nomi_nuovi = [vecchio if n is None else nomi.nome(r, n) for n, r, _ in parti]
        pesi = [p for _, _, p in parti]
        usati = []
        for f in e['piani']:
            tot = f['posti_di_lavoro']
            if not tot:
                continue
            f['aziende'] = [{'azienda': n, 'dipendenti': x} for n, x in zip(nomi_nuovi, quote(pesi, tot)) if x]
            f['imprese'] = len(f['aziende'])
            usati.append(f['piano'])
        e['aziende'] = [{'azienda': n, 'ramo': r, 'dipendenti': 0, 'piani': usati} for n, (_, r, _) in zip(nomi_nuovi, parti)]
        ricalcola(e)
        nuove += len(parti) - 1
    return nuove


def aggiungi_locali(edifici, lots, cat_label, sigla, riallinea, nomi, codici):
    """Bar e ristoranti: al piano terra di alcuni palazzi di Le Corti e in edifici nuovi negli altri quartieri."""
    quartiere = {l['number']: l['quarter'] for l in lots}
    n = 0
    for zona, lotto, tipi in LOCALI_PALAZZI:
        assert quartiere[lotto] == zona, (lotto, zona)
        palazzi = sorted((e for e in edifici if e['lotto'] == lotto and e['destinazione_uso'] == 'residenziale' and e['zona'] == zona),
                         key=lambda e: e['codice'])
        coppie = [tipi[i:i + 2] for i in range(0, len(tipi), 2)]
        assert len(palazzi) >= len(coppie), (lotto, len(palazzi))
        for e, due in zip(palazzi, coppie):
            abitanti = e['abitanti']
            f0 = e['piani'][0]
            assert f0['destinazione_uso'] == 'residenziale'
            locali = [(nomi.nome(LOCALI[t][0], LOCALI[t][2]), LOCALI[t][0], LOCALI[t][1]) for t in due]
            f0.update({'attivita': 'Negozi e bar', 'destinazione_uso': 'negozio', 'alloggi': 0, 'abitanti': 0,
                       'posti_di_lavoro': sum(x for _, _, x in locali), 'imprese': len(locali),
                       'aziende': [{'azienda': nm, 'dipendenti': x} for nm, _, x in locali], 'posti_liberi': 0})
            e['aziende'] = [{'azienda': nm, 'ramo': r, 'dipendenti': x, 'piani': [0]} for nm, r, x in locali]
            e['destinazione_uso'] = 'misto'
            e['categoria'] = cat_label['res'] + ' con negozi al piano terra'
            riallinea(e, abitanti)                   # gli abitanti del piano terra salgono ai piani sopra
            ricalcola(e)
            n += len(locali)
    for zona, lotto, tipi in LOCALI_NUOVI:
        assert quartiere[lotto] == zona, (lotto, zona)
        for t in tipi:
            ramo, addetti, modello, m2 = LOCALI[t]
            edifici.append(edificio_nuovo(codici.nuovo(sigla[zona]), nomi.nome(ramo, modello), zona, lotto, 'negozio',
                                          cat_label['com'], m2, 1, ramo, addetti))
            n += 1
    return n


def aggiungi_cliniche(edifici, nomi):
    """Cliniche private nei piani liberi dei palazzi per uffici di La Cerchia: restituisce i dipendenti aggiunti."""
    per_codice = {e['codice']: e for e in edifici}
    tot = 0
    for codice, nome, gruppi in CLINICHE:
        e = per_codice[codice]
        assert e['nome'] == nome, (codice, e['nome'])
        for piani, attivita, modello, ramo, addetti in gruppi:
            nm = nomi.nome(ramo, modello)
            for p in piani:
                f = e['piani'][p]
                assert f['attivita'] == 'Spazio libero', (codice, p, f['attivita'])
                capienza = f['posti_liberi']
                assert capienza >= addetti, (codice, p, capienza)
                f.update({'attivita': attivita, 'posti_di_lavoro': addetti, 'posti_liberi': capienza - addetti,
                          'imprese': 1 if p == piani[0] else 0, 'aziende': [{'azienda': nm, 'dipendenti': addetti}]})
                tot += addetti
            e['aziende'].append({'azienda': nm, 'ramo': ramo, 'dipendenti': addetti * len(piani), 'piani': list(piani)})
        ricalcola(e)
    return tot


def aggiungi_agricoltura(edifici, lots, cat_label, sigla, nomi, codici):
    """Aziende agricole e di trasformazione nuove: restituisce (aziende, dipendenti)."""
    quartiere = {l['number']: l['quarter'] for l in lots}
    tot = 0
    for zona, lotto, modello, ramo, uso, addetti, m2, piani in AGRICOLE:
        assert quartiere[lotto] == zona, (lotto, zona)
        categoria = cat_label['com'] if uso == 'negozio' else cat_label['agr']
        edifici.append(edificio_nuovo(codici.nuovo(sigla[zona]), nomi.nome(ramo, modello), zona, lotto, uso, categoria, m2, piani,
                                      ramo, addetti))
        tot += addetti
    return len(AGRICOLE), tot


# ------------------------------------------------------------------ più commercio: negozi vari, bar, ristoranti, supermercati
M2_PER_ADDETTO_PIANO_TERRA = 45     # un piano terra di negozi e bar ha un addetto ogni 45 m²
# negozi: (ramo, modello del nome, addetti da-a, peso)
NEGOZI = [
    ('fruttivendolo', 'Frutta e verdura {A}', (2, 3), 3), ('macelleria', 'Macelleria {A}', (3, 4), 3),
    ('pescheria', 'Pescheria {A}', (2, 3), 2), ('salumeria e gastronomia', 'Salumeria {A}', (3, 4), 2),
    ('formaggi e latticini', 'Formaggi {A}', (2, 3), 1), ('negozio di prodotti biologici', 'Bio {A}', (3, 4), 2),
    ('cioccolateria', 'Cioccolateria {A}', (2, 3), 1), ('pasta fresca', 'Pasta fresca {A}', (3, 4), 1),
    ('vini e liquori', 'Vineria {A}', (2, 3), 1),
    ('abbigliamento donna', 'Boutique {A}', (3, 5), 4), ('abbigliamento uomo', 'Abbigliamento uomo {A}', (3, 5), 3),
    ('abbigliamento bambini', 'Abbigliamento bambini {A}', (2, 4), 2), ('intimo e calzetteria', 'Intimo {A}', (2, 3), 1),
    ('calzature', 'Calzature {A}', (3, 4), 3), ('borse e pelletteria', 'Pelletteria {A}', (2, 3), 1),
    ('gioielleria', 'Gioielleria {A}', (2, 3), 2), ('orologeria', 'Orologeria {A}', (2, 2), 1), ('ottica', 'Ottica {A}', (3, 4), 2),
    ('profumeria', 'Profumeria {A}', (3, 4), 2), ('parrucchiere', 'Parrucchiere {A}', (3, 5), 3), ('barbiere', 'Barbiere {A}', (2, 3), 2),
    ('centro estetico', 'Centro estetico {A}', (3, 4), 2), ('erboristeria', 'Erboristeria {A}', (2, 3), 1),
    ('parafarmacia', 'Parafarmacia {A}', (3, 4), 1), ('sartoria su misura', 'Sartoria {A}', (2, 3), 1),
    ('casalinghi', 'Casalinghi {A}', (3, 4), 2), ('arredamento', 'Arredamento {A}', (4, 6), 2), ('illuminazione', 'Illuminazione {A}', (2, 3), 1),
    ('tessuti per la casa', 'Tessuti {A}', (2, 3), 1), ('ferramenta', 'Ferramenta {A}', (3, 4), 2), ('colorificio', 'Colorificio {A}', (2, 3), 1),
    ('elettronica di consumo', 'Elettronica {A}', (4, 6), 2), ('telefonia e riparazioni', 'Telefonia {A}', (2, 4), 3),
    ('informatica', 'Informatica {A}', (3, 4), 1), ('videogiochi', 'Videogiochi {A}', (2, 3), 1), ('fotografia', 'Foto {A}', (2, 3), 1),
    ('libreria', 'Libreria {A}', (3, 4), 3), ('cartoleria', 'Cartoleria {A}', (2, 3), 3), ('giocattoli', 'Giocattoli {A}', (3, 4), 2),
    ('articoli sportivi', 'Sport {A}', (4, 6), 2), ('biciclette', 'Biciclette {A}', (2, 4), 1), ('strumenti musicali', 'Musica {A}', (2, 3), 1),
    ('dischi e vinili', 'Vinili {A}', (2, 2), 1), ('articoli per animali', 'Animali {A}', (2, 3), 2), ('fiorista', 'Fiorista {A}', (2, 3), 3),
    ('antiquariato', 'Antiquariato {A}', (2, 2), 1), ('edicola', 'Edicola {A}', (1, 2), 3), ('tabaccheria', 'Tabaccheria {A}', (2, 3), 3),
    ('lavanderia', 'Lavanderia {A}', (2, 3), 2), ('copisteria', 'Copisteria {A}', (2, 3), 1),
]
# locali: (ramo, modello, addetti, peso); i rami sono quelli della ristorazione
CIBO = [
    ('bar e caffetteria', 'Bar {A}', (4, 6), 4), ('bar e caffetteria', 'Caffetteria {A}', (4, 6), 3),
    ('gelateria e pasticceria', 'Bar pasticceria {A}', (4, 6), 2), ('gelateria e pasticceria', 'Gelateria {A}', (3, 5), 2),
    ('pizzeria', 'Pizzeria {A}', (6, 9), 3), ('pizzeria', 'Pizzeria al taglio {A}', (3, 5), 1),
    ('trattoria e osteria', 'Trattoria {A}', (7, 10), 3), ('trattoria e osteria', 'Osteria {A}', (6, 9), 2),
    ('ristorante', 'Ristorante {A}', (9, 14), 3), ('ristorante', 'Ristorante di pesce {A}', (9, 13), 1),
    ('ristorante', 'Sushi {A}', (6, 9), 2), ('ristorante', 'Ristorante vegetariano {A}', (6, 9), 1),
    ('fast food e paninoteca', 'Tavola calda {A}', (5, 8), 2), ('fast food e paninoteca', 'Paninoteca {A}', (3, 5), 2),
    ('fast food e paninoteca', 'Rosticceria {A}', (3, 5), 1), ('pub, birreria ed enoteca', 'Birreria {A}', (4, 6), 1),
    ('pub, birreria ed enoteca', 'Wine bar {A}', (3, 5), 1), ('panetteria e panificio', 'Panetteria {A}', (3, 5), 2),
]
# supermercati e minimarket: (ramo, modello, addetti da-a)
ANCORE = {'super': ('grande distribuzione alimentare', 'Supermercato {A}', (14, 22)),
          'mini': ('minimarket', 'Minimarket {A}', (3, 5))}
MENSA = ('mensa', 'Mensa aziendale {A}', (10, 16))
QUOTA_CIBO = 0.32                   # parte dei locali di un piano terra che sono bar o ristoranti

# Centro: i piani "Negozi e bar" e alcuni palazzi residenziali (piano terra nuovo): supermercati e minimarket
COMMERCIO_CENTRO = {'palazzi_nuovi': 4, 'super': 5, 'mini': 8}
COMMERCIO_CERCHIA = {'mini': 6}
# Le Corti: per lotto, quanti piani terra di palazzi residenziali diventano negozi (oltre ai 6 con i locali già inseriti)
COMMERCIO_CORTI = {202: 2, 203: 2, 204: 2, 205: 2, 206: 1, 207: 3, 208: 2}
COMMERCIO_CORTI_ANCORE = {'super': 4, 'mini': 5}
# nuclei di locali e negozi nei quartieri lontani da bar e negozi: (zona, lotto, locali, negozi, supermercato)
NUCLEI = [('Villanova', 332, 3, 3, False), ('Villanova', 308, 2, 3, False), ('Gli Ulivi', 537, 3, 3, False),
          ('Le Magnolie', 872, 3, 3, False), ('Parco del Lago', 501, 4, 3, False), ('San Michele', 718, 3, 3, False),
          ('Gli Olmi', 846, 3, 3, False), ('Gli Olmi', 859, 2, 3, False), ('Gli Olmi', 818, 2, 3, False),
          ('Le Acacie', 541, 3, 3, False), ('Le Grazie', 792, 3, 3, False), ('Le Grazie', 439, 3, 3, False),
          ('Borgo Nuovo', 767, 3, 3, False),
          ('San Michele', 707, 1, 2, True), ('Le Magnolie', 874, 1, 2, True), ('Le Grazie', 459, 1, 2, True)]
# locali per i poli di lavoro (una mensa e poi bar, tavole calde, ristoranti), nel lotto dove lavora più gente
POLI_LAVORO = [('Città degli Studi', 8), ('San Luca', 8), ('Aeroporto', 6), ('Polo Logistico', 4),
               ('Zona Industriale Sud', 4), ('Campagna Sud', 3)]


class Assortimento:
    """Sceglie negozi e locali con varietà: più un tipo è già stato usato, meno è probabile."""

    def __init__(self, rng, nomi):
        self.rng, self.nomi, self.usati = rng, nomi, collections.Counter()

    def _voce(self, catalogo, evita):
        voci = [v for v in catalogo if v[1] not in evita] or catalogo
        pesi = [v[3] / (1 + 0.4 * self.usati[v[1]]) for v in voci]
        v = self.rng.choices(voci, pesi)[0]
        self.usati[v[1]] += 1
        return v

    def attivita(self, dip_max, evita, cibo=None):
        """Un negozio o un locale di al più `dip_max` addetti: (nome, ramo, addetti, modello)."""
        cibo = self.rng.random() < QUOTA_CIBO if cibo is None else cibo
        ramo, modello, (lo, hi), _ = self._voce(CIBO if cibo else NEGOZI, evita)
        dip = min(self.rng.randint(lo, hi), dip_max)
        if dip_max - dip == 1:
            dip = dip_max
        return self.nomi.nome(ramo, modello), ramo, dip, modello

    def ancora(self, tipo, grande=False):
        ramo, modello, (lo, hi) = ANCORE[tipo]
        dip = self.rng.randint(lo + 6, hi + 8) if grande else self.rng.randint(lo, hi)
        return self.nomi.nome(ramo, modello), ramo, dip, modello

    def riempi(self, target, ancora=None, grande=False, evita=()):
        """Le imprese di un piano terra, per un totale di `target` addetti (almeno l'ancora e due altri esercizi)."""
        voci, evita = [], set(evita)
        if ancora:
            voci.append(self.ancora(ancora, grande))
        resto = max(target, sum(v[2] for v in voci) + 3) - sum(v[2] for v in voci)
        while resto > 0:
            nome, ramo, dip, modello = self.attivita(resto, evita)
            evita.add(modello)
            voci.append((nome, ramo, dip, modello))
            resto -= dip
        return voci


def converti_piano_terra(e, cat_label, riallinea):
    """Il piano terra di un palazzo residenziale diventa uno spazio per negozi: gli abitanti salgono ai piani sopra."""
    abitanti = e['abitanti']
    f0 = e['piani'][0]
    assert f0['destinazione_uso'] == 'residenziale' and e['destinazione_uso'] == 'residenziale', e['codice']
    f0.update({'attivita': 'Negozi e bar', 'destinazione_uso': 'negozio', 'alloggi': 0, 'abitanti': 0, 'posti_di_lavoro': 0,
               'imprese': 0, 'aziende': [], 'posti_liberi': 0})
    e['destinazione_uso'] = 'misto'
    e['categoria'] = cat_label['res'] + ' con negozi al piano terra'
    riallinea(e, abitanti)


def popola_piano_terra(e, ass, ancora=None):
    """Riempie il piano terra "Negozi e bar" di un edificio con imprese dal nome e dal ramo specifici: restituisce gli addetti aggiunti."""
    f = e['piani'][0]
    esistenti = list(f.get('aziende') or [])
    occupati = sum(a['dipendenti'] for a in esistenti)
    capienza = f['posti_di_lavoro'] + f.get('posti_liberi', 0)
    prima = f['posti_di_lavoro']
    target = max(round(f['superficie_m2'] / M2_PER_ADDETTO_PIANO_TERRA), occupati + 3)
    grande = f['superficie_m2'] >= 2500
    voci = ass.riempi(target - occupati, ancora, grande, evita={a['azienda'] for a in esistenti})
    f['aziende'] = esistenti + [{'azienda': nm, 'dipendenti': d} for nm, _, d, _ in voci]
    f['posti_di_lavoro'] = sum(a['dipendenti'] for a in f['aziende'])
    f['imprese'] = len(f['aziende'])
    f['posti_liberi'] = max(0, capienza - f['posti_di_lavoro'])
    e['aziende'] += [{'azienda': nm, 'ramo': r, 'dipendenti': d, 'piani': [0]} for nm, r, d, _ in voci]
    ricalcola(e)
    return f['posti_di_lavoro'] - prima


def aumenta_commercio(edifici, lots, cat_label, sigla, riallinea, nomi, codici, rng):
    """Più negozi, bar, ristoranti, supermercati e minimarket. Restituisce un riassunto."""
    ass = Assortimento(rng, nomi)
    quartiere = {l['number']: l['quarter'] for l in lots}
    r = collections.Counter()
    ancore_ass = lambda piani, tipi: dict(zip(rng.sample(piani, len(tipi)), tipi))   # piano (indice) -> 'super' o 'mini'

    def esegui(piani, ancore_tipi):
        """`piani`: lista di edifici con il piano terra da popolare; `ancore_tipi`: lista di 'super'/'mini' da assegnare."""
        scelti = ancore_ass(list(range(len(piani))), ancore_tipi)
        for i, e in enumerate(piani):
            tipo = scelti.get(i)
            r['addetti'] += popola_piano_terra(e, ass, tipo)
            r['piani_terra'] += 1
            r[tipo or 'negozi'] += 1

    # Centro: i piani "Negozi e bar" e alcuni palazzi residenziali con il piano terra nuovo
    centro = [e for e in edifici if e['zona'] == 'Centro' and e['piani'][0]['attivita'] == 'Negozi e bar']
    puri = sorted((e for e in edifici if e['zona'] == 'Centro' and e['destinazione_uso'] == 'residenziale'), key=lambda e: e['codice'])
    nuovi = [puri[i] for i in range(0, len(puri), max(1, len(puri) // COMMERCIO_CENTRO['palazzi_nuovi']))][:COMMERCIO_CENTRO['palazzi_nuovi']]
    for e in nuovi:
        converti_piano_terra(e, cat_label, riallinea)
    esegui(centro + nuovi, ['super'] * COMMERCIO_CENTRO['super'] + ['mini'] * COMMERCIO_CENTRO['mini'])

    # La Cerchia: i piani "Negozi e bar", con qualche minimarket
    esegui([e for e in edifici if e['zona'] == 'La Cerchia' and e['piani'][0]['attivita'] == 'Negozi e bar'],
           ['mini'] * COMMERCIO_CERCHIA['mini'])

    # Le Corti: il piano terra di altri palazzi residenziali
    corti = []
    for lotto, n in COMMERCIO_CORTI.items():
        assert quartiere[lotto] == 'Le Corti', lotto
        pal = sorted((e for e in edifici if e['lotto'] == lotto and e['zona'] == 'Le Corti' and e['destinazione_uso'] == 'residenziale'),
                     key=lambda e: e['codice'])
        corti += pal[:n]
    for e in corti:
        converti_piano_terra(e, cat_label, riallinea)
    esegui(corti, ['super'] * COMMERCIO_CORTI_ANCORE['super'] + ['mini'] * COMMERCIO_CORTI_ANCORE['mini'])

    # nuclei di locali e negozi nei quartieri scoperti, e locali per i poli di lavoro: edifici nuovi senza contorno
    def nuovo(zona, lotto, voce, m2_per_addetto):
        nome, ramo, dip, _ = voce
        edifici.append(edificio_nuovo(codici.nuovo(sigla[zona]), nome, zona, lotto, 'negozio', cat_label['com'],
                                      max(60, dip * m2_per_addetto), 1, ramo, dip))
        r['edifici_nuovi'] += 1
        r['addetti'] += dip
        r[ramo] += 1

    for zona, lotto, n_cibo, n_negozi, super_ in NUCLEI:
        assert quartiere[lotto] == zona, (lotto, zona)
        usati = set()
        if super_:
            nuovo(zona, lotto, ass.ancora('super'), 45)
        for cibo in [True] * n_cibo + [False] * n_negozi:
            v = ass.attivita(99, usati, cibo)
            usati.add(v[3])
            nuovo(zona, lotto, v, 25 if cibo else 30)
    per_lotto = collections.Counter()
    for e in edifici:
        per_lotto[(e['zona'], e['lotto'])] += e['posti_di_lavoro']
    for zona, n in POLI_LAVORO:
        lotto = max((l for (z, l) in per_lotto if z == zona and l), key=lambda l: per_lotto[(zona, l)])
        assert quartiere[lotto] == zona, (lotto, zona)
        ramo, modello, (lo, hi) = MENSA
        nuovo(zona, lotto, (nomi.nome(ramo, modello), ramo, rng.randint(lo, hi), modello), 25)
        usati = set()
        for _ in range(n - 1):
            v = ass.attivita(99, usati, True)
            usati.add(v[3])
            nuovo(zona, lotto, v, 25)
    return dict(r)


# ------------------------------------------------------------------ asili, scuole elementari, medie e superiori
# tipo: (nome, ramo, addetti, impronta m², piani)
SCUOLE_TIPI = {
    'nido': ('Asilo nido', 'asilo nido', 12, 600, 1),
    'infanzia': ("Scuola dell'infanzia", "scuola dell'infanzia", 20, 1200, 1),
    'primaria': ('Scuola primaria', 'scuola primaria', 40, 2500, 2),
    'media': ('Scuola media', 'scuola secondaria di primo grado', 50, 3000, 2),
    'superiore': ('Liceo', 'liceo', 90, 4500, 3),
}
# (zona, lotto, [tipi]): proposta dei lotti in base ai bambini per quartiere e alle scuole esistenti
SCUOLE = [
    ('Centro', 26, ['infanzia', 'infanzia']), ('Centro', 2, ['primaria']),
    ('La Cerchia', 70, ['nido']), ('La Cerchia', 89, ['nido']), ('Le Corti', 202, ['nido']),
    ('San Michele', 721, ['nido', 'nido', 'primaria']), ('San Michele', 718, ['infanzia', 'infanzia']),
    ('San Michele', 708, ['infanzia']), ('San Michele', 716, ['primaria']), ('San Michele', 727, ['nido']),
    ('San Rocco', 408, ['nido', 'primaria']), ('San Rocco', 406, ['primaria']), ('San Rocco', 410, ['infanzia']),
    ('San Rocco', 412, ['media']),
    ('Belvedere', 578, ['nido', 'infanzia', 'infanzia', 'primaria', 'primaria']),
    ('I Mandorli', 549, ['nido', 'media']), ('I Mandorli', 550, ['infanzia']),
    ("Sant'Elena", 216, ['infanzia']), ("Sant'Elena", 250, ['nido', 'media']),
    ('Santa Lucia', 378, ['nido']), ('Santa Lucia', 379, ['primaria']),
    ('Villanova', 301, ['nido', 'primaria']), ('Villanova', 323, ['infanzia']),
    ('Le Acacie', 541, ['nido']), ('Le Acacie', 540, ['primaria']),
    ('Le Grazie', 455, ['infanzia', 'primaria']),
    ('Le Magnolie', 877, ['infanzia']), ('Le Magnolie', 873, ['superiore']),
    ('Borgo Fiorito', 114, ['nido', 'primaria']), ('Borgo Fiorito', 154, ['infanzia']),
    ('Borgo Fiera', 354, ['infanzia']), ('Borgo Nazionale', 268, ['infanzia']), ('Gli Olmi', 836, ['infanzia']),
    ('Gli Ulivi', 534, ['infanzia']), ('Parco del Lago', 483, ['infanzia']), ('Riva dei Salici', 927, ['nido']),
]
# a chi sono intitolate le scuole
DEDICHE = ['Gianni Rodari', 'Maria Montessori', 'Italo Calvino', 'Don Lorenzo Milani', 'Carlo Collodi', 'Dante Alighieri',
           'Alessandro Manzoni', 'Giuseppe Verdi', 'Leonardo da Vinci', 'Galileo Galilei', 'Marco Polo', 'Rita Levi-Montalcini',
           'Grazia Deledda', 'Giovanni Pascoli', 'Giacomo Leopardi', 'Umberto Eco', 'Primo Levi', 'Maria Callas', 'Enrico Fermi',
           'Margherita Hack', 'Antonio Gramsci', 'Eugenio Montale', 'Sibilla Aleramo', 'Pier Paolo Pasolini', 'Elsa Morante',
           'Bruno Munari', 'Federico Fellini', 'Giorgio Gaber', 'Tina Anselmi', 'Gino Strada', 'Giovanni Falcone', 'Paolo Borsellino',
           'Dino Buzzati', 'Natalia Ginzburg', 'Rosa Luxemburg', 'Gianna Nannini', 'Alda Merini', 'Ada Negri', 'Cesare Pavese',
           'Beppe Fenoglio', 'Gianfranco Zavalloni', 'Bianca Pitzorno', 'Mario Lodi', 'Loris Malaguzzi', 'Rosa Agazzi',
           'Lina Merlin', 'Camillo Golgi', 'Maria Grazia Cutuli', 'Anna Frank', 'Ilaria Alpi', 'Tullio De Mauro', 'Oriana Fallaci',
           'Pietro Mennea', 'Fausto Coppi', 'Gino Bartali', 'Nilde Iotti', 'Lucio Dalla', 'Fabrizio De André', 'Mia Martini',
           'Franca Rame', 'Dario Fo', 'Luciano Pavarotti', 'Maria Bellonci', 'Carlo Levi', 'Ignazio Silone', 'Elio Vittorini']


def aggiungi_scuole(edifici, lots, cat_label, sigla, rng, codici):
    """Asili nido, scuole dell'infanzia, primarie, medie e un liceo in lotti da 'SCUOLE': edifici nuovi senza contorno.
    Restituisce {tipo: numero} e gli addetti."""
    quartiere = {l['number']: l['quarter'] for l in lots}
    dediche = DEDICHE[:]
    rng.shuffle(dediche)
    n, addetti = collections.Counter(), 0
    for zona, lotto, tipi in SCUOLE:
        assert quartiere[lotto] == zona, (lotto, zona)
        for t in tipi:
            nome, ramo, dip, m2, piani = SCUOLE_TIPI[t]
            dedica = dediche.pop() if dediche else f'{len(edifici)}'
            edifici.append(edificio_nuovo(codici.nuovo(sigla[zona]), f'{nome} {dedica}', zona, lotto, 'servizio pubblico',
                                          cat_label['pub'], m2, piani, ramo, dip))
            n[t] += 1
            addetti += dip
    return dict(n), addetti


# ------------------------------------------------------------------ identità per le imprese che hanno solo un numero
def identita_anonime(edifici, nomi, rng):
    """I piani con imprese ma senza un elenco (un numero di imprese e basta) ricevono imprese con un nome: una sola impresa prende
    il nome del piano ("Software house"); un incubatore, un coworking o una galleria commerciale con più imprese le divide.
    Così ogni attività ha un nome e può avere un perimetro sulla mappa. Restituisce quante imprese ha creato."""
    ass = Assortimento(rng, nomi)
    creati = 0
    for e in edifici:
        for f in e['piani']:
            n = f.get('imprese', 0)
            if n <= 0 or f.get('aziende'):
                continue
            posti, att = f['posti_di_lavoro'], f['attivita']
            if n == 1:
                voci = [(att, None, posti)]
            else:
                q = quote([1] * n, posti)
                voci = []
                for d in q:
                    if att == 'Incubatore di startup':
                        voci.append((nomi.nome('startup', 'Startup {A}'), 'startup', d))
                    elif att == 'Coworking':
                        voci.append((nomi.nome('libera professione in coworking', 'Professionista {A}'), 'libera professione in coworking', d))
                    elif f['destinazione_uso'] == 'negozio':
                        nome, ramo, _, _ = ass.attivita(99, set())
                        voci.append((nome, ramo, d))
                    else:
                        voci.append((nomi.nome(att.lower(), att + ' {A}'), att.lower(), d))
            f['aziende'] = [{'azienda': nm, 'dipendenti': d} for nm, _, d in voci]
            f['imprese'] = len(voci)
            for nm, ramo, d in voci:
                a = next((x for x in e['aziende'] if x['azienda'] == nm), None)
                if a:
                    a['piani'] = sorted(set(a['piani']) | {f['piano']})
                else:
                    if ramo is None:
                        ramo = next((r for rx, r in NAME_RAMO if rx.search(nm)), att.lower())
                    e['aziende'].append({'azienda': nm, 'ramo': ramo, 'dipendenti': d, 'piani': [f['piano']]})
                creati += 1
        ricalcola(e)
    return creati


def applica(edifici, lots, cat_label, sigla, riallinea):
    """Modifica `edifici` sul posto e restituisce un riassunto (per la stampa)."""
    rng = random.Random(SEED)
    nomi = Nomi(rng)
    nomi.usati |= {a['azienda'] for e in edifici for a in e['aziende']} | {e['nome'] for e in edifici}
    codici = Codici(edifici)
    r = {}
    r['rami_specificati'] = specifica_rami(edifici)
    r['professioni'] = riduci_professioni(edifici, rng, nomi)
    r['rami_divisi'] = dividi_rami(edifici, rng)
    r['nomi_specifici'] = nomi_specifici(edifici, nomi)
    r['sanita_istruzione'] = aumenta_sanita_istruzione(edifici)
    r['capannoni'] = dividi_capannoni(edifici, nomi)
    r['locali'] = aggiungi_locali(edifici, lots, cat_label, sigla, riallinea, nomi, codici)
    r['cliniche'] = aggiungi_cliniche(edifici, nomi)
    r['agricole'] = aggiungi_agricoltura(edifici, lots, cat_label, sigla, nomi, codici)
    r['commercio'] = aumenta_commercio(edifici, lots, cat_label, sigla, riallinea, nomi, codici, rng)
    r['scuole'] = aggiungi_scuole(edifici, lots, cat_label, sigla, rng, codici)
    r['imprese_con_nome'] = identita_anonime(edifici, nomi, rng)
    return r
