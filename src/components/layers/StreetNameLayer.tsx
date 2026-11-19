import { memo } from 'react';
import type { StreetLabel } from '../../types';

const SANS = "'DejaVu Sans', Verdana, 'Segoe UI', Arial, sans-serif";

/**
 * Nomi delle vie scritti lungo il loro tracciato.
 * Ogni etichetta ha un breve percorso invisibile (in <defs>) che il testo segue con <textPath>.
 */
function StreetNameLayer({ streets }: { streets: StreetLabel[] }) {
  return (
    <g className="layer-street-names" pointerEvents="none">
      <defs>
        {streets.map((street) => (
          <path key={street.id} id={street.id} d={street.path} />
        ))}
      </defs>
      {streets.map((street) => (
        <text
          key={street.id}
          fontFamily={SANS}
          fontWeight="bold"
          fontSize={street.size}
          fill={street.color}
          stroke="#fff"
          strokeWidth={3.2}
          strokeLinejoin="round"
          paintOrder="stroke"
          dy={street.size * 0.36}
        >
          <textPath href={`#${street.id}`} startOffset="50%" textAnchor="middle">
            {street.name}
          </textPath>
        </text>
      ))}
    </g>
  );
}

export default memo(StreetNameLayer);
