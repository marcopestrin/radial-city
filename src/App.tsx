import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { AreaHighlight, LayerVisibility, MapData } from './types';
import { loadMapData } from './data/loadMapData';
import { readStored, writeStored } from './lib/storage';
import { useViewport } from './hooks/useViewport';
import type { FreeArea } from './hooks/useViewport';
import MapView from './components/MapView';
import Sidebar from './components/sidebar/Sidebar';
import type { RevealRequest } from './components/sidebar/Directory';
import type { Selection } from './components/layers/HighlightLayer';
import Tooltip from './components/Tooltip';
import ZoomControls from './components/ZoomControls';
import ScaleBar from './components/ScaleBar';

/** Livelli accesi all'apertura (poi si ricordano le scelte dell'utente). */
const DEFAULT_LAYERS: LayerVisibility = {
  satellite: true,
  quarterTint: false,
  quarterNames: true,
  streetNames: true,
  lotOutlines: false,
  lotNumbers: true,
  activityLabels: false,
  heightLabels: false,
  residentLabels: false,
  jobLabels: false,
  busLines: true,
  activityOutlines: true,
};
const STORAGE_KEY = 'citta-radiale-mappa';

/** Sotto questa larghezza la legenda copre la mappa: non si tiene conto del suo spazio. */
const NARROW_SCREEN_PX = 760;

interface HoverTooltip {
  placeId: number;
  x: number;
  y: number;
}

/**
 * Il componente principale: carica i dati e tiene lo stato condiviso tra mappa e legenda
 * (livelli accesi, luogo sotto il mouse, luogo scelto, area evidenziata).
 */
