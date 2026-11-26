import { forwardRef, memo, useState } from 'react';
import type { AreaHighlight, LayerVisibility, MapData } from '../../types';
import LayerPanel from './LayerPanel';
import BusPanel from './BusPanel';
import BuildingsPanel from './BuildingsPanel';
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
 * La legenda a sinistra: titolo, livelli e colori, linee autobus, e l'accordion
 * degli edifici (censimento ed elenco per quartiere e lotto). Si può chiudere per lasciare tutta la finestra alla mappa.
 */
const Sidebar = forwardRef<HTMLElement, SidebarProps>(function Sidebar(props, ref) {
  const { data, open, onOpenChange, layers, onToggleLayer, scale } = props;
  const [busOpen, setBusOpen] = useState(false);
  const [buildingsOpen, setBuildingsOpen] = useState(true);

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
        <LayerPanel layers={layers} onToggle={onToggleLayer} scale={scale} minZoom={data.world.minZoom} />
        <BusPanel
          visible={layers.busLines}
          onToggleVisible={() => onToggleLayer('busLines')}
          lines={data.bus.lines}
          hiddenLines={props.hiddenBusLines}
          onToggleLine={props.onToggleBusLine}
          open={busOpen}
          onOpenChange={setBusOpen}
        />
        <BuildingsPanel
          data={data}
          open={buildingsOpen}
          onOpenChange={setBuildingsOpen}
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
