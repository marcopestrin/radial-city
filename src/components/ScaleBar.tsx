import { formatDistance } from '../lib/format';

/** Lunghezza indicativa della barra, in pixel. */
const TARGET_PX = 110;

/**
 * La barra della scala in basso a destra.
 * Cerca una distanza "tonda" (1, 2 o 5 per una potenza di dieci) vicina a 110 pixel allo zoom attuale.
 */
export default function ScaleBar({ scale }: { scale: number }) {
  const metres = TARGET_PX / scale;
  const power = Math.pow(10, Math.floor(Math.log10(metres)));
  const leading = metres / power;
  const niceMetres = (leading >= 5 ? 5 : leading >= 2 ? 2 : 1) * power;

  return (
    <div className="scale-bar card" aria-label={`Scala: ${formatDistance(niceMetres)}`}>
      <span>{formatDistance(niceMetres)}</span>
      <div className="bar" style={{ width: Math.round(niceMetres * scale) }} />
    </div>
  );
}