export default function App() {
  const [data, setData] = useState<MapData | null>(null);
  const [error, setError] = useState<string | null>(null);

  // le scelte salvate si leggono una volta sola, alla prima apertura
  const [stored] = useState(() =>
    readStored(STORAGE_KEY, { layers: DEFAULT_LAYERS, sidebarOpen: window.innerWidth >= 600, hiddenBusLines: [] as string[] }),
  );
  const [layers, setLayers] = useState<LayerVisibility>({ ...DEFAULT_LAYERS, ...stored.layers });
  const [hiddenBusLines, setHiddenBusLines] = useState<string[]>(Array.isArray(stored.hiddenBusLines) ? stored.hiddenBusLines : []);
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(stored.sidebarOpen);

  const [tooltip, setTooltip] = useState<HoverTooltip | null>(null);
  const [listHoverPlaceId, setListHoverPlaceId] = useState<number | null>(null);
  const [area, setArea] = useState<AreaHighlight>(null);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [reveal, setReveal] = useState<RevealRequest | null>(null);

  const svgRef = useRef<SVGSVGElement>(null);
  const sidebarRef = useRef<HTMLElement>(null);

  // ---------------------------------------------------------------- dati
  useEffect(() => {
    loadMapData()
      .then(setData)
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : String(reason)));
  }, []);

  useEffect(() => {
    writeStored(STORAGE_KEY, { layers, sidebarOpen, hiddenBusLines });
  }, [layers, sidebarOpen, hiddenBusLines]);

  // ---------------------------------------------------------------- zoom e spostamento
  /** La parte di finestra non coperta dalla legenda: è lì che la mappa si centra. */
  const getFreeArea = useCallback((): FreeArea => {
    const width = window.innerWidth;
    const height = window.innerHeight;
    const sidebar = sidebarRef.current;
    if (sidebar && sidebarOpen && width > NARROW_SCREEN_PX) {
      const x0 = sidebar.getBoundingClientRect().right + 12;
      return { x0, width: width - x0, height };
    }
    return { x0: 0, width, height };
  }, [sidebarOpen]);

  const { view, dragging, zoomAt, fit, flyTo } = useViewport(svgRef, data?.world ?? null, getFreeArea);

  // la prima volta si mostra tutta la città
  const fitted = useRef(false);
  useLayoutEffect(() => {
    if (data && !fitted.current) {
      fitted.current = true;
      fit();
    }
  }, [data, fit]);

  const zoomAtCentre = (factor: number) => zoomAt(factor, window.innerWidth / 2, window.innerHeight / 2);

  // ---------------------------------------------------------------- interazioni
  const toggleLayer = useCallback((key: keyof LayerVisibility) => {
    setLayers((current) => ({ ...current, [key]: !current[key] }));
  }, []);

  /** Accende o spegne una linea autobus; accenderne una riaccende anche il livello "Linee autobus". */
  const toggleBusLine = useCallback((id: string) => {
    setHiddenBusLines((current) => {
      const showing = current.includes(id);
      if (showing) setLayers((l) => (l.busLines ? l : { ...l, busLines: true }));
      return showing ? current.filter((x) => x !== id) : [...current, id];
    });
  }, []);

  /** Sceglie un edificio: lo evidenzia e, se richiesto, vola fin lì. */
  const select = useCallback(
    (placeId: number, fly: boolean) => {
      setSelection({ placeId, token: performance.now() });
      if (fly && data) {
        const place = data.placeById.get(placeId);
        if (place) flyTo(place.bbox);
      }
    },
    [data, flyTo],
  );

  const handleSelectFromList = useCallback(
    (placeId: number) => {
      setTooltip(null);
      select(placeId, true);
    },
    [select],
  );

  const handleHoverOnMap = useCallback((placeId: number | null, x: number, y: number) => {
    setTooltip(placeId === null ? null : { placeId, x, y });
  }, []);

  const handleClickOnMap = useCallback(
    (placeId: number, x: number, y: number, fromTouch: boolean) => {
      if (fromTouch) {
        // sul telefono il tocco mostra il tooltip (non c'è il passaggio del mouse)
        setTooltip({ placeId, x, y });
        return;
      }
      select(placeId, false);
      // il perimetro di un'attività apre nell'elenco l'edificio che la contiene
      const container = data?.censusActivityByPlace.get(placeId)?.building.luoghi[0];
      setReveal({ placeId: container ?? placeId, token: performance.now() });
      setSidebarOpen(true);
    },
    [select, data],
  );

  const handleClickEmpty = useCallback(() => setTooltip(null), []);

  // ---------------------------------------------------------------- disegno
  if (error) {
    return <div className="message">Errore nel caricamento della mappa: {error}</div>;
  }
  if (!data) {
    return <div className="message">Caricamento della mappa…</div>;
  }

  const tooltipPlace = tooltip ? data.placeById.get(tooltip.placeId) : undefined;

  return (
    <>
      <MapView
        svgRef={svgRef}
        data={data}
        view={view}
        dragging={dragging}
        layers={layers}
        hiddenBusLines={hiddenBusLines}
        area={area}
        listHoverPlaceId={listHoverPlaceId}
        selection={selection}
        onHoverPlace={handleHoverOnMap}
        onClickPlace={handleClickOnMap}
        onClickEmpty={handleClickEmpty}
      />
      <Sidebar
        ref={sidebarRef}
        data={data}
        open={sidebarOpen}
        onOpenChange={setSidebarOpen}
        layers={layers}
        onToggleLayer={toggleLayer}
        hiddenBusLines={hiddenBusLines}
        onToggleBusLine={toggleBusLine}
        scale={view.scale}
        selectedPlaceId={selection?.placeId ?? null}
        reveal={reveal}
        onHoverArea={setArea}
        onHoverPlace={setListHoverPlaceId}
        onSelectPlace={handleSelectFromList}
      />
      {tooltip && tooltipPlace && (
        <Tooltip
          place={tooltipPlace}
          category={data.categoryById[tooltipPlace.category]}
          building={data.censusBuildingByPlace.get(tooltipPlace.id)}
          space={data.censusSpaceByPlace.get(tooltipPlace.id)}
          activity={data.censusActivityByPlace.get(tooltipPlace.id)}
          clientX={tooltip.x}
          clientY={tooltip.y}
        />
      )}
      <ZoomControls onZoomIn={() => zoomAtCentre(1.6)} onZoomOut={() => zoomAtCentre(1 / 1.6)} onShowAll={fit} />
      <ScaleBar scale={view.scale} />
    </>
  );
}
