// The Scorers table's rows (CF-1303, `GET /api/scorers`): each scorer's answers over 7 and 30 days.
export interface ScorerWindow {
  yes: number
  no: number
  unclear: number
  pass_rate: number | null
}

export interface Scorer {
  repository: string
  name: string
  question: string
  stage: string
  sample: number
  threshold: number
  week: ScorerWindow
  month: ScorerWindow
  ticket: string
}

/** Every answer in the window, yes, no or unclear. */
export function asked(window: ScorerWindow): number {
  return window.yes + window.no + window.unclear
}

/** A pass rate as a whole percent, or a dash while no yes or no answer was given. */
export function rate(window: ScorerWindow): string {
  return window.pass_rate === null ? '-' : `${String(Math.round(window.pass_rate * 100))}%`
}
