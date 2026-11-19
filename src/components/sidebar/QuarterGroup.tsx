import type { Category, CategoryId } from '../../types';
import type { FilteredQuarter } from '../../lib/directory';
import { countWithWord, formatNumber, plural } from '../../lib/format';
import LotGroup from './LotGroup';

interface QuarterGroupProps {
  entry: FilteredQuarter;
  open: boolean;
  openLots: Set<string>;
  onToggleQuarter: () => void;
  onToggleLot: (key: string) => void;
  categoryById: Record<CategoryId, Category>;
  selectedPlaceId: number | null;
  registerButton: (placeId: number, element: HTMLButtonElement | null) => void;
  onHoverQuarter: (name: string | null) => void;
  onHoverLot: (lotNumber: number | null) => void;
  onHoverPlace: (placeId: number | null) => void;
  onSelectPlace: (placeId: number) => void;
}

/** Un quartiere nell'elenco: nome e abitanti; aperto mostra il riepilogo e i suoi lotti. */
export default function QuarterGroup(props: QuarterGroupProps) {
  const { entry, open, openLots } = props;
  const { quarter } = entry;
  const lotCount = quarter.lots.filter((lot) => lot.number !== null).length;

  return (
    <div className="quarter-group">
      <button
        type="button"
        className="group-toggle quarter-toggle"
        aria-expanded={open}
        onClick={props.onToggleQuarter}
        onMouseEnter={() => props.onHoverQuarter(quarter.name)}
        onMouseLeave={() => props.onHoverQuarter(null)}
        onFocus={() => props.onHoverQuarter(quarter.name)}
        onBlur={() => props.onHoverQuarter(null)}
      >
        <span className="chevron" aria-hidden="true" />
        <span className="group-name">{quarter.name}</span>
        <span className="group-count" title={countWithWord(quarter.population, 'abitante', 'abitanti')}>
          {formatNumber(quarter.population)} ab.
        </span>
      </button>

      {open && (
        <>
          <p className="quarter-summary">
            {countWithWord(quarter.population, 'abitante', 'abitanti')} · {lotCount} {plural(lotCount, 'lotto', 'lotti')} ·{' '}
            {quarter.placeCount} {plural(quarter.placeCount, 'edificio con una funzione', 'edifici con una funzione')}
          </p>
          {entry.lots.map(({ lot, places }) => (
            <LotGroup
              key={lot.key}
              lot={lot}
              places={places}
              open={openLots.has(lot.key)}
              onToggle={() => props.onToggleLot(lot.key)}
              categoryById={props.categoryById}
              selectedPlaceId={props.selectedPlaceId}
              registerButton={props.registerButton}
              onHoverLot={props.onHoverLot}
              onHoverPlace={props.onHoverPlace}
              onSelectPlace={props.onSelectPlace}
            />
          ))}
        </>
      )}
    </div>
  );
}
