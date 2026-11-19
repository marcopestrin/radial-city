import type { CSSProperties } from 'react';
import type { Category, CategoryId, Place } from '../../types';
import type { DirectoryLot } from '../../lib/directory';
import { countWithWord, plural } from '../../lib/format';

interface LotGroupProps {
  lot: DirectoryLot;
  places: Place[]; // i luoghi da mostrare (con una ricerca attiva possono essere solo alcuni)
  open: boolean;
  onToggle: () => void;
  categoryById: Record<CategoryId, Category>;
  selectedPlaceId: number | null;
  registerButton: (placeId: number, element: HTMLButtonElement | null) => void;
  onHoverLot: (lotNumber: number | null) => void;
  onHoverPlace: (placeId: number | null) => void;
  onSelectPlace: (placeId: number) => void;
}

/** Un lotto nell'elenco: intestazione con abitanti e numero di edifici, poi l'elenco degli edifici. */
export default function LotGroup(props: LotGroupProps) {
  const { lot, places, open, onToggle, categoryById, selectedPlaceId } = props;
  const title = lot.number === null ? 'Fuori dai lotti' : `Lotto ${lot.number}`;

  // riga sotto gli edifici: case presenti nel lotto, oppure "nessun edificio"
  let residential: string | null = null;
  if (lot.homes > 0) {
    residential = `${lot.places.length > 0 ? 'e ' : ''}${countWithWord(lot.homes, 'edificio residenziale', 'edifici residenziali')}`;
  } else if (lot.places.length === 0) {
    residential = 'Nessun edificio: campi, verde o piazzali';
  }

  return (
    <div className="lot-group">
      <button
        type="button"
        className="group-toggle lot-toggle"
        aria-expanded={open}
        onClick={onToggle}
        onMouseEnter={() => props.onHoverLot(lot.number)}
        onMouseLeave={() => props.onHoverLot(null)}
        onFocus={() => props.onHoverLot(lot.number)}
        onBlur={() => props.onHoverLot(null)}
      >
        <span className="chevron" aria-hidden="true" />
        <span className="group-name">{title}</span>
        {lot.number !== null && <span className="group-population">· {countWithWord(lot.population, 'abitante', 'abitanti')}</span>}
        <span className="group-count" title={`${lot.places.length} ${plural(lot.places.length, 'edificio', 'edifici')} con una funzione`}>
          {lot.places.length}
        </span>
      </button>

      {open && (
        <>
          <ul className="place-list">
            {places.map((place) => (
              <li key={place.id}>
                <button
                  type="button"
                  ref={(element) => props.registerButton(place.id, element)}
                  className={place.id === selectedPlaceId ? 'place-button is-selected' : 'place-button'}
                  title={categoryById[place.category].label}
                  style={{ '--c': categoryById[place.category].color } as CSSProperties}
                  onMouseEnter={() => props.onHoverPlace(place.id)}
                  onMouseLeave={() => props.onHoverPlace(null)}
                  onFocus={() => props.onHoverPlace(place.id)}
                  onBlur={() => props.onHoverPlace(null)}
                  onClick={() => props.onSelectPlace(place.id)}
                >
                  <i aria-hidden="true" />
                  {place.name}
                </button>
              </li>
            ))}
          </ul>
          {residential && <p className="residential">{residential}</p>}
        </>
      )}
    </div>
  );
}
