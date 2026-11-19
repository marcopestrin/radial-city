import { memo } from 'react';
import type { BusNetwork } from '../../types';

const SANS = "'DejaVu Sans', Verdana, 'Segoe UI', Arial, sans-serif";

/** Sotto questo zoom (pixel per metro) i nomi della stazione e degli smistamenti non si scrivono. */
const HUB_LABEL_MIN_SCALE = 0.12;
/** Sotto questo zoom le fermate normali non si disegnano (sarebbero puntini sovrapposti). */
const STOP_MIN_SCALE = 0.2;

/**
 * Livello "Linee autobus": percorsi, fermate, stazione e smistamenti.
 * Linee e simboli hanno una dimensione fissa sullo schermo (in pixel), qualunque sia lo zoom.
 * Ogni linea si accende e si spegne dalla legenda (`hiddenLines`); una fermata resta finché passa almeno una linea accesa.
 * Nei tratti in comune le linee si sovrappongono: per vederne una sola, spegni le altre.
 * Passando il mouse su una fermata compare il suo nome con le linee che ci passano.
 */
function BusLayer({ bus, scale, hiddenLines }: { bus: BusNetwork; scale: number; hiddenLines: string[] }) {
  const px = 1 / scale; // un pixel dello schermo, in metri
  const lineById = new Map(bus.lines.map((line) => [line.id, line]));
  const visible = (id: string) => !hiddenLines.includes(id);
  const ordered = bus.lines.filter((line) => visible(line.id));

  return (
    <g className="layer-bus">
      <g fill="none" strokeLinecap="round" strokeLinejoin="round" pointerEvents="none">
        {ordered.map((line) => (
          <g key={line.id}>
            <path d={line.path} className="bus-casing" strokeWidth={7} />
            <path d={line.path} className="bus-line" stroke={line.color} strokeWidth={4} />
          </g>
        ))}
      </g>
      {bus.stops.map((stop) => {
        const important = stop.kind !== 'stop';
        if (!important && scale < STOP_MIN_SCALE) return null;
        if (!stop.lines.some(visible)) return null;
        const names = stop.lines.map((id) => lineById.get(id)?.name ?? id).join(', ');
        const size = (stop.kind === 'station' ? 9 : stop.kind === 'hub' ? 8 : 4) * px;
        return (
          <g key={stop.id} className={`bus-stop is-${stop.kind}`}>
            <title>{`${stop.name} · ${names}`}</title>
            {important ? (
              <rect x={stop.x - size} y={stop.y - size} width={size * 2} height={size * 2} rx={size * 0.3} />
            ) : (
              <circle cx={stop.x} cy={stop.y} r={size} />
            )}
            {important && scale >= HUB_LABEL_MIN_SCALE && (
              <text x={stop.x + size + 4 * px} y={stop.y + 4 * px} fontSize={12 * px} fontFamily={SANS} strokeWidth={3 * px}>
                {stop.name}
              </text>
            )}
          </g>
        );
      })}
    </g>
  );
}

export default memo(BusLayer);
