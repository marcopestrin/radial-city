import { memo } from 'react';
import type { Lot } from '../../types';

const SANS = "'DejaVu Sans', Verdana, 'Segoe UI', Arial, sans-serif";

/** Il numero di ogni lotto, al centro del lotto. */
function LotNumberLayer({ lots }: { lots: Lot[] }) {
  return (
    <g
      className="layer-lot-numbers"
      pointerEvents="none"
      fontFamily={SANS}
      fontWeight="bold"
      textAnchor="middle"
      fill="#1f1f24"
      stroke="#fff"
      strokeWidth={2.6}
      strokeLinejoin="round"
      paintOrder="stroke"
    >
      {lots.map((lot) => (
        <text key={lot.number} x={lot.label.x} y={lot.label.y + lot.label.size * 0.36} fontSize={lot.label.size}>
          {lot.number}
        </text>
      ))}
    </g>
  );
}

export default memo(LotNumberLayer);
