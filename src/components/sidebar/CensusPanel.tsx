import { useEffect, useMemo, useRef, useState } from 'react';
import type { CSSProperties } from 'react';
import type { AreaHighlight, Category, CategoryId, Census, CensusBuilding, CensusCompany, CensusFloor, CensusSummary, CensusUse } from '../../types';
import { formatNumber } from '../../lib/format';

interface CensusPanelProps {
  census: Census;
  categoryById: Record<CategoryId, Category>;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onHoverArea: (area: AreaHighlight) => void;
  onHoverPlace: (placeId: number | null) => void;
  onSelectPlace: (placeId: number) => void;
  /** Un edificio cliccato sulla mappa: se è censito, la sezione si apre sulla sua scheda e sulla sua riga. */
  reveal: { placeId: number; token: number } | null;
  /** Dentro un altro accordion: solo il corpo, senza la sua sezione e il suo pulsante. */
  embedded?: boolean;
}

/** La scheda di un edificio: la strada per quelli del fronte strada, altrimenti il quartiere. */
const zoneOf = (b: { zona?: string; quartiere: string }) => b.zona ?? b.quartiere;

/** Colore di ogni destinazione d'uso: quello della categoria corrispondente della mappa. */
const USE_CATEGORY: Record<CensusUse, CategoryId | null> = {
  residenziale: 'res',
  misto: 'res',
  ufficio: 'uff',
  negozio: 'com',
  fabbrica: 'ind',
  'servizio pubblico': 'pub',
  ricettivo: 'com',
  parcheggio: null,
  deposito: 'ind',
  agricolo: 'agr',
  ferroviario: 'ind',
  impianto: 'ind',
};
const USE_ORDER: CensusUse[] = ['residenziale', 'misto', 'ufficio', 'negozio', 'fabbrica', 'servizio pubblico', 'ricettivo', 'parcheggio', 'deposito', 'agricolo', 'ferroviario', 'impianto'];
const USE_LABEL: Record<CensusUse, string> = {
  residenziale: 'Residenziale',
  misto: 'Misto (case e negozi)',
  ufficio: 'Uffici',
  negozio: 'Negozi',
  fabbrica: 'Fabbriche e laboratori',
  'servizio pubblico': 'Servizi pubblici',
  ricettivo: 'Alberghi',
  parcheggio: 'Parcheggi',
  deposito: 'Depositi, silos e magazzini',
  agricolo: 'Stalle, serre e cascine',
  ferroviario: 'Ferrovia',
  impianto: 'Impianti',
};
const TOTAL = 'Totale';

const n = (value: number) => formatNumber(Math.round(value));
const decimal = (value: number, digits = 1) => formatNumber(Number(value.toFixed(digits)));
const percent = (value: number) => `${decimal(value * 100, 0)}%`;

function useColor(use: CensusUse, categoryById: Record<CategoryId, Category>): string {
  const id = USE_CATEGORY[use];
  return id ? categoryById[id].color : '#8a8d90';
}

/** I numeri principali di un quartiere, in una griglia. */
function SummaryGrid({ summary }: { summary: CensusSummary }) {
  const items: [string, string, string?][] = [
    ['Edifici', n(summary.edifici), `${summary.lotti} lotti, ${summary.lotti_senza_edifici} senza edifici`],
    ['Abitanti', n(summary.abitanti), summary.abitanti_in_villette ? `${n(summary.abitanti_in_villette)} nelle villette` : undefined],
    ['Alloggi', n(summary.alloggi)],
    ['Attività', n(summary.attivita), 'imprese ed enti'],
    ['Posti di lavoro', n(summary.posti_di_lavoro)],
    ['Posti liberi', n(summary.posti_liberi ?? 0), 'spazio per altre imprese, non ancora occupato'],
  ];
  return (
    <dl className="census-grid">
      {items.map(([label, value, note]) => (
        <div key={label} title={note}>
          <dt>{label}</dt>
          <dd>{value}</dd>
          {note && <dd className="census-note">{note}</dd>}
        </div>
      ))}
    </dl>
  );
}

/** Piani consecutivi con la stessa attività, per scriverli in una riga sola ("piani 9–12"); i piani con le aziende in
 * affitto restano uno per riga, perché ognuno ha le sue. */
