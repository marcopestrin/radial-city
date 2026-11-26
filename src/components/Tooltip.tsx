import { useLayoutEffect, useRef, useState } from 'react';
import type { Category, CensusActivity, CensusBuilding, CensusOpenSpace, Place } from '../types';
import { formatNumber, placeLocation } from '../lib/format';

interface TooltipProps {
  place: Place;
  category: Category;
  /** La scheda del censimento dell'edificio (o dello spazio aperto), se c'è. */
  building?: CensusBuilding;
  space?: CensusOpenSpace;
  /** Se il luogo è il perimetro di un'attività dentro un edificio: l'attività e l'edificio. */
  activity?: CensusActivity;
  clientX: number;
  clientY: number;
}

/** Il riquadro con il nome del luogo sotto il mouse. Si sposta per non uscire dallo schermo. */
export default function Tooltip({ place, category, building, space, activity, clientX, clientY }: TooltipProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ left: clientX + 16, top: clientY + 16 });

  useLayoutEffect(() => {
    const box = ref.current;
    if (!box) return;
    const width = box.offsetWidth;
    const height = box.offsetHeight;
    let left = clientX + 16;
    let top = clientY + 16;
    if (left + width > window.innerWidth - 8) left = clientX - width - 12;
    if (top + height > window.innerHeight - 8) top = clientY - height - 12;
    setPosition({ left, top });
  }, [clientX, clientY, place.id]);

  return (
    <div ref={ref} className="tooltip card" role="tooltip" style={position}>
      <strong>
        <i style={{ background: category.color }} />
        {place.name}
      </strong>
      <span>{placeLocation(place.lot, place.quarter)}</span>
      {activity ? <ActivityInfo activity={activity} /> : building ? <BuildingInfo building={building} /> : space ? <SpaceInfo space={space} /> : (
        place.workers !== undefined && (
          <span>
            {place.floors ? `${place.floors} ${place.floors === 1 ? 'piano' : 'piani'} · ` : ''}
            {place.workers > 0
              ? `${formatNumber(place.workers)} ${place.workers === 1 ? 'lavoratore' : 'lavoratori'}`
              : 'nessun addetto fisso'}
          </span>
        )
      )}
    </div>
  );
}

/** Una singola attività (negozio, bar, ufficio...) e l'edificio in cui sta. */
function ActivityInfo({ activity: { company: a, building: b } }: { activity: CensusActivity }) {
  const floors = a.piani.length === 0 ? '' : a.piani.length === 1 ? `piano ${a.piani[0]}` : `piani ${a.piani[0]}–${a.piani[a.piani.length - 1]}`;
  return (
    <>
      {a.ramo && <span>{a.ramo}</span>}
      <span>
        {formatNumber(a.dipendenti)} {a.dipendenti === 1 ? 'addetto' : 'addetti'}
        {floors ? ` · ${floors}` : ''}
      </span>
      <span className="tooltip-company">
        in {b.nome} ({b.codice}) · {b.destinazione_uso}
      </span>
    </>
  );
}

/** Quante aziende si elencano nel tooltip prima di "e altre". */
const MAX_COMPANIES = 3;

/** I dati del censimento di un edificio: codice, uso, piani, chi ci vive e chi ci lavora. */
function BuildingInfo({ building: b }: { building: CensusBuilding }) {
  const companies = b.aziende ?? [];
  return (
    <>
      <span>
        {b.codice} · {b.destinazione_uso} · {b.piani_totali} {b.piani_totali === 1 ? 'piano' : 'piani'}
      </span>
      {b.abitanti > 0 && <span>{formatNumber(b.abitanti)} {b.abitanti === 1 ? 'abitante' : 'abitanti'}</span>}
      <span>
        {b.posti_di_lavoro > 0
          ? `${formatNumber(b.posti_di_lavoro)} ${b.posti_di_lavoro === 1 ? 'addetto' : 'addetti'}`
          : b.abitanti > 0
            ? null
            : 'nessun addetto fisso'}
      </span>
      {companies.slice(0, MAX_COMPANIES).map((a) => (
        <span key={a.azienda} className="tooltip-company">
          {a.azienda}
          {a.ramo ? `, ${a.ramo}` : ''} · {formatNumber(a.dipendenti)}
        </span>
      ))}
      {companies.length > MAX_COMPANIES && <span className="tooltip-company">e altre {companies.length - MAX_COMPANIES}</span>}
    </>
  );
}

/** I dati del censimento di uno spazio aperto o di una struttura. */
function SpaceInfo({ space: s }: { space: CensusOpenSpace }) {
  return (
    <span>
      {s.codice} · {s.tipo} · {formatNumber(s.superficie_m2)} m²
      {s.posti_di_lavoro > 0 ? ` · ${formatNumber(s.posti_di_lavoro)} addetti` : ''}
    </span>
  );
}
