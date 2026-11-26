// Every page over the `demo` sample: each shows what the sample filed, with no console error.
// The demo writes git repositories and transcripts under its state folder, so it gets one of its
// own rather than the default the owner's board uses.

import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import type { Locator, Page } from '@playwright/test'
import {
  DESIGN_VIEWPORTS,
  TIMEOUT,
  captureDesign,
  dropSample,
  expect,
  prepareSample,
  start,
  test,
} from './fixtures'

let url = ''
let stop = (): void => undefined
let schema = ''
let state = ''

// Preparing the demo writes three git repositories and runs checks and hooks: it takes a while.
const LOAD_MS = 180_000

test.describe.configure({ mode: 'serial' })

test.beforeAll(async () => {
  test.setTimeout(LOAD_MS)
  state = mkdtempSync(join(tmpdir(), 'cf-demo-'))
  const claude = join(state, 'claude')
  const agents = join(claude, 'agents')
  mkdirSync(agents, { recursive: true })
  writeFileSync(
    join(agents, 'code-reviewer.md'),
    '---\nname: code-reviewer\ndescription: Reviews a diff.\ntools: Read, Grep\n---\n',
  )
  const env = { CODE_FACTORY_STATE_DIR: state, CLAUDE_CONFIG_DIR: claude }
  schema = prepareSample('demo', env)
  const started = await start(schema, { env })
  url = started.url
  stop = started.stop
})

test.afterAll(() => {
  stop()
  dropSample(schema)
  rmSync(state, { recursive: true, force: true })
})

/** Open `path`, collecting the page's console errors and uncaught exceptions. */
async function visit(page: Page, path: string): Promise<string[]> {
  const errors: string[] = []
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text())
  })
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto(`${url}${path}`)
  return errors
}

async function shows(page: Page, texts: string[]): Promise<void> {
  for (const text of texts) {
    await expect(page.getByRole('main')).toContainText(text, { timeout: TIMEOUT })
  }
}

test('e2e_demo_tickets_show_every_column_of_the_three_repositories', async ({ page }) => {
  const errors = await visit(page, '/tickets')
  await shows(page, [
    'Gift cards',
    'Pay part of an order with a gift card',
    'Issue a gift card code on purchase',
    'Coupons expire at the end of their day',
    'Agents are stopped',
  ])
  const blocker = page.getByRole('note').filter({ hasText: 'Blocked by CF-12' })
  await expect(blocker).toBeVisible()
  expect(await blocker.evaluate((node) => node.getBoundingClientRect().height)).toBeLessThanOrEqual(
    18,
  )
  const laneCount = await page
    .getByRole('button', { name: 'Build', exact: true })
    .evaluate((lane) => {
      const pill = lane.parentElement?.querySelector('[data-lane-count-pill]')
      if (!pill) return null
      const { fontSize, height } = getComputedStyle(pill)
      return { fontSize, height }
    })
  expect(laneCount).toStrictEqual({ fontSize: '12px', height: '18px' })
  await page.getByRole('button', { name: 'Views', exact: true }).click()
  await expect(page.getByText('High priority', { exact: true })).toBeVisible()
  await expect(page.getByText('Storefront', { exact: true })).toBeVisible()
  expect(errors).toStrictEqual([])
})

test('e2e_demo_a_ticket_shows_its_documents_and_its_question', async ({ page }) => {
  const errors = await visit(page, '/tickets')
  // A fresh schema numbers the demo's tickets from CF-1: Gift cards is the eleventh.
  await page.goto(`${url}/tickets/shop-api/CF-11`)
  await shows(page, ['Customers buy a gift card and pay with it', 'Do gift cards expire?'])
  expect(errors).toStrictEqual([])
})

