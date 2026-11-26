import { useEffect, useState } from 'react';
import type { AreaHighlight, MapData } from '../../types';
import { formatNumber } from '../../lib/format';
import CensusPanel from './CensusPanel';
import Directory from './Directory';
import type { RevealRequest } from './Directory';

/** Le due viste dell'accordion: il censimento (schede, piani, aziende) e l'elenco per quartiere e lotto. */
type View = 'census' | 'directory';
const VIEWS: { value: View; label: string }[] = [
  { value: 'census', label: 'Censimento' },
  { value: 'directory', label: 'Quartieri e lotti' },
];

interface BuildingsPanelProps {
  data: MapData;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selectedPlaceId: number | null;
  reveal: RevealRequest | null;
  onHoverArea: (area: AreaHighlight) => void;
  onHoverPlace: (placeId: number | null) => void;
  onSelectPlace: (placeId: number) => void;
}

/**
 * Un solo accordion "Edifici" con due viste dello stesso elenco: il censimento (data/censimento.json: riepilogo per zona,
 * destinazioni d'uso, edifici con piani, abitanti, addetti e aziende) e l'albero quartieri > lotti > edifici.
 * Le due viste restano montate: la ricerca e i gruppi aperti non si perdono quando si cambia vista.
 */
export default function BuildingsPanel({ data, open, onOpenChange, selectedPlaceId, reveal, onHoverArea, onHoverPlace, onSelectPlace }: BuildingsPanelProps) {
  const census = data.census;
  const [view, setView] = useState<View>(census ? 'census' : 'directory');

  // un clic su un edificio della mappa: si apre l'accordion sulla sua scheda del censimento (o sull'elenco, senza censimento)
  useEffect(() => {
    if (!reveal) return;
    onOpenChange(true);
    setView(census ? 'census' : 'directory');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reveal]);

  const count = census ? census.edifici.length + census.spazi_aperti.length : data.places.length;

  return (
    <section className={open ? 'panel-section buildings-panel is-open' : 'panel-section buildings-panel'}>
      <button type="button" className="section-toggle" aria-expanded={open} onClick={() => onOpenChange(!open)}>
        <span className="chevron" aria-hidden="true" />
        Edifici
        <span className="section-count">{formatNumber(count)} schede</span>
      </button>
      <div className="buildings-body" hidden={!open}>
        {census && (
          <div className="segmented buildings-views" role="tablist" aria-label="Vista degli edifici">
            {VIEWS.map((v) => (
              <button
                key={v.value}
                type="button"
                role="tab"
                aria-selected={view === v.value}
                className={view === v.value ? 'is-active' : undefined}
                onClick={() => setView(v.value)}
              >
                {v.label}
              </button>
            ))}
          </div>
        )}
        {census && (
          <div className="buildings-view" hidden={view !== 'census'}>
            <CensusPanel
              embedded
              census={census}
              categoryById={data.categoryById}
              open={open && view === 'census'}
              onOpenChange={onOpenChange}
              onHoverArea={onHoverArea}
              onHoverPlace={onHoverPlace}
              onSelectPlace={onSelectPlace}
              reveal={reveal}
            />
          </div>
        )}
        <div className="buildings-view" hidden={census !== null && view !== 'directory'}>
          <Directory
            data={data}
            categoryById={data.categoryById}
            selectedPlaceId={selectedPlaceId}
            reveal={reveal}
            onHoverArea={onHoverArea}
            onHoverPlace={onHoverPlace}
            onSelectPlace={onSelectPlace}
          />
        </div>
      </div>
    </section>
  );
}
