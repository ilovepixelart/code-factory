// What the Team tests mount with: a row, a peek and a read of `GET /api/team/now` built by hand.
// The instants are in UTC, so a test sets `process.env.TZ = 'UTC'` to read them as written.

import type { Peek, TeamNow, TeamRow } from '@/lib/teamNow'

/** 2026-11-10 12:00:00 UTC. */
export const NOW = 1_794_312_000

export function teamRow(over: Partial<TeamRow> = {}): TeamRow {
  return {
    key: 'row-1',
    state: 'working',
    ticket: { repository: 'sample', id: 'CF-1', title: 'Build the thing' },
    actor: { kind: 'agent', name: 'builder' },
    line: 'build run',
    since: NOW - 540,
    until: null,
    also: [],
    pull: null,
    ...over,
  }
}

/** Filed 10:00, first commit 10:20, no pull request yet. */
export function teamPeek(): Peek {
  return {
    type: 'feature',
    column: 'Build',
    milestones: [
      { stage: 'filed', at: NOW - 7200, cycle: null },
      { stage: 'first_commit', at: NOW - 6000, cycle: 1800 },
      { stage: 'pull_request', at: null, cycle: 3600 },
    ],
    events: [{ at: NOW - 300, words: 'build run started' }],
  }
}

export function teamNow(rows: Partial<Record<keyof TeamNow['groups'], TeamRow[]>> = {}): TeamNow {
  const groups = { needs_you: [], waiting: [], working: [], done_today: [], stale: [], ...rows }
  return {
    now: NOW,
    today: NOW - 43_200,
    cycle: { since: NOW - 7 * 86_400, from: 'the last 7 days' },
    counts: {
      needs_you: groups.needs_you.length,
      waiting: groups.waiting.length,
      working: groups.working.length,
      done_today: groups.done_today.length,
      stale: groups.stale.length,
    },
    groups,
    idle: [],
    paused: [],
    stages: [],
    peek: {},
  }
}