test('e2e_demo_inbox_shows_the_questions_the_proposal_and_the_capture', async ({ page }) => {
  const errors = await visit(page, '/inbox')
  await shows(page, [
    'Do gift cards expire?',
    'Which is spent first when an order has a gift card and a coupon?',
    "Read the shop's timezone from settings, never from the server",
    'Ready to merge',
    'Failing checks',
    'Idle pull requests',
  ])
  const count = await page.getByRole('heading', { name: /^Questions/ }).evaluate((heading) => {
    const pill = heading.querySelector('[data-section-count]')
    if (!pill) return null
    const box = pill.getBoundingClientRect()
    const title = heading.getBoundingClientRect()
    return {
      fontSize: getComputedStyle(pill).fontSize,
      offset: Math.abs(box.y + box.height / 2 - (title.y + title.height / 2)),
    }
  })
  const mergeable = page.getByRole('region', { name: /^Ready to merge/ })
  await expect(mergeable.getByRole('listitem')).toHaveAttribute('data-slot', 'card')
  expect(count?.fontSize).toBe('12px')
  expect(count?.offset).toBeLessThan(1)
  await page.setViewportSize({ width: 390, height: 844 })
  const scrollWidth = await page.getByRole('main').evaluate((main) => {
    const scroller = main.querySelector('[data-scroller]')
    return scroller ? scroller.scrollWidth - scroller.clientWidth : -1
  })
  expect(scrollWidth).toBe(0)
  expect(errors).toStrictEqual([])
})

test('e2e_demo_sessions_and_a_session_show_the_recorded_work', async ({ page }) => {
  const errors = await visit(page, '/')
  await shows(page, [
    'Search ranks in-stock products first',
    'Pay part of an order with a gift card',
  ])
  await page.goto(`${url}/sessions/demo-search-rank`)
  await shows(page, ['Rank in-stock products above the rest'])
  expect(errors).toStrictEqual([])
})

test('e2e_demo_analytics_flow_shows_the_merges_and_scorers_the_answers', async ({ page }) => {
  const errors = await visit(page, '/analytics?range=30d')
  await shows(page, ['Shipped', 'Product images load lazily below the fold'])
  await page.getByRole('button', { name: 'Show response times' }).click()
  await shows(page, ['across 3 answered questions'])
  await page.getByRole('button', { name: 'Recent check runs and time budgets' }).click()
  await shows(page, ['Over budget'])
  await page.goto(`${url}/analytics/scorers`)
  await shows(page, ['test-first'])
  // The demo carries recorded runs and PRs. Hidden eval tabs redirect to Flow.
  await page.goto(`${url}/analytics/factory`)
  await shows(page, [
    'Pull request outcomes',
    'Most expensive pull requests',
    'Merge outcomes by repair round',
    'closed unmerged',
    'Review role notes',
    '17 finished, 1 failed, 0 stopped',
  ])
  await expect(page.getByRole('table', { name: 'Most expensive pull requests' })).toBeVisible()
  await page.goto(`${url}/analytics/benchmarks`)
  await expect(page).toHaveURL(`${url}/analytics`)
  await page.goto(`${url}/analytics/self-improvement`)
  await expect(page).toHaveURL(`${url}/analytics`)
  expect(errors).toStrictEqual([])
})

