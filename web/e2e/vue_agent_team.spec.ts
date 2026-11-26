// CF-360 acceptance flow: a card names the defined agent working it, served by the server
// over the writes sample state with a sleeping stand-in for the agent.

import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import type { Locator, Page } from '@playwright/test'
import { Served, TIMEOUT, boardLoaded, card, expect, serve, test as base } from './fixtures'

/** The board with agent `writer` working Spec; every run is stopped before the server. */
const test = base.extend<{ team: { served: Served; page: Page } }>({
  team: async ({ browser }, use) => {
    const { served, stop } = await serve('writes', 'sleep 60')
    writeFileSync(
      join(served.home, 'agents.json'),
      JSON.stringify([{ name: 'writer', runtime: 'claude', roles: ['spec'] }]),
    )
    const context = await browser.newContext()
    const page = await context.newPage()
    await use({ served, page })
    await page.request.post(`${served.url}/api/agents/stop`)
    await context.close()
    stop()
  },
})

function agent(page: Page): Locator {
  return page.getByRole('region', { name: /^Agent/ })
}

function claimants(served: Served): string[] {
  const path = join(served.home, 'leases.json')
  if (!existsSync(path)) return []
  const leases = JSON.parse(readFileSync(path, 'utf8')) as Record<string, { agent: string }>
  return Object.values(leases).map((lease) => lease.agent)
}

test('e2e_a_card_shows_the_agent_working_it', async ({ team: { served, page } }) => {
  await page.goto(`${served.url}/tickets/sample/CF-2`)
  await agent(page).getByRole('button', { name: 'Start agent' }).click()
  await agent(page).getByText('Iteration 1 on Spec').waitFor({ timeout: TIMEOUT })
  await page.goto(`${served.url}/tickets`)
  await boardLoaded(page)

  await expect(card(page, 'CF-2').getByText('writer working', { exact: true })).toBeVisible()
  expect(claimants(served)).toStrictEqual(['writer'])
})
