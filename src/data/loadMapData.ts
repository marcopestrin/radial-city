import type { BusNetwork, Category, CategoryId, Lot, MapData, Place, Quarter, StreetLabel, WorldInfo } from '../types';

/**
 * Carica i file JSON da public/data/ e costruisce le tabelle di ricerca.
 * I file si scaricano all'avvio (non sono inclusi nel bundle): il JavaScript resta leggero
 * e i dati si possono sostituire senza ricompilare l'app.
 */
async function fetchJson<T>(name: string): Promise<T> {
  const response = await fetch(`${import.meta.env.BASE_URL}data/${name}.json`);
  if (!response.ok) {
    throw new Error(`Impossibile caricare data/${name}.json (${response.status})`);
  }
  return (await response.json()) as T;
}

/** Le linee degli autobus sono facoltative: senza bus.json la mappa funziona lo stesso, senza linee. */
async function fetchBus(): Promise<BusNetwork> {
  try {
    return await fetchJson<BusNetwork>('bus');
  } catch {
    return { updated: '', lines: [], stops: [] };
  }
}

export async function loadMapData(): Promise<MapData> {
  const [world, quarters, lots, streets, places, categories, bus] = await Promise.all([
    fetchJson<WorldInfo>('world'),
    fetchJson<Quarter[]>('quarters'),
    fetchJson<Lot[]>('lots'),
    fetchJson<StreetLabel[]>('streets'),
    fetchJson<Place[]>('places'),
    fetchJson<Category[]>('categories'),
    fetchBus(),
  ]);

  const categoryById = {} as Record<CategoryId, Category>;
  for (const category of categories) {
    categoryById[category.id] = category;
  }

  return {
    world,
    quarters,
    lots,
    streets,
    places,
    categories,
    bus,
    categoryById,
    placeById: new Map(places.map((place) => [place.id, place])),
    lotByNumber: new Map(lots.map((lot) => [lot.number, lot])),
    quarterByName: new Map(quarters.map((quarter) => [quarter.name, quarter])),
  };
}
