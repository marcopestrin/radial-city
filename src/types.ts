/**
 * Modello dei dati della mappa.
 *
 * Tutte le coordinate sono in metri nel sistema "mondo" della città: x cresce verso est,
 * y cresce verso SUD (come sullo schermo), così i dati si disegnano in SVG senza conversioni.
 * I file JSON in public/data/ hanno esattamente queste forme.
 */

/** Un riquadro dell'immagine satellitare (public/tiles/*.jpg). */
export interface SatelliteTile {
  file: string; // percorso relativo alla radice del sito, es. "tiles/sat_0_0.jpg"
  x: number; // posizione dell'angolo in alto a sinistra (m)
  y: number;
  size: number; // lato del quadrato (m)
}

/** Estensione della mappa e soglie di disegno (data/world.json). */
export interface WorldInfo {
  x: number;
  y: number;
  width: number;
  height: number;
  tiles: SatelliteTile[];
  /** Un livello si disegna solo quando lo zoom (pixel dello schermo per metro) è almeno questo valore. */
  minZoom: {
    streets: number;
    lotNumbers: number;
    /** Da qui in su si vedono i perimetri delle singole attività dentro gli edifici (i nuovi edifici si vedono già da molto meno). */
    activities: number;
  };
}

/** Dove e quanto grande è scritto il nome di un quartiere. */
export interface QuarterLabel {
  x: number;
  y: number;
  size: number; // dimensione del carattere in metri
  rotate: number; // gradi; -90 per la scritta verticale di Campagna Ovest
  spacing: number; // spaziatura tra le lettere in metri
}

/** Un quartiere (data/quarters.json). */
export interface Quarter {
  id: number;
  name: string;
  color: string; // colore della campitura
  labelColor: string; // tono più scuro usato per il nome
  rural: boolean; // i quartieri di campagna hanno una campitura più leggera
  population: number;
  path: string; // dati SVG del contorno (può avere buchi)
  label: QuarterLabel;
}

/** Un lotto: un isolato tra le strade (data/lots.json). */
export interface Lot {
  number: number;
  quarter: string;
  path: string;
  label: { x: number; y: number; size: number };
  population: number; // abitanti (stima)
  homes: number; // edifici residenziali
  floors?: number; // piani medi dei palazzi abitati (solo Centro e La Cerchia)
}

export type StreetKind = 'main' | 'minor' | 'country' | 'rail' | 'river';

/** Il nome di una via: il testo scorre lungo `path` (data/streets.json). */
export interface StreetLabel {
  id: string;
  name: string;
  kind: StreetKind;
  size: number;
  color: string;
  path: string;
}

/** Categorie di funzione: commercio, industria, artigianato, uffici, servizi pubblici, agricoltura. */
export type CategoryId = 'com' | 'ind' | 'art' | 'uff' | 'pub' | 'agr' | 'res';

export interface Category {
  id: CategoryId;
  label: string;
  color: string;
}

/** Un edificio con una funzione, o un luogo con un nome (parco, impianto, piazza...) (data/places.json). */
export interface Place {
  id: number;
  name: string;
  category: CategoryId;
  lot: number | null; // null quando il luogo non è dentro un lotto (ponti, strade)
  quarter: string;
  bbox: [number, number, number, number]; // minX, minY, maxX, maxY
  path: string;
  /** Dove si scrive il nome sulla mappa quando il livello "etichette delle attività" è acceso. */
  label: { x: number; y: number; size: number; angle: number };
  /** Piani dell'edificio (stima, salvo l'altezza scritta nel nome). Vedi tools/lavoratori.py. */
  floors?: number;
  /** Lavoratori (stima di tools/lavoratori.py). */
  workers?: number;
  /**
   * Solo per i perimetri di public/data/perimetri.json: `footprint` = il contorno di un edificio del censimento che non ne aveva,
   * `activity` = il perimetro di un'attività (negozio, bar, ufficio...) dentro un edificio, `pertinenza` = il parcheggio o l'aia
   * di un edificio nuovo. Vedi tools/perimetri.py.
   */
  kind?: 'footprint' | 'activity' | 'pertinenza';
  /** Il codice dell'edificio del censimento a cui appartiene il perimetro (solo con `kind`). */
  edificio?: string;
}


