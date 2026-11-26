import { useMemo, useRef } from 'react';
import type { PointerEvent as ReactPointerEvent, RefObject } from 'react';
import type { AreaHighlight, LayerVisibility, MapData } from '../types';
import type { ViewportState } from '../hooks/useViewport';
import SatelliteLayer from './layers/SatelliteLayer';
import QuarterTintLayer from './layers/QuarterTintLayer';
import LotOutlineLayer from './layers/LotOutlineLayer';
import QuarterNameLayer from './layers/QuarterNameLayer';
import LotNumberLayer from './layers/LotNumberLayer';
import StreetNameLayer from './layers/StreetNameLayer';
import PlaceLayer from './layers/PlaceLayer';
import HighlightLayer from './layers/HighlightLayer';
import type { Selection } from './layers/HighlightLayer';
import ActivityLabelLayer from './layers/ActivityLabelLayer';
import FigureLabelLayer from './layers/FigureLabelLayer';
import BusLayer from './layers/BusLayer';

interface MapViewProps {
  svgRef: RefObject<SVGSVGElement>;
  data: MapData;
  view: ViewportState;
  dragging: boolean;
  layers: LayerVisibility;
  /** Linee autobus spente dalla legenda. */
  hiddenBusLines: string[];
  area: AreaHighlight;
  listHoverPlaceId: number | null;
  selection: Selection | null;
  /** Il mouse è sopra un luogo (o non più: id null). */
  onHoverPlace: (placeId: number | null, clientX: number, clientY: number) => void;
  /** Clic (senza trascinare) su un luogo. `fromTouch` è vero per il tocco sul telefono. */
  onClickPlace: (placeId: number, clientX: number, clientY: number, fromTouch: boolean) => void;
  /** Clic o tocco sulla mappa fuori da ogni luogo. */
  onClickEmpty: () => void;
}

/** Da questo zoom si vedono i contorni dei nuovi edifici (public/data/perimetri.json); quelli delle attività da `world.minZoom.activities`. */
const FOOTPRINT_MIN_SCALE = 0.35;

/** Oltre questo spostamento (in pixel) un clic diventa un trascinamento. */
const CLICK_TOLERANCE_PX = 6;

/** Trova l'id del luogo sotto il puntatore leggendo l'attributo data-place-id. */
function placeIdFromTarget(target: EventTarget | null): number | null {
  const element = target instanceof Element ? target.closest('[data-place-id]') : null;
  return element ? Number(element.getAttribute('data-place-id')) : null;
}

/**
 * La mappa: un unico <svg> a tutto schermo.
 * Il gruppo principale porta la trasformazione dello zoom; dentro, i livelli sono in metri.
 * L'ordine dei livelli è l'ordine di disegno: dal satellite (sotto) alle etichette (sopra).
 */
export default function MapView(props: MapViewProps) {
  const { svgRef, data, view, dragging, layers, hiddenBusLines, area, listHoverPlaceId, selection } = props;
  const { world } = data;
  const pointerDown = useRef<{ x: number; y: number; target: EventTarget | null } | null>(null);

  const transform = `translate(${view.tx} ${view.ty}) scale(${view.scale}) translate(${-world.x} ${-world.y})`;

  // ---------------------------------------------------------------- mouse e tocco sui luoghi
  const handlePointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (event.pointerType !== 'mouse') return; // sul telefono il tooltip compare al tocco
    if (dragging) {
      props.onHoverPlace(null, 0, 0);
      return;
    }
    props.onHoverPlace(placeIdFromTarget(event.target), event.clientX, event.clientY);
  };

  const handlePointerDown = (event: ReactPointerEvent<SVGSVGElement>) => {
    pointerDown.current = { x: event.clientX, y: event.clientY, target: event.target };
  };

  const handlePointerUp = (event: ReactPointerEvent<SVGSVGElement>) => {
    const down = pointerDown.current;
    pointerDown.current = null;
    if (!down) return;
    const moved = Math.hypot(event.clientX - down.x, event.clientY - down.y) > CLICK_TOLERANCE_PX;
    if (moved) return;
    const placeId = placeIdFromTarget(down.target);
    if (placeId === null) props.onClickEmpty();
    else props.onClickPlace(placeId, event.clientX, event.clientY, event.pointerType !== 'mouse');
  };

  const showStreets = layers.streetNames && view.scale >= world.minZoom.streets;
  const showFigures = layers.heightLabels || layers.residentLabels || layers.jobLabels;
  const figureKinds = useMemo(
    () => ({ height: layers.heightLabels, residents: layers.residentLabels, jobs: layers.jobLabels }),
    [layers.heightLabels, layers.residentLabels, layers.jobLabels],
  );
  const showLotNumbers = layers.lotNumbers && view.scale >= world.minZoom.lotNumbers;
  // i perimetri si mostrano e si possono scegliere con il mouse solo da questo zoom: più lontano resta l'edificio intero
  const mapClass = [
    'map',
    dragging && 'is-dragging',
    layers.activityOutlines && view.scale >= FOOTPRINT_MIN_SCALE && 'show-footprints',
    layers.activityOutlines && view.scale >= world.minZoom.activities && 'show-activities',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <svg
      ref={svgRef}
      className={mapClass}
      xmlns="http://www.w3.org/2000/svg"
      textRendering="geometricPrecision"
      role="img"
      aria-label="Mappa di Città Radiale"
      onPointerMove={handlePointerMove}
      onPointerLeave={() => props.onHoverPlace(null, 0, 0)}
      onPointerDown={handlePointerDown}
      onPointerUp={handlePointerUp}
    >
      <g transform={transform}>
        {layers.satellite && <SatelliteLayer tiles={world.tiles} />}
        {layers.quarterTint && <QuarterTintLayer quarters={data.quarters} />}
        {layers.lotOutlines && <LotOutlineLayer lots={data.lots} />}
        {layers.quarterNames && <QuarterNameLayer quarters={data.quarters} />}
        {showLotNumbers && <LotNumberLayer lots={data.lots} />}
        {showStreets && <StreetNameLayer streets={data.streets} />}
        <HighlightLayer data={data} area={area} listHoverPlaceId={listHoverPlaceId} selection={selection} />
        <PlaceLayer places={data.places} categoryById={data.categoryById} />
        {layers.busLines && <BusLayer bus={data.bus} scale={view.scale} hiddenLines={hiddenBusLines} />}
        {layers.activityLabels && <ActivityLabelLayer places={data.places} categoryById={data.categoryById} scale={view.scale} />}
        {showFigures && (
          <FigureLabelLayer places={data.places} buildings={data.censusBuildingByPlace} kinds={figureKinds} scale={view.scale} />
        )}
      </g>
    </svg>
  );
}
