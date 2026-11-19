import { memo } from 'react';
import type { SatelliteTile } from '../../types';

/** L'immagine satellitare, divisa in riquadri JPEG che il browser carica in parallelo. */
function SatelliteLayer({ tiles }: { tiles: SatelliteTile[] }) {
  return (
    <g className="layer-satellite">
      {tiles.map((tile) => (
        <image
          key={tile.file}
          href={`${import.meta.env.BASE_URL}${tile.file}`}
          x={tile.x}
          y={tile.y}
          // un decimo di metro in più evita le sottili righe chiare tra un riquadro e l'altro
          width={tile.size + 0.1}
          height={tile.size + 0.1}
          preserveAspectRatio="none"
        />
      ))}
    </g>
  );
}

export default memo(SatelliteLayer);