test('e2e_demo_archive_memory_agents_and_team_show_what_the_demo_filed', async ({ page }) => {
  const errors = await visit(page, '/archive')
  await shows(page, ['Checkout refunds partial orders', 'Released 1.3.0'])
  await page.goto(`${url}/archive?show=hand`)
  await shows(page, ['Product page shows delivery estimate', 'Archived by hand'])
  await page.goto(`${url}/memory`)
  await shows(page, ['Money is stored in integer cents, never floats'])
  const core = page.getByRole('region', { name: /^Core/ })
  const entries = core.getByRole('listitem')
  await expect(entries).toHaveCount(3)
  const dividers = await core.evaluate(
    (node) => node.querySelectorAll('[data-slot="item-separator"]').length,
  )
  expect(dividers).toBe(0)
  const statement = 'Money is stored in integer cents, never floats'
  const entry = core.getByRole('listitem', { name: statement })
  await expect(entry).toHaveCSS('border-radius', '8.4px')
  const proposal = page.getByRole('region', { name: /^Proposed by agents/ })
  await expect(
    proposal.getByRole('article', {
      name: "Read the shop's timezone from settings, never from the server",
    }),
  ).toBeVisible()
  await entry.getByText(statement, { exact: true }).click()
  await expect(entry.getByRole('button', { name: 'Edit' })).toBeVisible()
  await page.goto(`${url}/agents`)
  await shows(page, ['builder', 'reviewer'])
  await expect(page.getByRole('table', { name: 'Spec run order' })).toBeVisible()
  const claude = page.getByRole('region', { name: /^Claude Code agents/ })
  const reviewer = claude.getByRole('listitem').filter({ hasText: 'code-reviewer' })
  await expect(reviewer).toHaveAttribute('data-slot', 'card')
  await page.setViewportSize({ width: 1440, height: 960 })
  await page.goto(`${url}/team`)
  await shows(page, ['Move staging to the new cluster'])
  const waitingOnYou = page.getByRole('table', { name: 'Waiting on you', exact: true })
  await expect(waitingOnYou.getByRole('columnheader', { name: 'Title' })).toBeVisible()
  await expect(waitingOnYou.getByRole('button', { name: 'Export orders as CSV' })).toBeVisible()
  const waiting = page.getByRole('table', { name: 'Waiting', exact: true })
  await expect(waiting).toBeVisible()
  const x = (table: Locator) =>
    table
      .getByRole('columnheader')
      .evaluateAll((cells) => cells.map((cell) => Math.round(cell.getBoundingClientRect().left)))
  expect(await x(waitingOnYou)).toStrictEqual(await x(waiting))
  expect(errors).toStrictEqual([])
})

test('e2e_demo_factory_tables_fit_and_sort_on_a_phone', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(`${url}/analytics/factory`)
  for (const caption of [
    'Pull request merge outcomes by repair round',
    'Review role notes linked to fixes',
    'Most expensive pull requests',
  ]) {
    const table = page.getByRole('table', { name: caption })
    await expect(table).toBeVisible()
    const layout = await table.evaluate((node) => {
      const container = node.parentElement
      const cell = node.querySelector('tbody td')
      const row = node.querySelector('tbody tr')
      const body = node.querySelector('tbody')
      return {
        overflow: container ? container.scrollWidth - container.clientWidth : -1,
        labelDisplay: cell ? getComputedStyle(cell, '::before').display : null,
        divider: row ? getComputedStyle(row).borderBottomWidth : null,
        radius: row ? getComputedStyle(row).borderTopLeftRadius : null,
        gap: body ? getComputedStyle(body).rowGap : null,
      }
    })
    expect(layout, caption).toStrictEqual({
      overflow: 0,
      labelDisplay: 'block',
      divider: '0px',
      radius: '10.8px',
      gap: '12px',
    })
  }
  await page.getByRole('button', { name: /Sort by .* for Pull request merge outcomes/ }).click()
  await page.getByRole('menuitem', { name: 'Merged', exact: true }).click()
  await expect(page).toHaveURL(/fix_rounds_sort=merged&fix_rounds_dir=desc/)
  const heading = page.getByRole('heading', { name: /Merge outcomes by repair round/ })
  await heading.evaluate((node) => {
    node.scrollIntoView({ block: 'start' })
  })
  await captureDesign(page, 'mobile-factory-outcomes')
  await page.setViewportSize({ width: 1440, height: 960 })
  const outcomes = page.getByRole('table', { name: 'Pull request merge outcomes by repair round' })
  await expect(outcomes.getByRole('columnheader', { name: 'Merged', exact: true })).toBeVisible()
  for (const row of await outcomes.getByRole('row').all()) {
    await expect(row).toHaveCSS('display', 'table-row')
    await expect(row).toHaveCSS('border-bottom-width', '0px')
  }
})

const SCREENS = [
  ['sessions', '/', 'Search ranks in-stock products first'],
  ['session', '/sessions/demo-search-rank', 'Rank in-stock products above the rest'],
  ['tickets', '/tickets', 'Gift cards'],
  ['ticket-list', '/tickets/list', 'Gift cards'],
  ['ticket', '/tickets/shop-api/CF-11', 'Customers buy a gift card and pay with it'],
  ['inbox', '/inbox', 'Do gift cards expire?'],
  ['flow', '/analytics?range=30d', 'Shipped'],
  ['factory', '/analytics/factory', 'Cost per PR'],
  ['scorers', '/analytics/scorers', 'test-first'],
  ['archive', '/archive', 'Released 1.3.0'],
  ['memory', '/memory', 'Money is stored in integer cents'],
  ['agents', '/agents', 'builder'],
  ['connections', '/agents?tab=connections', 'Check'],
  ['team', '/team', 'Move staging to the new cluster'],
  ['design', '/design', 'Design'],
  ['not-found', '/missing-screen', 'Nothing at this address'],
] as const

