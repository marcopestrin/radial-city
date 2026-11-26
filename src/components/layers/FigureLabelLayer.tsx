import { memo, useMemo } from 'react';
import type { CensusBuilding, Place } from '../../types';
import { formatNumber } from '../../lib/format';

const SANS = "'DejaVu Sans', Verdana, 'Segoe UI', Arial, sans-serif";

/** Una scritta è leggibile quando sullo schermo è alta almeno questi pixel. */
const MIN_READABLE_PX = 7;
/** Altezza delle scritte rispetto al lato minore dell'edificio, con i limiti in metri. */
const SIZE_RATIO = 0.3;
const MIN_SIZE = 3;
const MAX_SIZE = 16;
/** Spazio tra le righe (in altezze di scritta) e tra la prima riga e il tetto dell'edificio. */
const LINE_GAP = 1.15;
const ROOF_GAP = 0.35;

/** Le tre cifre che si possono scrivere sopra un edificio. */
export interface FigureKinds {
  height: boolean;
  residents: boolean;
  jobs: boolean;
}

const COLORS = { height: '#374151', residents: '#a14a00', jobs: '#0b4fb3' };

interface Figure {
  place: Place;
  building: CensusBuilding;
  size: number;
}

interface FigureGroup {
  minScale: number;
  figures: Figure[];
}

/** Raggruppa gli edifici per soglia di zoom, a passi di mezza ottava (come le etichette delle attività). */
function groupByMinScale(places: Place[], buildings: Map<number, CensusBuilding>): FigureGroup[] {
  const groups = new Map<number, Figure[]>();
  for (const place of places) {
    const building = buildings.get(place.id);
    if (!building) continue;
    const [x0, y0, x1, y1] = place.bbox;
    const size = Math.min(MAX_SIZE, Math.max(MIN_SIZE, Math.min(x1 - x0, y1 - y0) * SIZE_RATIO));
    const step = Math.round(2 * Math.log2(MIN_READABLE_PX / size)) / 2;
    const list = groups.get(step) ?? [];
    list.push({ place, building, size });
    groups.set(step, list);
  }
  return [...groups.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([step, figures]) => ({ minScale: Math.pow(2, step), figures }));
}

/** Le righe di un edificio, dalla più alta alla più bassa: altezza, residenti, posti di lavoro (solo quelle accese e con un valore). */
function linesOf(b: CensusBuilding, kinds: FigureKinds): { text: string; color: string }[] {
  const lines: { text: string; color: string }[] = [];
  if (kinds.height && b.altezza_m !== undefined) lines.push({ text: `${formatNumber(b.altezza_m)} m`, color: COLORS.height });
  if (kinds.residents && b.abitanti > 0) lines.push({ text: `${formatNumber(b.abitanti)} ab.`, color: COLORS.residents });
  if (kinds.jobs && b.posti_di_lavoro > 0) lines.push({ text: `${formatNumber(b.posti_di_lavoro)} lav.`, color: COLORS.jobs });
  return lines;
}

/** Un gruppo di scritte: si ridisegna solo se cambiano le cifre accese. */
const FigureGroupView = memo(function FigureGroupView({ group, kinds }: { group: FigureGroup; kinds: FigureKinds }) {
  return (
    <g>
      {group.figures.flatMap(({ place, building, size }) => {
        const lines = linesOf(building, kinds);
        const [x0, y0, x1] = place.bbox;
        const x = (x0 + x1) / 2;
        return lines.map((line, i) => (
          <text
            key={`${place.id}-${i}`}
            x={x}
            // la riga più bassa sta appena sopra il tetto; le altre salgono
            y={y0 - size * ROOF_GAP - (lines.length - 1 - i) * size * LINE_GAP}
            fontSize={size}
            fill={line.color}
            strokeWidth={Math.max(0.22, size * 0.2)}
          >
            {line.text}
          </text>
        ));
      })}
    </g>
  );
});

/**
 * Livelli "Altezza", "Residenti" e "Posti di lavoro": scrivono sopra ogni edificio le cifre del censimento accese
 * nella legenda, una riga per cifra. Ogni scritta compare solo quando è abbastanza grande da leggersi.
 */
function FigureLabelLayer({
  places,
  buildings,
  kinds,
  scale,
}: {
  places: Place[];
  buildings: Map<number, CensusBuilding>;
  kinds: FigureKinds;
  scale: number;
}) {
  const groups = useMemo(() => groupByMinScale(places, buildings), [places, buildings]);
  return (
    <g
      className="layer-figure-labels"
      pointerEvents="none"
      fontFamily={SANS}
      fontWeight="bold"
      textAnchor="middle"
      stroke="#fff"
      strokeOpacity={0.92}
      strokeLinejoin="round"
      paintOrder="stroke"
    >
      {groups
        .filter((group) => scale >= group.minScale)
        .map((group) => (
          <FigureGroupView key={group.minScale} group={group} kinds={kinds} />
        ))}
    </g>
  );
}

export default memo(FigureLabelLayer);
