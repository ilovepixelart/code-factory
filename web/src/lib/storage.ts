// Per-browser choices, as the board keeps them; storage can be unavailable, and the choice
// then holds for this page only.

export function load<T>(key: string, fallback: T): T {
  try {
    const text = localStorage.getItem(key)
    return text === null ? fallback : (JSON.parse(text) as T)
  } catch {
    return fallback
  }
}

export function save(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // Unavailable storage: the choice applies to this page.
  }
}

export function loadText(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

export function saveText(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    // Unavailable storage: the choice applies to this page.
  }
}