/** Una fermata degli autobus (data/bus.json). La stazione e gli smistamenti sono fermate speciali. */
export interface BusStop {
  id: string;
  name: string;
  quarter: string;
  kind: 'station' | 'hub' | 'stop';
  x: number;
  y: number;
  lines: string[]; // id delle linee che ci passano
}

/** Una linea degli autobus: il percorso segue le strade; `stops` è in ordine di marcia. */
export interface BusLine {
  id: string;
  name: string;
  short: string; // sigla breve: "1", "2", "C"
  color: string;
  circular: boolean;
  description: string;
  lengthM: number;
  path: string;
  stops: string[];
}

export interface BusNetwork {
  updated: string;
  lines: BusLine[];
  stops: BusStop[];
}

/** Destinazione d'uso di un edificio nel censimento. */
export type CensusUse =
  | 'residenziale'
  | 'misto'
  | 'ufficio'
  | 'negozio'
  | 'fabbrica'
  | 'servizio pubblico'
  | 'ricettivo'
  | 'parcheggio'
  | 'deposito'
  | 'agricolo'
  | 'ferroviario'
  | 'impianto';

/** Un negozio al piano terra di un palazzo residenziale. */
export interface CensusUnit {
  luogo: number;
  nome: string;
  destinazione_uso: CensusUse;
  piano: number;
  posti_di_lavoro: number;
}

/** Un edificio del censimento (tutti gli edifici della mappa, villette escluse; data/censimento.json, generato da tools/censimento.py). */
export interface CensusBuilding {
  codice: string;
  nome: string;
  quartiere: string;
  zona?: string; // la scheda: Centro, La Cerchia o la strada sul cui fronte sta l'edificio
  lotto: number | null; // null per i pochi luoghi fuori da ogni lotto
  luoghi: number[]; // id dei luoghi di places.json dentro l'edificio (vuoto per le case delle strade senza contorno)
  destinazione_uso: CensusUse;
  categoria: string;
  superficie_impronta_m2: number;
  piani_totali: number;
  superficie_lorda_m2: number;
  abitanti: number;
  alloggi: number;
  attivita: number;
  posti_di_lavoro: number;
  posti_liberi?: number; // posti di lavoro che restano liberi
  unita: CensusUnit[];
  /** Altezza (piani × 3,5 m) e un record per piano, dal piano terra (0) in su. */
  altezza_m?: number;
  piani?: CensusFloor[];
  /** Le imprese dell'edificio, con i dipendenti e i piani. */
  aziende?: CensusCompany[];
}

/** Un'impresa di un edificio: col suo nome, o "Azienda 1, 2..." negli uffici in affitto del Centro. */
/** Un'attività con il suo perimetro sulla mappa e l'edificio che la contiene. */
export interface CensusActivity {
  company: CensusCompany;
  building: CensusBuilding;
}

export interface CensusCompany {
  azienda: string; // "Macelleria Rota", "Studio legale Conti e Neri"...
  ramo: string | null; // cosa fa: macelleria, studio legale, software gestionale ed ERP...
  dipendenti: number;
  piani: number[];
  /** Il perimetro dell'attività sulla mappa: un luogo di places.json o di perimetri.json (quello dell'edificio se è l'unica attività). */
  luogo?: number | null;
}

