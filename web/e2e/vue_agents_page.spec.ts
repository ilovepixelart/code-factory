// CF-481 acceptance flows: the Agents page's connection rows (the context mark, Edit, a refused
// Remove), Undo of a removal, and a card whose claim went quiet, served by the server over
// the writes sample state without the run follower, so written claims and runs stay as written.
// The model server is a fake LM Studio on a free port of 127.0.0.1.

import { readFileSync, writeFileSync } from 'node:fs'
import { createServer, type Server } from 'node:http'
import type { AddressInfo } from 'node:net'
import { join } from 'node:path'
import type { Page } from '@playwright/test'
import { TIMEOUT, expect, scroller, serve, test as base, toasts, Served } from './fixtures'

/** A pid no process can hold, so nothing a test writes is ever signalled. */
const NO_PROCESS = 2_147_483_647

/** A fake LM Studio listing `models` (id and context length); its address. */
async function studio(models: [string, number][]): Promise<{ address: string; server: Server }> {
  const server = createServer((request, response) => {
    if (request.url !== '/api/v0/models') {
      response.writeHead(404)
      response.end()
      return
    }
    response.writeHead(200, { 'content-type': 'application/json' })
    response.end(
      JSON.stringify({
        data: models.map(([id, context]) => ({ id, type: 'llm', max_context_length: context })),
      }),
    )
  })
  await new Promise<void>((done) => server.listen(0, '127.0.0.1', done))
  const { port } = server.address() as AddressInfo
  return { address: `http://127.0.0.1:${String(port)}`, server }
}

/** The board unfollowed, with a fake LM Studio behind the connection `local`. */
const test = base.extend<{ board: { served: Served; address: string } }>({
  board: async ({}, use) => {
    const { address, server } = await studio([
      ['short', 63_999],
      ['exact', 64_000],
    ])
    const { served, stop } = await serve('writes', 'false', false)
    writeFileSync(
      join(served.home, 'connections.json'),
      JSON.stringify([{ name: 'local', kind: 'lm-studio', base_url: address, key_env: '' }]),
    )
    await use({ served, address })
    stop()
    server.closeAllConnections()
    server.close()
  },
})

function agents(served: Served, list: object[]): void {
  writeFileSync(join(served.home, 'agents.json'), JSON.stringify(list))
}

function saved(served: Served, file: string): unknown {
  return JSON.parse(readFileSync(join(served.home, file), 'utf8'))
}

function connection(page: Page, name: string) {
  return page.getByRole('region', { name: /^Connections/ }).getByRole('listitem', { name })
}

function card(page: Page, name: string) {
  return page.getByRole('region', { name: /^Agents/ }).getByRole('listitem', { name })
}

test('e2e_a_model_under_64000_is_marked', async ({ board: { served }, page }) => {
  await page.goto(`${served.url}/agents?tab=connections`)
  const local = connection(page, 'local')
  await local.getByText('2 models', { exact: true }).click()
  await expect(local.getByText('short', { exact: true })).toBeVisible({ timeout: TIMEOUT })

  // A model's entry reads as its id, its context and the mark, side by side.
  await expect(local.getByText(/^short\s*63,999 tokens\s*under 64,000$/)).toBeVisible()
  await expect(local.getByText(/^exact\s*64,000 tokens$/)).toBeVisible()
  await expect(local.getByText('under 64,000', { exact: true })).toHaveCount(1)
})

test('e2e_a_removal_on_the_agents_page_is_undone', async ({ board: { served }, page }) => {
  agents(served, [{ name: 'writer', runtime: 'claude', roles: ['spec'] }])
  const undo = toasts(page).getByRole('button', { name: 'Undo' })
  await page.goto(`${served.url}/agents`)
  await card(page, 'writer').getByLabel('More actions for writer').click()
  await card(page, 'writer').getByRole('button', { name: 'Remove' }).click()
  await expect(card(page, 'writer')).toHaveCount(0, { timeout: TIMEOUT })
  await undo.click()

  await expect(card(page, 'writer')).toBeVisible({ timeout: TIMEOUT })
  expect(saved(served, 'agents.json')).toMatchObject([{ name: 'writer' }])

  await page.getByRole('link', { name: 'Connections' }).click()
  await connection(page, 'local').getByRole('button', { name: 'Remove' }).click()
  await expect(connection(page, 'local')).toHaveCount(0, { timeout: TIMEOUT })
  await undo.click()

  await expect(connection(page, 'local')).toBeVisible({ timeout: TIMEOUT })
  expect(saved(served, 'connections.json')).toMatchObject([{ name: 'local' }])
})

test('e2e_a_connection_is_edited_in_place', async ({ board: { served }, page }) => {
  await page.goto(`${served.url}/agents?tab=connections`)
  const local = connection(page, 'local')
  await local.getByRole('button', { name: 'Edit' }).click()
  const form = local.getByRole('form', { name: 'Edit local' })
  await form.getByRole('textbox', { name: 'Address' }).fill('http://127.0.0.1:9')
  await form.getByRole('button', { name: 'Save' }).click()

  await expect(local.getByText('http://127.0.0.1:9', { exact: true })).toBeVisible({
    timeout: TIMEOUT,
  })
  await expect(toasts(page).getByText('Saved local')).toBeVisible()
  expect(saved(served, 'connections.json')).toMatchObject([
    { name: 'local', base_url: 'http://127.0.0.1:9' },
  ])
})

