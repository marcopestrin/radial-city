import type { MapData, Place } from '../types';

/**
 * L'elenco a sinistra: quartieri (in ordine alfabetico; l'elenco può riordinarli per abitanti) > lotti (in ordine di numero) > edifici.
 * Qui si costruisce l'albero una volta sola e si filtra con la ricerca.
 */

export interface DirectoryLot {
  key: string; // chiave unica per React e per lo stato aperto/chiuso
  number: number | null; // null = "Fuori dai lotti"
  population: number;
  homes: number;
  places: Place[];
}

export interface DirectoryQuarter {
  name: string;
  population: number;
  lots: DirectoryLot[];
  placeCount: number;
}

/** Confronto alfabetico italiano che ignora maiuscole e accenti ("Città" vicino a "Citta"). */
const collator = new Intl.Collator('it', { sensitivity: 'base' });

export function buildDirectory(data: MapData): DirectoryQuarter[] {
  // luoghi raggruppati per quartiere e per lotto
  const placesByQuarter = new Map<string, Map<number | null, Place[]>>();
  for (const place of data.places) {
    let byLot = placesByQuarter.get(place.quarter);
    if (!byLot) {
      byLot = new Map();
      placesByQuarter.set(place.quarter, byLot);
    }
    const list = byLot.get(place.lot) ?? [];
    list.push(place);
    byLot.set(place.lot, list);
  }

  // tutti i quartieri: quelli con un contorno, quelli che hanno lotti e quelli che hanno luoghi
  const quarterNames = new Set<string>([
    ...data.quarters.map((quarter) => quarter.name),
    ...data.lots.map((lot) => lot.quarter),
    ...placesByQuarter.keys(),
  ]);

  const byName = (a: Place, b: Place) => collator.compare(a.name, b.name) || a.id - b.id;

  return [...quarterNames].sort(collator.compare).map((quarterName) => {
    const placesByLot = placesByQuarter.get(quarterName) ?? new Map<number | null, Place[]>();
    const lotNumbers = new Set<number>(data.lots.filter((lot) => lot.quarter === quarterName).map((lot) => lot.number));
    for (const lotNumber of placesByLot.keys()) {
      if (lotNumber !== null) lotNumbers.add(lotNumber);
    }

    const lots: DirectoryLot[] = [...lotNumbers]
      .sort((a, b) => a - b)
      .map((number) => {
        const lot = data.lotByNumber.get(number);
        return {
          key: `lot-${number}`,
          number,
          population: lot?.population ?? 0,
          homes: lot?.homes ?? 0,
          places: [...(placesByLot.get(number) ?? [])].sort(byName),
        };
      });

    const outside = placesByLot.get(null);
    if (outside && outside.length > 0) {
      lots.push({ key: `outside-${quarterName}`, number: null, population: 0, homes: 0, places: [...outside].sort(byName) });
    }

    const quarter = data.quarterByName.get(quarterName);
    return {
      name: quarterName,
      population: quarter?.population ?? lots.reduce((sum, lot) => sum + lot.population, 0),
      lots,
      placeCount: lots.reduce((sum, lot) => sum + lot.places.length, 0),
    };
  });
}

/* ------------------------------------------------------------------ ricerca */

/** Testo in minuscolo e senza accenti, per confrontare "citta" con "Città". */
export function normalize(text: string): string {
  return text.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
}

/** Risultato della ricerca: cosa mostrare e cosa aprire automaticamente. */
export interface FilteredQuarter {
  quarter: DirectoryQuarter;
  lots: { lot: DirectoryLot; places: Place[]; open: boolean }[];
  open: boolean;
}

/**
 * Filtra l'elenco.
 * - Se la ricerca corrisponde al nome del quartiere, si mostra tutto il quartiere.
 * - Se corrisponde a "lotto N" (o solo "N"), si mostra quel lotto con tutti i suoi edifici.
 * - Altrimenti si mostrano solo gli edifici il cui nome contiene il testo cercato,
 *   e i loro lotti e quartieri si aprono da soli.
 * Con la ricerca vuota tutto è visibile e chiuso (l'utente apre quello che vuole).
 */
export function filterDirectory(directory: DirectoryQuarter[], query: string): FilteredQuarter[] {
  const q = normalize(query);
  if (!q) {
    return directory.map((quarter) => ({
      quarter,
      lots: quarter.lots.map((lot) => ({ lot, places: lot.places, open: false })),
      open: false,
    }));
  }

  const result: FilteredQuarter[] = [];
  for (const quarter of directory) {
    const quarterMatches = normalize(quarter.name).includes(q);
    const lots: FilteredQuarter['lots'] = [];
    for (const lot of quarter.lots) {
      const lotName = lot.number === null ? 'fuori dai lotti' : `lotto ${lot.number}`;
      const lotMatches = lotName.includes(q) || (lot.number !== null && String(lot.number) === q);
      const matchingPlaces = lot.places.filter((place) => normalize(place.name).includes(q));
      if (quarterMatches || lotMatches) {
        lots.push({ lot, places: lot.places, open: lotMatches || matchingPlaces.length > 0 });
      } else if (matchingPlaces.length > 0) {
        lots.push({ lot, places: matchingPlaces, open: true });
      }
    }
    if (lots.length > 0) {
      // un quartiere trovato per nome resta chiuso (si vede l'elenco dei suoi lotti aprendolo)
      const open = lots.some((entry) => entry.open);
      result.push({ quarter, lots, open });
    }
  }
  return result;
}