/** Un piano di un edificio (tools/centro.py, tools/cerchia.py): ogni piano ha una sola destinazione d'uso. */
export interface CensusFloor {
  piano: number; // 0 = piano terra
  attivita: string; // cosa c'è: "Anagrafe e stato civile", "Abitazioni", "Uffici"...
  destinazione_uso: CensusUse;
  superficie_m2: number;
  abitanti: number;
  alloggi: number;
  posti_di_lavoro: number;
  imprese: number;
  camere?: number; // negli alberghi
  aziende?: { azienda: string; dipendenti: number }[]; // le imprese su questo piano
  posti_liberi?: number; // posti di lavoro che restano liberi su questo piano
}

export interface CensusOpenSpace {
  codice: string;
  nome: string;
  quartiere: string;
  lotto: number | null;
  luogo: number;
  tipo: string;
  superficie_m2: number;
  posti_di_lavoro: number;
  abitanti?: number;
}

export interface CensusUseSummary {
  edifici: number;
  superficie_lorda_m2: number;
  posti_di_lavoro: number;
  attivita: number;
}

/** Riepilogo di un quartiere (o del totale) con gli indicatori urbanistici. */
export interface CensusSummary {
  lotti: number;
  lotti_senza_edifici: number;
  superficie_territoriale_ha: number;
  edifici: number;
  villette?: number; // le villette stanno in censimento_villette.json
  spazi_aperti?: number;
  abitanti: number;
  abitanti_in_villette?: number;
  alloggi: number;
  attivita: number;
  posti_di_lavoro: number;
  posti_liberi?: number;
  superficie_lorda_m2: number;
  per_destinazione_uso: Partial<Record<CensusUse, CensusUseSummary>>;
}

export interface Census {
  meta: {
    titolo: string;
    quartieri: string[];
    /** I coefficienti dei programmi piano per piano (tools/centro.py e tools/cerchia.py). */
    parametri: {
      casa: { m2_per_alloggio: number; alloggi_sfitti: number; abitanti_per_alloggio: number };
      m2_per_addetto: Record<string, number>;
      occupazione: Record<string, number>;
      m2_per_camera: number;
      m2_per_studente: number;
      aziende: { classi_dipendenti: [number, number][]; probabilita_azienda_grande: number };
      altezza_piano_m: number;
    };
  };
  riepilogo: Record<string, CensusSummary>; // per quartiere, più "Totale"
  edifici: CensusBuilding[];
  spazi_aperti: CensusOpenSpace[];
}

/** Tutto quello che serve all'app, più alcune tabelle di ricerca costruite una volta sola. */
export interface MapData {
  /** Censimento di tutti gli edifici della mappa (villette escluse); null se data/censimento.json manca. */
  census: Census | null;
  world: WorldInfo;
  quarters: Quarter[];
  lots: Lot[];
  streets: StreetLabel[];
  places: Place[];
  categories: Category[];
  bus: BusNetwork;
  categoryById: Record<CategoryId, Category>;
  placeById: Map<number, Place>;
  /** La scheda del censimento di ogni luogo (per id di places.json): edifici e spazi aperti. */
  censusBuildingByPlace: Map<number, CensusBuilding>;
  censusSpaceByPlace: Map<number, CensusOpenSpace>;
  /** Per il perimetro di un'attività dentro un edificio: l'attività e l'edificio che la contiene. */
  censusActivityByPlace: Map<number, CensusActivity>;
  lotByNumber: Map<number, Lot>;
  quarterByName: Map<string, Quarter>;
}

/** Livelli che l'utente può accendere e spegnere. */
export interface LayerVisibility {
  satellite: boolean;
  quarterTint: boolean;
  quarterNames: boolean;
  streetNames: boolean;
  lotOutlines: boolean;
  lotNumbers: boolean;
  activityLabels: boolean;
  heightLabels: boolean;
  residentLabels: boolean;
  jobLabels: boolean;
  busLines: boolean;
  /** I perimetri delle attività e dei nuovi edifici (public/data/perimetri.json). */
  activityOutlines: boolean;
}

/** Un'area da illuminare sulla mappa quando la si passa col mouse nell'elenco. */
export type AreaHighlight = { type: 'quarter'; name: string } | { type: 'lot'; number: number } | null;