function groupFloors(floors: CensusFloor[]): CensusFloor[][] {
  const groups: CensusFloor[][] = [];
  for (const f of floors) {
    const last = groups[groups.length - 1];
    if (last && !f.aziende && !last[0].aziende && last[0].attivita === f.attivita && last[0].destinazione_uso === f.destinazione_uso)
      last.push(f);
    else groups.push([f]);
  }
  return groups;
}

const floorName = (piano: number) => (piano === 0 ? 'PT' : String(piano));

/** La sezione dell'edificio: i piani dall'alto in basso, ognuno con la sua destinazione d'uso. */
function FloorList({ floors, categoryById }: { floors: CensusFloor[]; categoryById: Record<CategoryId, Category> }) {
  return (
    <ol className="census-floors">
      {groupFloors(floors)
        .reverse()
        .map((g) => {
          const first = g[0].piano;
          const last = g[g.length - 1].piano;
          const sum = (key: 'abitanti' | 'posti_di_lavoro' | 'alloggi') => g.reduce((t, f) => t + f[key], 0);
          const rooms = g.reduce((t, f) => t + (f.camere ?? 0), 0);
          const free = g.reduce((t, f) => t + (f.posti_liberi ?? 0), 0);
          const figures = [
            sum('abitanti') > 0 && (sum('alloggi') > 0 ? `${n(sum('abitanti'))} ab. in ${n(sum('alloggi'))} alloggi` : `${n(sum('abitanti'))} posti letto`),
            rooms > 0 && `${n(rooms)} camere`,
            sum('posti_di_lavoro') > 0 && `${n(sum('posti_di_lavoro'))} lav.`,
            free > 0 && `${n(free)} posti liberi`,
          ].filter(Boolean);
          return (
            <li key={first} title={`${g.length} ${g.length === 1 ? 'piano' : 'piani'} da ${n(g[0].superficie_m2)} m²`}>
              <span className="census-floor-number">{first === last ? floorName(first) : `${floorName(first)}–${last}`}</span>
              <i style={{ background: useColor(g[0].destinazione_uso, categoryById) }} aria-hidden="true" />
              <span className="census-floor-what">
                {g[0].attivita}
                {figures.length > 0 && <small>{figures.join(' · ')}</small>}
                {g[0].aziende && g[0].aziende.length > 0 && (
                  <small className="census-floor-companies">
                    {g[0].aziende.map((a) => `${a.azienda}: ${n(a.dipendenti)}`).join(' · ')}
                  </small>
                )}
              </span>
            </li>
          );
        })}
    </ol>
  );
}

const floorRange = (piani: number[]) =>
  piani.length === 1 ? `piano ${floorName(piani[0])}` : `piani ${floorName(piani[0])}–${piani[piani.length - 1]}`;

/** Le aziende negli uffici in affitto: una riga per azienda, con ramo, dipendenti e piani. */
function CompanyList({ companies }: { companies: CensusCompany[] }) {
  return (
    <ol className="census-companies">
      {companies.map((a) => (
        <li key={a.azienda}>
          {a.ramo && <span className="census-company-name">{a.azienda}</span>}
          <span className="census-company-what">
            {a.ramo ?? a.azienda}
            <small>{floorRange(a.piani)}</small>
          </span>
          <span className="census-company-staff">{n(a.dipendenti)} dip.</span>
        </li>
      ))}
    </ol>
  );
}

/** L'intestazione di un lotto nell'elenco: ogni edificio è censito come parte del suo lotto. */
function LotHeader({ census, zona, lotto, onHoverArea }: { census: Census; zona: string; lotto: number | null; onHoverArea: (area: AreaHighlight) => void }) {
  const es = census.edifici.filter((e) => zoneOf(e) === zona && e.lotto === lotto);
  const quartiere = es[0]?.quartiere;
  const ab = es.reduce((t, e) => t + e.abitanti, 0);
  const jobs = es.reduce((t, e) => t + e.posti_di_lavoro, 0);
  return (
    <li className="census-lot" onMouseEnter={() => lotto !== null && onHoverArea({ type: 'lot', number: lotto })} onMouseLeave={() => onHoverArea(null)}>
      <span className="census-lot-name">
        {lotto === null ? 'Fuori lotto' : `Lotto ${lotto}`}
        {quartiere && quartiere !== zona && <small> · {quartiere}</small>}
      </span>
      <span>
        {es.length} {es.length === 1 ? 'edificio' : 'edifici'}
        {ab > 0 && ` · ${n(ab)} ab.`}
        {jobs > 0 && ` · ${n(jobs)} lav.`}
      </span>
    </li>
  );
}

