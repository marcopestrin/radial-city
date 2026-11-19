import { forwardRef, memo, useMemo, useState } from 'react';
import type { AreaHighlight, CategoryId, LayerVisibility, MapData } from '../../types';
import LayerPanel, { Toggle } from './LayerPanel';
import BusPanel from './BusPanel';
import Directory from './Directory';
import type { RevealRequest } from './Directory';

interface SidebarProps {
  data: MapData;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  layers: LayerVisibility;
  onToggleLayer: (key: keyof LayerVisibility) => void;
  hiddenBusLines: string[];
  onToggleBusLine: (id: string) => void;
  scale: number;
  selectedPlaceId: number | null;
  reveal: RevealRequest | null;
  onHoverArea: (area: AreaHighlight) => void;
  onHoverPlace: (placeId: number | null) => void;
  onSelectPlace: (placeId: number) => void;
}

/**
 * La legenda a sinistra: titolo, livelli e colori, linee autobus, interruttore delle etichette delle attività,
 * elenco degli edifici con la ricerca. Si può chiudere per lasciare tutta la finestra alla mappa.
 */
const Sidebar = forwardRef<HTMLElement, SidebarProps>(function Sidebar(props, ref) {
  const { data, open, onOpenChange, layers, onToggleLayer, scale } = props;
  const [layersOpen, setLayersOpen] = useState(false);
  const [busOpen, setBusOpen] = useState(false);

  const placeCountByCategory = useMemo(() => {
    const counts = {} as Record<CategoryId, number>;
    for (const place of data.places) counts[place.category] = (counts[place.category] ?? 0) + 1;
    return counts;
  }, [data]);

  return (
    <aside ref={ref} className={open ? 'sidebar card' : 'sidebar card is-closed'}>
      <header>
        <div>
          <h1>Città Radiale</h1>
          <div className="subtitle">Mappa 7 × 7 km</div>
        </div>
        <button
          type="button"
          className="collapse-button"
          aria-expanded={open}
          aria-controls="sidebar-body"
          title="Mostra o nascondi la legenda"
          onClick={() => onOpenChange(!open)}
        >
          {open ? '–' : '+'}
        </button>
      </header>

      {/* il contenuto resta montato anche a legenda chiusa: ricerca e gruppi aperti non si perdono */}
      <div className="sidebar-body" id="sidebar-body" hidden={!open}>
        <LayerPanel
          layers={layers}
          onToggle={onToggleLayer}
          scale={scale}
          minZoom={data.world.minZoom}
          categories={data.categories}
          placeCountByCategory={placeCountByCategory}
          open={layersOpen}
          onOpenChange={setLayersOpen}
        />
        <BusPanel
          visible={layers.busLines}
          onToggleVisible={() => onToggleLayer('busLines')}
          lines={data.bus.lines}
          hiddenLines={props.hiddenBusLines}
          onToggleLine={props.onToggleBusLine}
          open={busOpen}
          onOpenChange={setBusOpen}
        />
        <div className="activity-toggle">
          <Toggle label="Etichette delle attività sulla mappa" checked={layers.activityLabels} onChange={() => onToggleLayer('activityLabels')} />
          <p className="caption">Scrive su ogni edificio la sua funzione, come nell'elenco; le scritte compaiono man mano che ingrandisci.</p>
        </div>
        <Directory
          data={data}
          categoryById={data.categoryById}
          selectedPlaceId={props.selectedPlaceId}
          reveal={props.reveal}
          onHoverArea={props.onHoverArea}
          onHoverPlace={props.onHoverPlace}
          onSelectPlace={props.onSelectPlace}
        />
      </div>
    </aside>
  );
});

export default memo(Sidebar);
