import { useEffect, useMemo, useRef, useState } from 'react';
import type { AreaHighlight, Category, CategoryId, MapData } from '../../types';
import { buildDirectory, filterDirectory } from '../../lib/directory';
import { countWithWord, formatNumber } from '../../lib/format';
import { readStored, writeStored } from '../../lib/storage';
import QuarterGroup from './QuarterGroup';

/** Richiesta di mostrare un edificio nell'elenco (dopo un clic sulla mappa). */
export interface RevealRequest {
  placeId: number;
  token: number;
}

interface DirectoryProps {
  data: MapData;
  categoryById: Record<CategoryId, Category>;
  selectedPlaceId: number | null;
  reveal: RevealRequest | null;
  onHoverArea: (area: AreaHighlight) => void;
  onHoverPlace: (placeId: number | null) => void;
  onSelectPlace: (placeId: number) => void;
}

/** Ordine dei quartieri nell'elenco: alfabetico o per numero di abitanti (si ricorda tra una visita e l'altra). */
type QuarterSort = 'name' | 'population';
const SORT_KEY = 'citta-radiale-ordine-quartieri';
const SORT_OPTIONS: { value: QuarterSort; label: string }[] = [
  { value: 'name', label: 'A–Z' },
  { value: 'population', label: 'Abitanti' },
];

/** Ritardo della ricerca mentre si scrive, per non rifiltrare a ogni tasto. */
const SEARCH_DELAY_MS = 120;

/**
 * L'elenco degli edifici: quartieri > lotti > edifici, con la casella di ricerca.
 * Lo stato aperto/chiuso di quartieri e lotti è tenuto qui; la ricerca apre da sola quello che trova.
 */
export default function Directory({ data, categoryById, selectedPlaceId, reveal, onHoverArea, onHoverPlace, onSelectPlace }: DirectoryProps) {
  const directory = useMemo(() => buildDirectory(data), [data]);
  const totalPopulation = useMemo(() => directory.reduce((sum, quarter) => sum + quarter.population, 0), [directory]);

  const [input, setInput] = useState('');
  const [query, setQuery] = useState('');
  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(input), SEARCH_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [input]);

  const [sort, setSort] = useState<QuarterSort>(() => readStored(SORT_KEY, { sort: 'name' as QuarterSort }).sort);
  useEffect(() => writeStored(SORT_KEY, { sort }), [sort]);

  const filtered = useMemo(() => {
    const list = filterDirectory(directory, query);
    // il filtro mantiene l'ordine alfabetico; per abitanti si riordina dal più popoloso (a parità, alfabetico)
    return sort === 'population'
      ? [...list].sort((a, b) => b.quarter.population - a.quarter.population)
      : list;
  }, [directory, query, sort]);

  const [openQuarters, setOpenQuarters] = useState<Set<string>>(new Set());
  const [openLots, setOpenLots] = useState<Set<string>>(new Set());

  // a ogni nuova ricerca si aprono i quartieri e i lotti che contengono risultati (e si chiude il resto)
  useEffect(() => {
    setOpenQuarters(new Set(filtered.filter((entry) => entry.open).map((entry) => entry.quarter.name)));
    setOpenLots(new Set(filtered.flatMap((entry) => entry.lots.filter((item) => item.open).map((item) => item.lot.key))));
  }, [filtered]);

  const toggle = (setter: typeof setOpenQuarters, key: string) =>
    setter((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  // pulsanti degli edifici, per poter scorrere l'elenco fino a quello scelto sulla mappa
  const buttons = useRef(new Map<number, HTMLButtonElement>());
  const registerButton = (placeId: number, element: HTMLButtonElement | null) => {
    if (element) buttons.current.set(placeId, element);
    else buttons.current.delete(placeId);
  };

  // un clic sulla mappa apre il quartiere e il lotto dell'edificio e lo porta in vista
  useEffect(() => {
    if (!reveal) return;
    const place = data.placeById.get(reveal.placeId);
    if (!place) return;
    setInput('');
    setQuery('');
    const lotKey = place.lot === null ? `outside-${place.quarter}` : `lot-${place.lot}`;
    // aspetta che la ricerca vuota abbia richiuso tutto, poi apre il percorso dell'edificio
    window.setTimeout(() => {
      setOpenQuarters((current) => new Set(current).add(place.quarter));
      setOpenLots((current) => new Set(current).add(lotKey));
      window.setTimeout(() => buttons.current.get(place.id)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }), 60);
    }, SEARCH_DELAY_MS + 30);
  }, [reveal, data]);

  return (
    <section className="directory">
      <h2>
        Edifici{' '}
        <span className="caption">
          {formatNumber(data.places.length)} con una funzione · {countWithWord(totalPopulation, 'abitante', 'abitanti')}
        </span>
      </h2>
      <input
        type="search"
        className="search"
        placeholder="Cerca un edificio, un lotto o un quartiere"
        aria-label="Cerca un edificio, un lotto o un quartiere"
        autoComplete="off"
        value={input}
        onChange={(event) => setInput(event.target.value)}
      />
      <div className="sort-control" role="radiogroup" aria-label="Ordine dei quartieri">
        <span className="caption">Ordina i quartieri</span>
        <div className="segmented">
          {SORT_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              role="radio"
              aria-checked={sort === option.value}
              className={sort === option.value ? 'is-active' : undefined}
              onClick={() => setSort(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>
      <div className="directory-list" role="tree" aria-label="Edifici per quartiere e lotto">
        {filtered.length === 0 && <p className="empty">Nessun edificio trovato</p>}
        {filtered.map((entry) => (
          <QuarterGroup
            key={entry.quarter.name}
            entry={entry}
            open={openQuarters.has(entry.quarter.name)}
            openLots={openLots}
            onToggleQuarter={() => toggle(setOpenQuarters, entry.quarter.name)}
            onToggleLot={(key) => toggle(setOpenLots, key)}
            categoryById={categoryById}
            selectedPlaceId={selectedPlaceId}
            registerButton={registerButton}
            onHoverQuarter={(name) => onHoverArea(name ? { type: 'quarter', name } : null)}
            onHoverLot={(number) => onHoverArea(number !== null ? { type: 'lot', number } : null)}
            onHoverPlace={onHoverPlace}
            onSelectPlace={onSelectPlace}
          />
        ))}
      </div>
    </section>
  );
}
