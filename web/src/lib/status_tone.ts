import type { BadgeVariants } from '@/components/ui/badge'
import { sentence } from './format'

// The one map from a status word to the tone of its badge (CF-1276): a session's state, a run's
// outcome, a pull request's state. `TONE_VARIANTS` draws each tone with a Badge variant; the
// coloured ones are tinted like shadcn-vue's destructive badge, in the theme's status colours
// (`--success`, `--info`, `--warning` in app.css).

export type BadgeTone = 'quiet' | 'info' | 'success' | 'warning' | 'error'
export type BadgeVariant = NonNullable<BadgeVariants['variant']>

/** The Badge variant of each tone. */
export const TONE_VARIANTS: Record<BadgeTone, BadgeVariant> = {
  success: 'success',
  info: 'info',
  warning: 'warning',
  error: 'destructive',
  quiet: 'outline',
}

const STATUS_TONES: Record<string, BadgeTone> = {
  finished: 'success',
  done: 'success',
  approved: 'success',
  merged: 'success',
  working: 'info',
  running: 'info',
  open: 'info',
  'checks running': 'info',
  // A blocked session waits on the owner, as `owner` does: it reads "Waiting on you".
  blocked: 'warning',
  owner: 'warning',
  waiting: 'warning',
  stale: 'warning',
  uncommitted: 'warning',
  conflict: 'warning',
  failed: 'error',
  denied: 'error',
  'checks failing': 'error',
  // A card's delivery status (`deliveryStatus` in delivery.ts), by its shown words.
  'ship failed': 'error',
  'merge failed': 'error',
  'checks failed': 'error',
  'waiting for an answer': 'warning',
  'merge conflict': 'warning',
  'waiting for checks': 'info',
  'shipping branch': 'info',
  'opening pull request': 'info',
  idle: 'quiet',
  stopped: 'quiet',
  closed: 'quiet',
  ended: 'quiet',
  draft: 'quiet',
  interrupted: 'quiet',
}

/** The tone of a status word; a word the map does not know takes the quiet badge. */
export function statusTone(word: string): BadgeTone {
  return STATUS_TONES[word] ?? 'quiet'
}

/** The Badge variant of a status word. */
export function statusVariant(word: string): BadgeVariant {
  return TONE_VARIANTS[statusTone(word)]
}

// What a status says, beside its tone: a state the map names reads its own words; any other reads
// in sentence case, so a status never shows in two casings.
const STATUS_WORDS: Record<string, string> = {
  blocked: 'Waiting on you',
  owner: 'Waiting on you',
}

/** The words of a status word as a badge shows them. */
export function statusWord(word: string): string {
  return STATUS_WORDS[word] ?? sentence(word)
}
