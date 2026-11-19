import { memo } from 'react';
import type { CSSProperties } from 'react';
import type { AreaHighlight, CategoryId, MapData } from '../../types';

/** L'edificio scelto; `token` cambia a ogni scelta, così l'animazione riparte anche sullo stesso edificio. */
export interface Selection {
  placeId: number;
  token: number;
}

interface HighlightLayerProps {
  data: MapData;
  area: AreaHighlight; // quartiere o lotto passato col mouse nell'elenco
  listHoverPlaceId: number | null; // edificio passato col mouse nell'elenco
  selection: Selection | null; // edificio scelto (lampeggia due volte)
}

/**
 * Evidenziazioni disegnate sopra la mappa: non intercettano il mouse (pointer-events: none).
 * Lo spessore delle linee resta costante a ogni zoom grazie a vector-effect: non-scaling-stroke (nel CSS).
 */
function HighlightLayer({ data, area, listHoverPlaceId, selection }: HighlightLayerProps) {
  let areaPath: string | null = null;
  if (area?.type === 'quarter') areaPath = data.quarterByName.get(area.name)?.path ?? null;
  if (area?.type === 'lot') areaPath = data.lotByNumber.get(area.number)?.path ?? null;

  const hovered = listHoverPlaceId !== null ? data.placeById.get(listHoverPlaceId) : undefined;
  const selected = selection ? data.placeById.get(selection.placeId) : undefined;
  const colorOf = (category: CategoryId) => ({ '--c': data.categoryById[category].color }) as CSSProperties;

  return (
    <g className="layer-highlight" pointerEvents="none">
      {areaPath && <path className={area?.type === 'quarter' ? 'highlight-quarter' : 'highlight-lot'} d={areaPath} fillRule="evenodd" />}
      {selected && selection && <path key={selection.token} className="highlight-selected" d={selected.path} />}
      {hovered && <path className="highlight-place" d={hovered.path} style={colorOf(hovered.category)} />}
    </g>
  );
}

export default memo(HighlightLayer);
