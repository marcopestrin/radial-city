import { memo } from 'react';
import type { Quarter } from '../../types';

/** Campitura colorata dei quartieri; la campagna è più trasparente. */
function QuarterTintLayer({ quarters }: { quarters: Quarter[] }) {
  return (
    <g className="layer-quarter-tint">
      {quarters.map((quarter) => (
        <path
          key={quarter.id}
          d={quarter.path}
          fill={quarter.color}
          fillOpacity={quarter.rural ? 0.14 : 0.26}
          fillRule="evenodd"
        >
          <title>{quarter.name}</title>
        </path>
      ))}
    </g>
  );
}

export default memo(QuarterTintLayer);
