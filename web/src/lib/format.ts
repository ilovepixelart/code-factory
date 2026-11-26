// How the board writes values; tests hold them to the display goldens
// (tests/golden/formats/display).

/** A label's dot colours: the theme's eight categorical chart colours, in their order. */
export const LABEL_COLORS = [
  'bg-chart-1',
  'bg-chart-2',
  'bg-chart-3',
  'bg-chart-4',
  'bg-chart-5',
  'bg-chart-6',
  'bg-chart-7',
  'bg-chart-8',
] as const

const CRC_TABLE = Array.from({ length: 256 }, (_, n) => {
  let c = n
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
  return c >>> 0
})

/** zlib.crc32 of the text's UTF-8 bytes. */
function crc32(text: string): number {
  let crc = 0xffffffff
  for (const byte of new TextEncoder().encode(text)) {
    crc = (CRC_TABLE[(crc ^ byte) & 0xff] ?? 0) ^ (crc >>> 8)
  }
  return (crc ^ 0xffffffff) >>> 0
}

/** The dot colour of a label: the same name always gets the same colour. */
export function labelColor(name: string): string {
  return LABEL_COLORS[crc32(name.trim().toLowerCase()) % LABEL_COLORS.length] ?? LABEL_COLORS[0]
}

/** `places` decimals of the float's exact value, rounded half to even. `toFixed` alone rounds some values the other way (2.675 is 2.67499... exactly). */
function fixed(value: number, places: number): string {
  const exact = value.toFixed(20)
  const [whole = '0', fraction = ''] = exact.split('.')
  const kept = fraction.slice(0, places)
  const rest = fraction.slice(places)
  const half = rest.replace(/0+$/, '') === '5'
  const above = rest > '5' && !half
  const last = Number(kept.at(-1) ?? whole.at(-1) ?? '0')
  const up = above || (half && last % 2 === 1)
  const units = BigInt(whole + kept) + (up ? 1n : 0n)
  if (places === 0) return units.toString()
  const text = units.toString().padStart(places + 1, '0')
  return `${text.slice(0, -places)}.${text.slice(-places)}`
}

const cents = (value: number): string => fixed(value, 2)

/** A cost in dollars: `$1,234.50`. */
/** A fixed word (a type, a priority, a kind, a status) as it reads on screen: in sentence case, so a
 *  word reads the same on a card, in a list, a select and a menu; what is sent stays as it is. */
export function sentence(word: string): string {
  return word.charAt(0).toUpperCase() + word.slice(1)
}

export function money(value: number): string {
  const [whole = '0', fraction = '00'] = cents(Math.abs(value)).split('.')
  return `${value < 0 ? '-' : ''}$${thousands(whole)}.${fraction}`
}

/** A whole number with its thousands separated: `18,240`. */
export function thousands(value: number | string): string {
  return String(value).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
}

/**
 * Why a run stopped, said once (CF-1076): a reason that begins with "stopped" is capitalised, any
 * other follows `Stopped: `; a whole number of four digits or more is grouped (`3,000,233`), so
 * reasons recorded before the board grouped them read the same.
 */
