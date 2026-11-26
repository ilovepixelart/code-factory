// CF-552: the board's performance, rerun on demand with `pnpm --dir web perf`. The server serves
// the `perf` sample: merged tickets, as most of a working repository's are, and open ones spread
// over the columns. Each read, page and run start is timed and its median compared with
// web/perf/budgets.json.

import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { expect, serve, test } from '../tests/e2e/fixtures'
import budgets from './budgets.json' with { type: 'json' }

const TIMES = 5
const REPORT = join(import.meta.dirname, '..', 'test-results', 'perf.json')
/** The Inbox answers every reader from one gather for 4 seconds (server/src/inbox.rs,
 * `FRESH_FOR`); its pages poll every 5, so a board gathers it again for each poll. */
const INBOX_FRESH_MS = 4_100

interface Board {
  url: string
  stop: () => void
}

/** The `perf` sample, served: the sample loader generates the merged and open tickets. */
async function generated(): Promise<Board> {
  const { served, stop } = await serve('perf')
  return { url: served.url, stop }
}

const median = (times: number[]): number =>
  [...times].sort((a, b) => a - b)[Math.floor(times.length / 2)] ?? 0

/** Print each median beside its budget, keep them in the report, and return those over. */
function judged(kind: string, measured: Record<string, number>, budget: Record<string, number>) {
  const over: string[] = []
  for (const [name, ms] of Object.entries(measured)) {
    const limit = budget[name] ?? 0
    const verdict = ms > limit ? 'OVER' : 'ok'
    console.log(
      `${kind.padEnd(6)} ${name.padEnd(28)} ${ms.toFixed(0).padStart(7)} ms  budget ${String(limit).padStart(6)}  ${verdict}`,
    )
    if (ms > limit) over.push(`${name}: ${ms.toFixed(0)} ms, budget ${String(limit)} ms`)
  }
  mkdirSync(join(REPORT, '..'), { recursive: true })
  const report = existsSync(REPORT) ? (JSON.parse(readFileSync(REPORT, 'utf8')) as object) : {}
  writeFileSync(REPORT, `${JSON.stringify({ ...report, [kind]: measured }, null, 2)}\n`)
  return over
}

test("the board's reads answer within their budgets", async ({ request }) => {
  const board = await generated()
  try {
    const measured: Record<string, number> = {}
    for (const path of Object.keys(budgets.reads)) {
      const inbox = path.startsWith('/api/inbox')
      await request.get(board.url + path)
      const times: number[] = []
      for (let i = 0; i < TIMES; i++) {
        if (inbox) await new Promise((done) => setTimeout(done, INBOX_FRESH_MS))
        const began = performance.now()
        const answer = await request.get(board.url + path)
        times.push(performance.now() - began)
        expect(answer.status(), path).toBe(200)
      }
      measured[path] = median(times)
    }
    expect(judged('reads', measured, budgets.reads)).toEqual([])
  } finally {
    board.stop()
  }
})

/** What each page shows once its answer is in, never its loading state. */
const CONTENT: Record<string, string> = {
  '/tickets': '[data-ticket]',
  '/inbox': '#inbox-region',
  '/agents': 'section[aria-labelledby="agents-heading"]',
  '/flow': 'section[aria-label="At a glance"]',
  '/archive': '#archive-table',
  '/memory': 'section[aria-labelledby="memory-history"]',
  '/': 'section[aria-labelledby="sessions-heading"]',
}

test('the pages show their content within their budgets', async ({ browser }) => {
  const board = await generated()
  try {
    const measured: Record<string, number> = {}
    for (const path of Object.keys(budgets.pages)) {
      const times: number[] = []
      for (let i = 0; i <= TIMES; i++) {
        if (path === '/inbox') await new Promise((done) => setTimeout(done, INBOX_FRESH_MS))
        const context = await browser.newContext()
        const page = await context.newPage()
        const began = performance.now()
        await page.goto(board.url + path)
        await page
          .locator(CONTENT[path] ?? 'main')
          .first()
          .waitFor({ timeout: 60_000 })
        if (i > 0) times.push(performance.now() - began)
        await context.close()
      }
      measured[path] = median(times)
    }
    expect(judged('pages', measured, budgets.pages)).toEqual([])
  } finally {
    board.stop()
  }
})

test('a run starts within its budget', async ({ request }) => {
  const board = await generated()
  try {
    const began = performance.now()
    const answer = await request.post(`${board.url}/api/tickets/sample/PF-1/runs`, {
      data: {},
      headers: { Origin: board.url },
    })
    const took = performance.now() - began
    expect(answer.status(), await answer.text()).toBe(201)
    expect(judged('runs', { start: took }, { start: budgets.run_start })).toEqual([])
  } finally {
    board.stop()
  }
})
