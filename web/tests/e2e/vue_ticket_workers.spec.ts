// CF-1184 acceptance flows: a session subagent whose tool call names a ticket's worktree shows on
// that ticket's card, its ticket page and the Team page, and leaves the card once it stops. Served
// by the server over the writes sample without the run follower; the subagent's hook events
// are captured as the hooks capture them.

import { execFileSync } from 'node:child_process'
import type { Locator, Page } from '@playwright/test'
import { BINARY, Served, TIMEOUT, card, expect, serve, test as base } from './fixtures'

const test = base.extend<{ served: Served }>({
  served: async ({}, use) => {
    const { served, stop } = await serve('writes', 'false', false)
    await use(served)
    stop()
  },
})

const SESSION = 's-coordinator'
const AGENT = 'a1b2c3d4'

/** Capture one hook event of the coordinator session, working in the sample's checkout. */
function capture(served: Served, event: object): void {
  execFileSync(BINARY, ['capture'], {
    input: JSON.stringify({ session_id: SESSION, cwd: served.root, ...event }),
    env: { ...process.env, CODE_FACTORY_HOME: served.home },
  })
}

/** A `ticket-worker` subagent running the tests in CF-3's worktree, its call still open. */
function subagentInWc3(served: Served): void {
  capture(served, { hook_event_name: 'SessionStart' })
  capture(served, {
    hook_event_name: 'SubagentStart',
    agent_id: AGENT,
    agent_type: 'ticket-worker',
  })
  capture(served, {
    hook_event_name: 'PreToolUse',
    agent_id: AGENT,
    agent_type: 'ticket-worker',
    tool_name: 'Bash',
    tool_use_id: 't-1',
    tool_input: { command: `cd ${served.root}/.code-factory/worktrees/CF-3 && cargo test` },
  })
}

function badge(scope: Page | Locator) {
  return scope.getByRole('link', { name: /ticket-worker a1b2/ })
}

// CF-1184-A1, CF-1184-A2: the card, the ticket page and the Team page name the subagent.
test('e2e_a_subagent_shows_on_its_card_its_ticket_and_the_team_page', async ({ served, page }) => {
  subagentInWc3(served)

  await page.goto(`${served.url}/tickets`)
  const wc3 = card(page, 'CF-3')
  await expect(badge(wc3)).toHaveText(/^Working ticket-worker a1b2 · Bash cd .* · \d+s$/, {
    timeout: TIMEOUT,
  })
  await expect(badge(wc3)).toHaveAttribute('href', `/sessions/${SESSION}`)
  await expect(badge(page)).toHaveCount(1)

  await page.goto(`${served.url}/tickets/sample/CF-3`)
  const agents = page.getByRole('list', { name: 'Session subagents at work' })
  await expect(badge(agents)).toContainText('Working ticket-worker a1b2', { timeout: TIMEOUT })

  await page.goto(`${served.url}/team`)
  const working = page.getByRole('region', { name: /^Working/ }).getByRole('listitem')
  await expect(working.filter({ hasText: 'ticket-worker a1b2' })).toContainText('CF-3', {
    timeout: TIMEOUT,
  })
})

// CF-1184-A3: once the subagent stops, its card shows no badge.
test('e2e_a_stopped_subagent_leaves_its_card', async ({ served, page }) => {
  subagentInWc3(served)
  capture(served, { hook_event_name: 'SubagentStop', agent_id: AGENT, agent_type: 'ticket-worker' })

  await page.goto(`${served.url}/tickets`)
  await card(page, 'CF-3').waitFor({ timeout: TIMEOUT })

  await expect(badge(page)).toHaveCount(0)
})
