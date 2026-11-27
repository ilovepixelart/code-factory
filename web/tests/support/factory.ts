// The factory answers as the specification writes them (section 4.6, from the worked fixture F1):
// what the Factory pages' tests mount with. Each call returns a fresh copy a test may change.

import type { Dashboard, Expensive, Improvements, ScorerCards } from '@/lib/factory'

const PULLS = 'https://github.com/sample/sample/pull'

const EXPENSIVE: Expensive[] = [
  {
    url: `${PULLS}/14`,
    repository: 'sample',
    number: 14,
    ticket: 'CF-4',
    title: 'Cache the index',
    state: 'open',
    opened_at: 1793952000,
    cost: 10.0,
    cost_complete: true,
    estimated: false,
    changed_lines: 1000,
    size: 'XL',
    runs: 2,
  },
  {
    url: `${PULLS}/12`,
    repository: 'sample',
    number: 12,
    ticket: 'CF-2',
    title: 'Split the loader',
    state: 'merged',
    opened_at: 1793700000,
    cost: 5.0,
    cost_complete: true,
    estimated: false,
    changed_lines: 100,
    size: 'M',
    runs: 3,
  },
  {
    url: `${PULLS}/13`,
    repository: 'sample',
    number: 13,
    ticket: 'CF-3',
    title: 'Retry the fetch',
    state: 'merged',
    opened_at: 1793880000,
    cost: 2.0,
    cost_complete: true,
    estimated: false,
    changed_lines: 499,
    size: 'M',
    runs: 1,
  },
  // The two ties at 1.50 of the fixture, newest opened first: #17 (Nov 7 11:00), #16 (Nov 7 10:00).
  {
    url: `${PULLS}/17`,
    repository: 'sample',
    number: 17,
    ticket: 'CF-6',
    title: 'Trim the log',
    state: 'merged',
    opened_at: 1794049200,
    cost: 1.5,
    cost_complete: true,
    estimated: false,
    changed_lines: 99,
    size: 'S',
    runs: 2,
  },
  {
    url: `${PULLS}/16`,
    repository: 'sample',
    number: 16,
    ticket: 'CF-6',
    title: 'Warm the cache',
    state: 'open',
    opened_at: 1794045600,
    cost: 1.5,
    cost_complete: true,
    estimated: false,
    changed_lines: 999,
    size: 'L',
    runs: 2,
  },
]

const SCORERS: ScorerCards = {
  available: true,
  cards: [
    {
      repository: 'sample',
      name: 'ran-tests',
      question: 'Did the agent run the tests before finishing?',
      yes: 3,
      no: 1,
      unclear: 1,
      asked: 5,
      pass_rate: 0.75,
      average_score: null,
      window: { from: 1793664000, to: 1794268800 },
    },
  ],
}

const IMPROVEMENTS: Improvements = {
  available: true,
  items: [
    {
      url: `${PULLS}/21`,
      number: 21,
      title: 'Self-improvement: 25 failures',
      state: 'open',
      opened_at: 1794000000,
      failures: 25,
    },
  ],
}

