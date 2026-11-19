import { memo } from 'react';
import type { Quarter } from '../../types';

const SERIF = "'DejaVu Serif', Georgia, 'Times New Roman', serif";

/** Nomi dei quartieri in maiuscolo, nel colore del quartiere, con un alone bianco. */
function QuarterNameLayer({ quarters }: { quarters: Quarter[] }) {
  return (
    <g className="layer-quarter-names" pointerEvents="none">
      {quarters.map((quarter) => {
        const { x, y, size, rotate, spacing } = quarter.label;
        return (
          <text
            key={quarter.id}
            // il testo ruota attorno al proprio punto di ancoraggio
            transform={`translate(${x} ${y}) rotate(${rotate})`}
            // la linea di base scende di un terzo della dimensione: il testo risulta centrato in verticale
            y={size * 0.36}
            textAnchor="middle"
            fontFamily={SERIF}
            fontWeight="bold"
            fontSize={size}
            letterSpacing={spacing}
            fill={quarter.labelColor}
            fillOpacity={0.9}
            stroke="#fff"
            strokeWidth={5}
            strokeLinejoin="round"
            paintOrder="stroke"
          >
            {quarter.name.toUpperCase()}
          </text>
        );
      })}
    </g>
  );
}

export default memo(QuarterNameLayer);
