import { useLayoutEffect, useRef, useState } from 'react';
import type { Category, Place } from '../types';
import { formatNumber, placeLocation } from '../lib/format';

interface TooltipProps {
  place: Place;
  category: Category;
  clientX: number;
  clientY: number;
}

/** Il riquadro con il nome del luogo sotto il mouse. Si sposta per non uscire dallo schermo. */
export default function Tooltip({ place, category, clientX, clientY }: TooltipProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ left: clientX + 16, top: clientY + 16 });

  useLayoutEffect(() => {
    const box = ref.current;
    if (!box) return;
    const width = box.offsetWidth;
    const height = box.offsetHeight;
    let left = clientX + 16;
    let top = clientY + 16;
    if (left + width > window.innerWidth - 8) left = clientX - width - 12;
    if (top + height > window.innerHeight - 8) top = clientY - height - 12;
    setPosition({ left, top });
  }, [clientX, clientY, place.id]);

  return (
    <div ref={ref} className="tooltip card" role="tooltip" style={position}>
      <strong>
        <i style={{ background: category.color }} />
        {place.name}
      </strong>
      <span>{placeLocation(place.lot, place.quarter)}</span>
      {place.workers !== undefined && (
        <span>
          {place.floors ? `${place.floors} ${place.floors === 1 ? 'piano' : 'piani'} · ` : ''}
          {place.workers > 0
            ? `${formatNumber(place.workers)} ${place.workers === 1 ? 'lavoratore' : 'lavoratori'}${place.sector === 'pubblico' ? ' pubblici' : ''}`
            : 'nessun addetto fisso'}
        </span>
      )}
    </div>
  );
}