test('e2e_demo_each_screen_fits_on_desktop_and_mobile_in_both_themes', async ({ page }) => {
  test.setTimeout(LOAD_MS)
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  for (const [mode, width, height, colorScheme] of DESIGN_VIEWPORTS) {
    await page.emulateMedia({ colorScheme })
    await page.setViewportSize({ width, height })
    for (const [name, path, text] of SCREENS) {
      await page.goto(`${url}${path}`)
      await shows(page, [text])
      const viewport = await page.evaluate(() => {
        const scroller = document.querySelector('[data-scroller]')
        const workspace = scroller?.querySelector('.page-wide')
        return {
          document: document.documentElement.scrollWidth,
          window: innerWidth,
          dark: document.documentElement.classList.contains('dark'),
          scroller: scroller?.clientWidth ?? 0,
          workspace: workspace?.getBoundingClientRect().width ?? 0,
        }
      })
      expect(viewport.document, `${name} on ${mode}`).toBeLessThanOrEqual(viewport.window)
      expect(viewport.dark, `${name} on ${mode}`).toBe(colorScheme === 'dark')
      expect(viewport.workspace, `${name} on ${mode}`).toBeGreaterThan(0)
      expect(viewport.workspace, `${name} on ${mode}`).toBeGreaterThanOrEqual(viewport.scroller - 2)
      await captureDesign(page, `${mode}-${name}`)
    }
  }
  expect(errors).toStrictEqual([])
})

async function labelAbove(form: Locator, label: string): Promise<void> {
  const top = await form.getByLabel(label, { exact: true }).evaluate((control) => {
    const label = (control as HTMLInputElement).labels?.[0]
    return label ? control.getBoundingClientRect().top - label.getBoundingClientRect().bottom : -1
  })
  expect(top, label).toBeGreaterThanOrEqual(0)
}

test('e2e_demo_forms_keep_labels_above_their_controls', async ({ page }) => {
  test.setTimeout(LOAD_MS)
  for (const [mode, width, height] of DESIGN_VIEWPORTS.slice(0, 2)) {
    await page.setViewportSize({ width, height })
    await page.goto(`${url}/agents`)
    await page.getByRole('button', { name: 'New agent', exact: true }).click()
    const agent = page.getByRole('form', { name: 'New agent' })
    await expect(agent).toBeVisible()
    await labelAbove(agent, 'Name')
    await labelAbove(agent, 'Harness')
    await captureDesign(page, `${mode}-agent-form`)

    await page.goto(`${url}/agents?tab=connections`)
    await page.getByRole('button', { name: 'New connection', exact: true }).click()
    const connection = page.getByRole('form', { name: 'New connection' })
    await labelAbove(connection, 'Kind')
    await labelAbove(connection, 'Address')
    await captureDesign(page, `${mode}-connection-form`)

    await page.goto(`${url}/tickets`)
    await shows(page, ['Gift cards'])
    await page
      .getByRole('main')
      .getByRole('button', { name: /New ticket/ })
      .click()
    const ticket = page.getByRole('dialog', { name: 'New ticket' })
    await labelAbove(ticket, 'Title')
    await labelAbove(ticket, 'Repository')
    await expect(ticket.getByRole('button', { name: 'Create ticket' })).toBeInViewport({ ratio: 1 })
    await captureDesign(page, `${mode}-ticket-form`)

    await page.goto(`${url}/memory`)
    await page.getByRole('button', { name: 'Add an entry', exact: true }).click()
    const memory = page.getByRole('form', { name: 'Add an entry' })
    await labelAbove(memory, 'Statement')
    await labelAbove(memory, 'Why')
    await captureDesign(page, `${mode}-memory-form`)
  }
})