export function haltWords(reason: string): string {
  const grouped = reason.replace(/\b\d{4,}\b/g, (n) => thousands(n))
  return /^stopped\b/i.test(grouped)
    ? grouped.charAt(0).toUpperCase() + grouped.slice(1)
    : `Stopped: ${grouped}`
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** A due date as `3 Oct`, with the year when it is not today's; the raw text when unreadable. */
export function day(date: string | null, raw: string, today: string): string {
  if (!date) return raw
  const [year, month, dayOfMonth] = date.split('-').map(Number)
  const text = `${String(dayOfMonth)} ${String(MONTHS[(month ?? 1) - 1])}`
  return String(year) === today.slice(0, 4) ? text : `${text} ${String(year)}`
}

/** The first eight characters of an identifier. */
export function short(identifier: string): string {
  return Array.from(identifier).slice(0, 8).join('')
}

/** Rounded to a whole number, a half going to the even neighbour. */
function roundHalfEven(value: number): number {
  const floor = Math.floor(value)
  const fraction = value - floor
  if (fraction !== 0.5) return Math.round(value)
  return floor % 2 === 0 ? floor : floor + 1
}

/**
 * When a ticket held by a usage limit starts again: `resumes in 2.1h`, `resuming` once due, or
 * `resume refused: <reason>` while the board's last try was refused.
 */
export function resumes(until: number, now: number, refused = ''): string {
  if (refused !== '') return `resume refused: ${refused}`
  return until > now ? `resumes in ${span(until - now)}` : 'resuming'
}

/** A token count: `999`, `1.2k`, `150k`, `81.1M`. */
export function count(value: number): string {
  if (value < 1000) return String(value)
  if (value < 1_000_000) return `${fixed(value / 1000, 1).replace(/\.0$/, '')}k`
  return `${fixed(value / 1_000_000, 1).replace(/\.0$/, '')}M`
}

/** A duration: `350ms`, `1.8s`, `1m 35s`, or empty when unknown. */
export function dur(seconds: number | null): string {
  if (seconds === null) return ''
  if (seconds < 1) return `${String(roundHalfEven(seconds * 1000))}ms`
  if (seconds < 60) return `${fixed(seconds, 1)}s`
  const whole = Math.trunc(seconds)
  return `${String(Math.floor(whole / 60))}m ${String(whole % 60)}s`
}

/** Every age and span of time, one way on every page (CF-490): `12s`, `30m`, `1.5h`, `2d`. */
export function span(seconds: number): string {
  const whole = Math.max(0, roundHalfEven(seconds))
  if (whole < 60) return `${String(whole)}s`
  if (seconds >= 86_400) return `${fixed(seconds / 86_400, 1).replace(/\.0$/, '')}d`
  if (seconds >= 3600) return `${fixed(seconds / 3600, 1).replace(/\.0$/, '')}h`
  return `${String(roundHalfEven(seconds / 60))}m`
}

/** The text, cut to `limit` characters with an ellipsis when longer. */
export function trim(text: string, limit = 140): string {
  const characters = Array.from(text)
  if (characters.length <= limit) return text
  return `${characters.slice(0, limit - 1).join('')}…`
}

/** The wall-clock time of an epoch time, in this browser's zone: `14:30:05`. */
export function clock(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleTimeString('en-GB', { hour12: false })
}

/** The hours and minutes of an epoch time, in this browser's zone: `14:30`. */
export function hourMinute(timestamp: number): string {
  return clock(timestamp).slice(0, 5)
}

/** A local day as `YYYY-MM-DD`, as `day` reads it. */
export function localDay(seconds: number): string {
  const at = new Date(seconds * 1000)
  const two = (n: number) => String(n).padStart(2, '0')
  return `${String(at.getFullYear())}-${two(at.getMonth() + 1)}-${two(at.getDate())}`
}

/** A moment as its local day and minute: `6 Nov 09:12`, with the year when it is not `now`'s. */
export function dayClock(seconds: number, now: number): string {
  const then = localDay(seconds)
  return `${day(then, then, localDay(now))} ${hourMinute(seconds)}`
}

/** The tooltip of an amount that holds an estimate (CF-1216). */
export const ESTIMATE_NOTE =
  "includes cost estimated from the runs' tokens at their agents' prices, 0 for a model served on this machine"

/** A spend's tooltip: what it is, and that it holds an estimate when it does (CF-1216). */
export function spendTitle(what: string, estimated = false): string {
  return estimated ? `${what}; ${ESTIMATE_NOTE}` : what
}

/** A cost in dollars, led by `~` when a part of it is the board's estimate (CF-1216). */
export function cost(value: number, estimated = false): string {
  return estimated ? `~${money(value)}` : money(value)
}

/** How close a ticket's agent spend is to its budget: over it, within the last fifth, or neither. */
export function spendLevel(spent: number, budget: number | null): 'over' | 'watch' | 'normal' {
  if (budget === null) return 'normal'
  return spent >= budget ? 'over' : spent >= budget * 0.8 ? 'watch' : 'normal'
}