/** Una riga dell'elenco: si apre per mostrare tutti i dati dell'edificio. */
function BuildingRow(props: {
  building: CensusBuilding;
  categoryById: Record<CategoryId, Category>;
  color: string;
  expanded: boolean;
  onToggle: () => void;
  onHoverArea: (area: AreaHighlight) => void;
  onHoverPlace: (placeId: number | null) => void;
  onSelectPlace: (placeId: number) => void;
}) {
  const { building: b, color, expanded } = props;
  const placeId = b.luoghi[0];
  const enter = () => {
    if (b.lotto !== null) props.onHoverArea({ type: 'lot', number: b.lotto });
    if (placeId !== undefined) props.onHoverPlace(placeId);
  };
  const leave = () => {
    props.onHoverArea(null);
    props.onHoverPlace(null);
  };
  return (
    <li className={expanded ? 'census-row is-open' : 'census-row'} data-codice={b.codice}>
      <button
        type="button"
        className="census-button"
        aria-expanded={expanded}
        style={{ '--c': color } as CSSProperties}
        onMouseEnter={enter}
        onMouseLeave={leave}
        onFocus={enter}
        onBlur={leave}
        onClick={() => {
          props.onToggle();
          if (!expanded && placeId !== undefined) props.onSelectPlace(placeId);
        }}
      >
        <i aria-hidden="true" />
        <span className="census-code">{b.codice}</span>
        <span className="census-name">
          {b.nome}
          <small>
            Lotto {b.lotto} · {b.destinazione_uso} · {b.piani_totali} {b.piani_totali === 1 ? 'piano' : 'piani'}
          </small>
        </span>
        <span className="census-figures">
          {b.abitanti > 0 && <span title="abitanti">{n(b.abitanti)} ab.</span>}
          {b.posti_di_lavoro > 0 && <span title="posti di lavoro">{n(b.posti_di_lavoro)} lav.</span>}
        </span>
      </button>
      {expanded && (
        <dl className="census-detail">
          <dt>Destinazione</dt>
          <dd>
            {b.categoria}
          </dd>
          <dt>Piani</dt>
          <dd>
            {b.piani_totali}
            {b.altezza_m !== undefined && ` · alto ${decimal(b.altezza_m)} m`}
          </dd>
          <dt>Superficie</dt>
          <dd>
            impronta {n(b.superficie_impronta_m2)} m² · lorda {n(b.superficie_lorda_m2)} m²
          </dd>
          <dt>Abitanti</dt>
          <dd>
            {n(b.abitanti)} · {n(b.alloggi)} alloggi
          </dd>
          <dt>Attività</dt>
          <dd>
            {n(b.attivita)} · {n(b.posti_di_lavoro)} posti di lavoro
          </dd>
          {b.piani && b.piani.length > 0 && (
            <>
              <dt className="census-wide">Piano per piano</dt>
              <dd className="census-wide">
                <FloorList floors={b.piani} categoryById={props.categoryById} />
              </dd>
            </>
          )}
          {b.aziende && b.aziende.length > 0 && (
            <>
              <dt className="census-wide">
                Imprese: {b.aziende.length}, {n(b.aziende.reduce((t, a) => t + a.dipendenti, 0))} dipendenti
                {(b.posti_liberi ?? 0) > 0 && `, ${n(b.posti_liberi ?? 0)} posti liberi`}
              </dt>
              <dd className="census-wide">
                <CompanyList companies={b.aziende} />
              </dd>
            </>
          )}
          {b.unita.length > 0 && (
            <>
              <dt>Al piano terra</dt>
              <dd>
                {b.unita.map((u) => (
                  <span key={u.luogo} className="census-unit">
                    {u.nome} ({n(u.posti_di_lavoro)} lav.)
                  </span>
                ))}
              </dd>
            </>
          )}
        </dl>
      )}
    </li>
  );
}

/**
 * Sezione a scomparsa col censimento (data/censimento.json) di tutti gli edifici della mappa (le villette sono in
 * censimento_villette.json): riepilogo per zona,
 * destinazioni d'uso e l'elenco di tutti gli edifici, con ricerca e filtro. Passando su un edificio si illumina
 * il suo lotto; cliccandolo si aprono i suoi dati e, se è un edificio della mappa, viene scelto.
 */