/** `GET /api/factory/dashboard?from=2026-11-01&to=2026-11-08` with fixture F1. */
export function dashboard(): Dashboard {
  return structuredClone({
    from: 1793491200,
    to: 1794096000,
    now: 1794268800,
    runs: {
      total: 13,
      by_stage: [
        { key: 'build', runs: 6 },
        { key: 'review', runs: 4 },
        { key: 'eval', runs: 1 },
        { key: 'judge', runs: 1 },
        { key: 'spec', runs: 1 },
      ],
      by_state: [
        { key: 'finished', runs: 9 },
        { key: 'failed', runs: 2 },
        { key: 'running', runs: 1 },
        { key: 'stopped', runs: 1 },
      ],
      by_source: [
        { key: 'board', runs: 11 },
        { key: 'eval', runs: 1 },
        { key: 'judge', runs: 1 },
      ],
      by_model: [
        { key: 'opus', runs: 8 },
        { key: 'sonnet', runs: 5 },
      ],
      by_agent: [
        { key: 'builder', runs: 8 },
        { key: 'reviewer', runs: 4 },
        { key: 'judge', runs: 1 },
      ],
    },
    prs: { opened: 7, merged: 4, merged_in_period: 3, open: 2, closed: 1 },
    series: {
      bucket: 'day',
      points: [
        { start: 1793491200, opened: 0, merged: 0 },
        { start: 1793577600, opened: 1, merged: 1 },
        { start: 1793664000, opened: 1, merged: 1 },
        { start: 1793750400, opened: 0, merged: 0 },
        { start: 1793836800, opened: 1, merged: 1 },
        { start: 1793923200, opened: 2, merged: 0 },
        { start: 1794009600, opened: 2, merged: 1 },
      ],
    },
    autonomy: { share: 0.6666666666666666, autonomous: 2, assisted: 1, unknown: 1 },
    cycle: {
      total: { median: 79200.0, count: 4 },
      stages: [
        { stage: 'kickoff_to_pr', median: 9000.0, count: 4 },
        { stage: 'pr_to_review', median: 21600.0, count: 3 },
        { stage: 'review_to_merge', median: 64800.0, count: 3 },
      ],
    },
    cost: {
      median: 1.75,
      priced: 6,
      of: 7,
      estimated: false,
      measurement: 0.5,
      by_component: [
        { component: 'spec', median: 0.0, total: 0.5 },
        { component: 'build', median: 1.5, total: 16.0 },
        { component: 'review', median: 0.5, total: 5.0 },
        { component: 'other', median: 0.0, total: 0.0 },
      ],
      by_size: [
        { size: 'S', median: 1.5, priced: 2, of: 2 },
        { size: 'M', median: 3.5, priced: 2, of: 2 },
        { size: 'L', median: 1.5, priced: 1, of: 2 },
        { size: 'XL', median: 10.0, priced: 1, of: 1 },
      ],
    },
    expensive: EXPENSIVE,
    scorers: SCORERS,
    improvements: { available: false, items: [] },
  })
}

/** The dashboard of a range with no data (R3): every count 0, every median and share null. */
export function emptyDashboard(): Dashboard {
  const base = dashboard()
  const none = { median: null, count: 0 }
  return {
    ...base,
    runs: { total: 0, by_stage: [], by_state: [], by_source: [], by_model: [], by_agent: [] },
    prs: { opened: 0, merged: 0, merged_in_period: 0, open: 0, closed: 0 },
    series: {
      bucket: 'day',
      points: base.series.points.map((p) => ({ start: p.start, opened: 0, merged: 0 })),
    },
    autonomy: { share: null, autonomous: 0, assisted: 0, unknown: 0 },
    cycle: {
      total: none,
      stages: [
        { stage: 'kickoff_to_pr', ...none },
        { stage: 'pr_to_review', ...none },
        { stage: 'review_to_merge', ...none },
      ],
    },
    cost: {
      median: null,
      priced: 0,
      of: 0,
      estimated: false,
      measurement: null,
      by_component: [
        { component: 'spec', median: null, total: 0 },
        { component: 'build', median: null, total: 0 },
        { component: 'review', median: null, total: 0 },
        { component: 'other', median: null, total: 0 },
      ],
      by_size: [
        { size: 'S', median: null, priced: 0, of: 0 },
        { size: 'M', median: null, priced: 0, of: 0 },
        { size: 'L', median: null, priced: 0, of: 0 },
        { size: 'XL', median: null, priced: 0, of: 0 },
      ],
    },
    expensive: [],
    scorers: { available: true, cards: [] },
    improvements: { available: true, items: [] },
  }
}

/** `GET /api/factory/scorers?from=2026-11-01&to=2026-11-08`. */
export const scorers = (): ScorerCards => structuredClone(SCORERS)

/** `GET /api/factory/improvements?limit=3` with one provider item. */
export const improvements = (): Improvements => structuredClone(IMPROVEMENTS)
