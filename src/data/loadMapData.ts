import type { BusNetwork, Census, CensusActivity, Category, CategoryId, Lot, MapData, Place, Quarter, StreetLabel, WorldInfo } from '../types';

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

/** Anche il censimento è facoltativo: senza censimento.json la legenda non ha la sua sezione. */
async function fetchCensus(): Promise<Census | null> {
  try {
    return await fetchJson<Census>('censimento');
  } catch {
    return null;
  }
}

/** I perimetri delle attività e dei nuovi edifici sono facoltativi (tools/perimetri.py): senza il file la mappa ha solo i contorni di places.json. */
async function fetchOutlines(): Promise<Place[]> {
  try {
    return await fetchJson<Place[]>('perimetri');
  } catch {
    return [];
  }
}

export async function loadMapData(): Promise<MapData> {
  const [world, quarters, lots, streets, basePlaces, outlines, categories, bus, census] = await Promise.all([
    fetchJson<WorldInfo>('world'),
    fetchJson<Quarter[]>('quarters'),
    fetchJson<Lot[]>('lots'),
    fetchJson<StreetLabel[]>('streets'),
    fetchJson<Place[]>('places'),
    fetchOutlines(),
    fetchJson<Category[]>('categories'),
    fetchBus(),
    fetchCensus(),
  ]);

  // i perimetri vengono dopo: si disegnano sopra i contorni degli edifici (i luoghi sono ordinati dal più grande al più piccolo)
  const places = [...basePlaces, ...outlines];
  const censusActivityByPlace = new Map<number, CensusActivity>();
  for (const building of census?.edifici ?? []) {
    for (const company of building.aziende ?? []) {
      if (company.luogo != null && !building.luoghi.includes(company.luogo)) {
        censusActivityByPlace.set(company.luogo, { company, building });
      }
    }
  }

  const categoryById = {} as Record<CategoryId, Category>;
  for (const category of categories) {
    categoryById[category.id] = category;
  }

  return {
    census,
    world,
    quarters,
    lots,
    streets,
    places,
    categories,
    bus,
    categoryById,
    placeById: new Map(places.map((place) => [place.id, place])),
    censusBuildingByPlace: new Map((census?.edifici ?? []).flatMap((b) => b.luoghi.map((id) => [id, b] as const))),
    censusSpaceByPlace: new Map((census?.spazi_aperti ?? []).map((s) => [s.luogo, s] as const)),
    censusActivityByPlace,
    lotByNumber: new Map(lots.map((lot) => [lot.number, lot])),
    quarterByName: new Map(quarters.map((quarter) => [quarter.name, quarter])),
  };
}
