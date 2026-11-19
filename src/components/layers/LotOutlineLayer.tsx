import { memo } from 'react';
import type { Lot } from '../../types';

/** Contorno bianco di ogni lotto. */
function LotOutlineLayer({ lots }: { lots: Lot[] }) {
  return (
    <g className="layer-lot-outlines" fill="none" stroke="#fff" strokeOpacity={0.55} strokeWidth={0.9}>
      {lots.map((lot) => (
        <path key={lot.number} d={lot.path} />
      ))}
    </g>
  );
}

export default memo(LotOutlineLayer);
