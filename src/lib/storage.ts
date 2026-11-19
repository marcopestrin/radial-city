/**
 * Piccoli aiuti per localStorage. Il browser può rifiutare la memoria locale (finestre private,
 * cookie bloccati): in quel caso l'app parte semplicemente con le impostazioni predefinite.
 */

export function readStored<T extends object>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw === null ? fallback : { ...fallback, ...JSON.parse(raw) };
  } catch {
    return fallback;
  }
}

export function writeStored<T>(key: string, value: T): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // memoria locale non disponibile: non c'è niente da fare
  }
}