test('e2e_removing_a_connection_an_agent_uses_is_refused', async ({
  board: { served, address },
  page,
}) => {
  agents(served, [
    { name: 'qwen', runtime: 'claude', connection: 'local', model: 'short', roles: ['spec'] },
  ])
  await page.goto(`${served.url}/agents?tab=connections`)
  const local = connection(page, 'local')
  await local.getByRole('button', { name: 'Remove' }).click()

  await expect(local.getByText('agent qwen uses connection local')).toBeVisible({
    timeout: TIMEOUT,
  })
  await expect(local).toBeVisible()
  expect(saved(served, 'connections.json')).toMatchObject([{ name: 'local', base_url: address }])
})

test('e2e_an_agent_whose_claim_went_quiet_is_waiting', async ({ board: { served }, page }) => {
  const now = Date.now() / 1000
  agents(served, [
    { name: 'bonsai', runtime: 'claude', roles: ['spec'] },
    { name: 'qwen', runtime: 'claude', roles: ['spec'] },
  ])
  const run = (agent: string, ticket: string) => ({
    id: `r-${agent}`,
    ticket_id: ticket,
    repository: served.root,
    branch: '',
    worktree: '',
    stage: 'spec',
    pid: NO_PROCESS,
    started_at: now - 300,
    log: '',
    loop: false,
    agent,
  })
  writeFileSync(
    join(served.home, 'runs.json'),
    JSON.stringify([run('qwen', 'CF-2'), run('bonsai', 'CF-3')]),
  )
  const claim = (agent: string, beat: number) => ({
    agent,
    runs: [`r-${agent}`],
    claimed_at: now - 300,
    beat_at: beat,
  })
  writeFileSync(
    join(served.home, 'leases.json'),
    JSON.stringify({
      [`${served.root}:CF-2`]: claim('qwen', now - 120),
      [`${served.root}:CF-3`]: claim('bonsai', now),
    }),
  )
  await page.goto(`${served.url}/agents`)
  const cards = page.getByRole('region', { name: /^Agents/ }).getByRole('listitem')
  await expect(cards).toHaveCount(2, { timeout: TIMEOUT })

  await expect(card(page, 'qwen').getByText('waiting', { exact: true })).toBeVisible()
  await expect(card(page, 'bonsai').getByText('working CF-3')).toBeVisible()
  expect(
    await cards.evaluateAll((all) => all.map((c) => c.getAttribute('aria-label'))),
  ).toStrictEqual(['qwen', 'bonsai'])
})

// CF-472-R2: at a phone's width the page does not scroll sideways, a long name and model id
// truncated inside the card.
test('e2e_the_agents_page_fits_a_phone', async ({ board: { served }, page }) => {
  agents(served, [
    {
      name: 'a-very-long-agent-name-of-forty-chars-xx',
      runtime: 'claude',
      connection: '',
      model: 'claude-sonnet-4-5-20250929-with-a-long-suffix',
      roles: ['spec'],
      max_tokens: null,
      max_seconds: null,
    },
  ])
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(`${served.url}/agents`)
  await expect(card(page, 'a-very-long-agent-name-of-forty-chars-xx')).toBeVisible({
    timeout: TIMEOUT,
  })

  const widths = await scroller(page).evaluate((main) => [main.scrollWidth, main.clientWidth])

  expect(widths[0]).toBeLessThanOrEqual(widths[1] ?? 0)
})

/** Three agents working the Build column, in the order `one`, `two`, `three`. */
const BUILDERS = ['one', 'two', 'three']

async function openRunOrder(served: Served, page: Page): Promise<void> {
  agents(
    served,
    BUILDERS.map((name) => ({
      name,
      runtime: 'claude',
      connection: '',
      model: '',
      roles: ['build'],
    })),
  )
  await page.goto(`${served.url}/agents`)
  await page.getByRole('button', { name: 'Move one down in build' }).waitFor({ timeout: TIMEOUT })
}

const focusedControl = (page: Page) =>
  page.evaluate(() => document.activeElement?.getAttribute('aria-label') ?? 'body')

// A button disabled while its own request runs drops focus to the page body: the pressed control
// keeps it, or the row's other control takes it when this one is no longer available.
test('e2e_a_run_order_move_keeps_keyboard_focus', async ({ board: { served }, page }) => {
  await openRunOrder(served, page)
  const places = page.getByRole('region', { name: 'Run order' }).getByRole('listitem')

  await page.getByRole('button', { name: 'Move one down in build' }).focus()
  await page.keyboard.press('Enter')

  await expect(places).toContainText(['1 two', '2 one', '3 three'])
  await expect.poll(() => focusedControl(page)).toBe('Move one down in build')
})

test('e2e_a_run_order_move_to_the_end_moves_focus_to_the_rows_other_control', async ({
  board: { served },
  page,
}) => {
  await openRunOrder(served, page)
  const places = page.getByRole('region', { name: 'Run order' }).getByRole('listitem')

  await page.getByRole('button', { name: 'Move two down in build' }).focus()
  await page.keyboard.press('Enter')

  await expect(places).toContainText(['1 one', '2 three', '3 two'])
  await expect.poll(() => focusedControl(page)).toBe('Move two up in build')
})
