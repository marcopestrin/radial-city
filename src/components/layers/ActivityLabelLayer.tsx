import { memo, useMemo } from 'react';
import type { Category, CategoryId, Place } from '../../types';

const SANS = "'DejaVu Sans', Verdana, 'Segoe UI', Arial, sans-serif";

/** Una scritta è leggibile quando sullo schermo è alta almeno questi pixel. */
const MIN_READABLE_PX = 7;

interface LabelGroup {
  minScale: number; // zoom a partire dal quale il gruppo si vede
  places: Place[];
}

/**
 * Raggruppa le etichette per "soglia di zoom" a passi di mezza ottava.
 * Così allo zoom non si ricalcolano 1.300 scritte: si aggiungono o tolgono gruppi interi.
 */
function groupByMinScale(places: Place[]): LabelGroup[] {
  const groups = new Map<number, Place[]>();
  for (const place of places) {
    const step = Math.round(2 * Math.log2(MIN_READABLE_PX / place.label.size)) / 2;
    const list = groups.get(step) ?? [];
    list.push(place);
    groups.set(step, list);
  }
  return [...groups.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([step, list]) => ({ minScale: Math.pow(2, step), places: list }));
}

/** Un gruppo di scritte: non cambia mai dopo il primo disegno (memo). */
const LabelGroupView = memo(function LabelGroupView({
  group,
  categoryById,
}: {
  group: LabelGroup;
  categoryById: Record<CategoryId, Category>;
}) {
  return (
    <g>
      {group.places.map((place) => {
        const { x, y, size, angle } = place.label;
        return (
          <text
            key={place.id}
            x={x}
            y={y + size * 0.36}
            fontSize={size}
            fill={categoryById[place.category].color}
            strokeWidth={Math.max(0.22, size * 0.2)}
            transform={angle ? `rotate(${angle} ${x} ${y})` : undefined}
          >
            {place.name}
          </text>
        );
      })}
    </g>
  );
});

/**
 * Livello "Etichette delle attività": scrive su ogni edificio la sua funzione, con gli stessi nomi dell'elenco.
 * Ogni scritta compare solo quando è abbastanza grande da leggersi.
 */
function ActivityLabelLayer({
  places,
  categoryById,
  scale,
}: {
  places: Place[];
  categoryById: Record<CategoryId, Category>;
  scale: number;
}) {
  const groups = useMemo(() => groupByMinScale(places), [places]);
  return (
    <g
      className="layer-activity-labels"
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
          <LabelGroupView key={group.minScale} group={group} categoryById={categoryById} />
        ))}
    </g>
  );
}

export default memo(ActivityLabelLayer);
