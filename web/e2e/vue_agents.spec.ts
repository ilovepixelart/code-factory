// CF-210 acceptance flows: starting, stopping and halting agents from the Vue board, served by
// the server over the writes sample state with a sleeping stand-in for the agent.

import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import type { Locator, Page } from '@playwright/test'
import { TIMEOUT, expect, serve, test as base, toasts, Served } from './fixtures'

/** CF-2's ticket page, served with an agent that sleeps until it is stopped. */
const test = base.extend<{ agentPage: { served: Served; page: Page } }>({
  agentPage: async ({ browser }, use) => {
    const { served, stop } = await serve('writes', 'sleep 60')
    const context = await browser.newContext()
    const page = await context.newPage()
    await page.goto(`${served.url}/tickets/sample/CF-2`)
    await agent(page).waitFor({ timeout: TIMEOUT })
    await use({ served, page })
    await context.close()
    stop()
  },
})

function agent(page: Page): Locator {
  return page.getByRole('region', { name: /^Agent/ })
}

function runs(served: Served): string {
  return readFileSync(join(served.home, 'runs.json'), 'utf8')
}

test('e2e_an_agent_starts_and_stops_from_the_page', async ({ agentPage: { served, page } }) => {
  const section = agent(page)
  await section.getByRole('switch', { name: 'Loop until done' }).check()
  await section.getByRole('button', { name: 'Start agent' }).click()
  const running = section.getByText('Iteration 1 on Spec')
  await running.waitFor({ timeout: TIMEOUT })
  const looping = (await running.innerText()).includes('looping')
  const started = runs(served)
  await section.getByRole('button', { name: 'Stop agent' }).click()
  await section.getByRole('button', { name: 'Start agent' }).waitFor({ timeout: TIMEOUT })
  const ended = runs(served)

  expect(looping).toBe(true)
  expect(started).toContain('"loop": true')
  expect(started).toContain('"exit_code": null')
  expect(ended).toContain('"exit_code": -15')
})

test('e2e_every_agent_stops_and_resumes', async ({ agentPage: { served, page } }) => {
  await agent(page).getByRole('button', { name: 'Start agent' }).click()
  await agent(page).getByText('Iteration 1 on Spec').waitFor({ timeout: TIMEOUT })
  await page.keyboard.press('ControlOrMeta+k')
  await page.getByRole('combobox', { name: 'Search commands' }).fill('Stop every')
  await page.keyboard.press('Enter')
  const notice = page.getByRole('region', { name: 'Agents are stopped' })
  await notice.waitFor({ timeout: TIMEOUT })
  const onBoard = page.url().endsWith('/tickets')
  const halted = existsSync(join(served.home, 'halt.json'))
  await page.goto(`${served.url}/tickets/sample/CF-2`)
  await agent(page).getByRole('button', { name: 'Start agent' }).click()
  await toasts(page)
    .getByText('agents are stopped; resume them on the board or with code-factory resume')
    .waitFor({ timeout: TIMEOUT })
  await page.goto(`${served.url}/tickets`)
  await notice.getByRole('button', { name: 'Resume agents' }).click()
  await notice.waitFor({ state: 'hidden', timeout: TIMEOUT })

  expect(onBoard).toBe(true)
  expect(halted).toBe(true)
  expect(existsSync(join(served.home, 'halt.json'))).toBe(false)
  expect(runs(served)).toContain('"exit_code": -15')
})