export default function CensusPanel({ census, categoryById, open, onOpenChange, onHoverArea, onHoverPlace, onSelectPlace, reveal, embedded }: CensusPanelProps) {
  const quarters = [...census.meta.quartieri, TOTAL];
  const [quarter, setQuarter] = useState<string>(quarters[0]);
  const [query, setQuery] = useState('');
  const [use, setUse] = useState<CensusUse | ''>('');
  const [expanded, setExpanded] = useState<string | null>(null);
  const [showAssumptions, setShowAssumptions] = useState(false);
  const listRef = useRef<HTMLUListElement>(null);
  const scrollTo = useRef<string | null>(null);

  // un edificio cliccato sulla mappa: si apre la sua scheda con la sua riga aperta (i filtri si tolgono)
  useEffect(() => {
    if (!reveal) return;
    const b = census.edifici.find((e) => e.luoghi.includes(reveal.placeId));
    if (!b) return;
    onOpenChange(true);
    setQuarter(zoneOf(b));
    setQuery('');
    setUse('');
    setExpanded(b.codice);
    scrollTo.current = b.codice;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reveal, census]);

  const summary = census.riepilogo[quarter];
  const buildings = useMemo(() => {
    const q = query.trim().toLowerCase();
    return census.edifici.filter(
      (b) =>
        (quarter === TOTAL || zoneOf(b) === quarter) &&
        (use === '' || b.destinazione_uso === use) &&
        (q === '' ||
          b.codice.toLowerCase().includes(q) ||
          b.nome.toLowerCase().includes(q) ||
          `lotto ${b.lotto}` === q ||
          String(b.lotto) === q),
    );
  }, [census, quarter, use, query]);
  const spaces = census.spazi_aperti.filter((s) => quarter === TOTAL || s.quartiere === quarter);

  // dopo l'apertura dal clic sulla mappa, la riga dell'edificio si porta in vista
  useEffect(() => {
    const codice = scrollTo.current;
    if (!codice || !open || !listRef.current) return;
    const row = listRef.current.querySelector(`[data-codice="${codice}"]`);
    if (row) {
      row.scrollIntoView({ block: 'nearest' });
      scrollTo.current = null;
    }
  });
  const p = census.meta.parametri;

  const body = summary && (
        <>
          {quarters.length > 8 ? (
            <select
              className="census-select"
              aria-label="Zona del censimento"
              value={quarter}
              onChange={(event) => {
                setQuarter(event.target.value);
                setExpanded(null);
              }}
            >
              {quarters.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          ) : (
            <div className="segmented census-tabs" role="tablist" aria-label="Zona del censimento">
              {quarters.map((name) => (
                <button
                  key={name}
                  type="button"
                  role="tab"
                  aria-selected={quarter === name}
                  className={quarter === name ? 'is-active' : undefined}
                  onClick={() => {
                    setQuarter(name);
                    setExpanded(null);
                  }}
                >
                  {name}
                </button>
              ))}
            </div>
          )}

          <SummaryGrid summary={summary} />

          <h2>Destinazioni d'uso</h2>
          <table className="census-table">
            <thead>
              <tr>
                <th scope="col">Uso</th>
                <th scope="col">Edifici</th>
                <th scope="col">m² lordi</th>
                <th scope="col">Attività</th>
                <th scope="col">Lavoro</th>
              </tr>
            </thead>
            <tbody>
              {USE_ORDER.filter((u) => summary.per_destinazione_uso[u]).map((u) => {
                const row = summary.per_destinazione_uso[u]!;
                return (
                  <tr
                    key={u}
                    className={use === u ? 'is-active' : undefined}
                    title="Mostra solo questi edifici nell'elenco"
                    onClick={() => setUse(use === u ? '' : u)}
                  >
                    <th scope="row">
                      <i style={{ background: useColor(u, categoryById) }} aria-hidden="true" />
                      {USE_LABEL[u]}
                    </th>
                    <td>{n(row.edifici)}</td>
                    <td>{n(row.superficie_lorda_m2)}</td>
                    <td>{n(row.attivita)}</td>
                    <td>{n(row.posti_di_lavoro)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          <h2>
            Edifici <span className="caption">{n(buildings.length)} mostrati</span>
          </h2>
          <div className="census-filters">
            <input
              type="search"
              className="search"
              placeholder="Codice, nome, lotto"
              aria-label="Cerca nel censimento"
              autoComplete="off"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <select className="census-select" aria-label="Destinazione d'uso" value={use} onChange={(event) => setUse(event.target.value as CensusUse | '')}>
              <option value="">Tutti gli usi</option>
              {USE_ORDER.map((u) => (
                <option key={u} value={u}>
                  {USE_LABEL[u]}
                </option>
              ))}
            </select>
          </div>
          <ul className="census-list" ref={listRef}>
            {buildings.length === 0 && <li className="empty">Nessun edificio trovato</li>}
            {buildings.map((b, i) => [
              (i === 0 || buildings[i - 1].lotto !== b.lotto || zoneOf(buildings[i - 1]) !== zoneOf(b)) && (
                <LotHeader key={`lotto-${zoneOf(b)}-${b.lotto}`} census={census} zona={zoneOf(b)} lotto={b.lotto} onHoverArea={onHoverArea} />
              ),
              <BuildingRow
                key={b.codice}
                building={b}
                categoryById={categoryById}
                color={useColor(b.destinazione_uso, categoryById)}
                expanded={expanded === b.codice}
                onToggle={() => setExpanded(expanded === b.codice ? null : b.codice)}
                onHoverArea={onHoverArea}
                onHoverPlace={onHoverPlace}
                onSelectPlace={onSelectPlace}
              />,
            ])}
          </ul>

          {spaces.length > 0 && (
            <>
              <h2>
                Spazi aperti e strutture <span className="caption">{spaces.length}</span>
              </h2>
              <ul className="census-spaces">
                {spaces.map((s) => (
                  <li key={s.codice}>
                    <button
                      type="button"
                      className="place-button"
                      onMouseEnter={() => onHoverPlace(s.luogo)}
                      onMouseLeave={() => onHoverPlace(null)}
                      onClick={() => onSelectPlace(s.luogo)}
                    >
                      <span className="census-code">{s.codice}</span>
                      {s.nome} · lotto {s.lotto} · {n(s.superficie_m2)} m²
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}

          <button type="button" className="section-toggle census-assumptions" aria-expanded={showAssumptions} onClick={() => setShowAssumptions(!showAssumptions)}>
            <span className="chevron" aria-hidden="true" />
            Come sono stimati i numeri
          </button>
          {showAssumptions && (
            <ul className="hint census-hint">
              <li>
                Ogni edificio è censito come parte del suo lotto, con tutti i suoi piani ({decimal(p.altezza_piano_m)} m l'uno), ognuno
                con una sola destinazione d'uso (tools/centro.py, tools/cerchia.py).
              </li>
              <li>
                Case: un alloggio ogni {p.casa.m2_per_alloggio} m² lordi, {percent(p.casa.alloggi_sfitti)} vuoti,{' '}
                {decimal(p.casa.abitanti_per_alloggio)} abitanti per alloggio occupato; residenze per studenti, un posto letto ogni{' '}
                {p.m2_per_studente} m².
              </li>
              <li>
                Lavoro, m² lordi per addetto: uffici {p.m2_per_addetto.uffici}, sportelli pubblici {p.m2_per_addetto.sportelli},
                negozi {p.m2_per_addetto.negozi}, laboratori {p.m2_per_addetto.laboratorio}, scuole {p.m2_per_addetto.scuola},
                sanità {p.m2_per_addetto.sanita}, musei e teatri {p.m2_per_addetto.cultura}; alberghi una camera ogni{' '}
                {p.m2_per_camera} m².
              </li>
              <li>
                Imprese: quelle con il nome occupano i piani in ordine, ognuna grande quanto il suo tipo (un bar 2-5 addetti, uno
                studio 6-22, una società 35-110); gli uffici in affitto del Centro sono divisi in "Azienda 1, 2...". Lo spazio
                che avanza resta libero: posti liberi su un piano, o un piano intero libero.
              </li>
            </ul>
          )}
        </>
  );

  // dentro l'accordion "Edifici" (BuildingsPanel) il corpo sta senza sezione e senza intestazione propria
  if (embedded) return body || null;
  return (
    <section className="panel-section census">
      <button type="button" className="section-toggle" aria-expanded={open} onClick={() => onOpenChange(!open)}>
        <span className="chevron" aria-hidden="true" />
        Censimento
        <span className="section-count">{n(census.edifici.length)} edifici</span>
      </button>
      {open && body && <div className="section-body census-body">{body}</div>}
    </section>
  );
}
