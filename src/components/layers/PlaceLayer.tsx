import { memo } from 'react';
import type { CSSProperties } from 'react';
import type { Category, CategoryId, Place } from '../../types';

/**
 * Le zone sensibili: una forma trasparente sopra ogni edificio con una funzione e sopra ogni luogo.
 * Quando il mouse ci passa sopra, il CSS (.place:hover) la colora con il colore della categoria;
 * MapView legge `data-place-id` per mostrare il tooltip e per la selezione.
 * I luoghi arrivano già ordinati dal più grande al più piccolo, così quelli piccoli restano sopra.
 */
function PlaceLayer({ places, categoryById }: { places: Place[]; categoryById: Record<CategoryId, Category> }) {
  return (
    <g className="layer-places">
      {places.map((place) => (
        <path
          key={place.id}
          className={place.kind ? `place place--${place.kind}` : 'place'}
          data-place-id={place.id}
          d={place.path}
          style={{ '--c': categoryById[place.category].color } as CSSProperties}
        />
      ))}
    </g>
  );
}

export default memo(PlaceLayer);
