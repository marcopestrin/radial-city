/** Funzioni di formattazione di numeri e testi (in italiano). */

const numberFormat = new Intl.NumberFormat('it-IT');

/** 81726 -> "81.726" */
export function formatNumber(value: number): string {
  return numberFormat.format(value);
}

/** Sceglie singolare o plurale: plural(1, 'lotto', 'lotti') -> "lotto". */
export function plural(count: number, singular: string, pluralForm: string): string {
  return count === 1 ? singular : pluralForm;
}

/** "12 abitanti", "1 abitante" */
export function countWithWord(count: number, singular: string, pluralForm: string): string {
  return `${formatNumber(count)} ${plural(count, singular, pluralForm)}`;
}

/** Posizione di un luogo nel tooltip: "Lotto 457 · Le Grazie", oppure solo il quartiere. */
export function placeLocation(lot: number | null, quarter: string): string {
  return lot ? `Lotto ${lot} · ${quarter}` : quarter;
}

/** Una distanza per la barra della scala: 1000 -> "1 km", 200 -> "200 m". */
export function formatDistance(metres: number): string {
  return metres >= 1000 ? `${metres / 1000} km` : `${metres} m`;
}
