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
  sector?: 'pubblico' | 'privato' | '—';
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

/** Tutto quello che serve all'app, più alcune tabelle di ricerca costruite una volta sola. */
export interface MapData {
  world: WorldInfo;
  quarters: Quarter[];
  lots: Lot[];
  streets: StreetLabel[];
  places: Place[];
  categories: Category[];
  bus: BusNetwork;
  categoryById: Record<CategoryId, Category>;
  placeById: Map<number, Place>;
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
  busLines: boolean;
}

/** Un'area da illuminare sulla mappa quando la si passa col mouse nell'elenco. */
export type AreaHighlight = { type: 'quarter'; name: string } | { type: 'lot'; number: number } | null;
