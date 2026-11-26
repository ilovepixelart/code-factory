// The browser tests' Chromium and `code-factory shoot` (CF-240): scrollbars drawn, as the owner sees
// them, and a ticket's pages captured light and dark from the running board.

import { execFileSync } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { BINARY, expect, test } from './fixtures'

// An unstyled element that always scrolls: it takes scrollbar width only when the browser draws
// scrollbars. A styled one (the board's columns keep a gutter) takes width either way.
const DRAWN_BAR = `(() => {
  const probe = document.createElement('div')
  probe.style.cssText = 'overflow-y: scroll; width: 100px; height: 50px; scrollbar-color: auto'
  document.body.append(probe)
  const width = probe.offsetWidth - probe.clientWidth
  probe.remove()
  return width
})()`

test('e2e_the_test_browser_draws_scrollbars', async ({ page, served }) => {
  await page.goto(`${served.url}/tickets`)

  expect(
    await page.evaluate(DRAWN_BAR),
    'the test browser drew no scrollbar: launch it without --hide-scrollbars, and on macOS set Show scroll bars to Always',
  ).toBeGreaterThan(0)
})

// CF-482: a stalled action fails on its own, naming its locator, with most of the test limit
// left. 3.06 s is the slowest step of three full runs (frd.md); the bound is at least 3 times it.
test('e2e_an_action_gives_up_long_before_the_test_limit', ({ actionTimeout }, testInfo) => {
  expect(actionTimeout).toBeGreaterThanOrEqual(3 * 3_060)
  expect(actionTimeout).toBeLessThanOrEqual(testInfo.timeout / 4)
})

test('e2e_shoot_captures_light_and_dark', ({ served }) => {
  served.editTicket('CF-1', 'labels: docs\n', 'labels: docs, ui\n')

  execFileSync(BINARY, ['shoot', 'CF-1', '--url', served.url], {
    cwd: served.root,
    env: { ...process.env, CODE_FACTORY_HOME: served.home },
  })
  const history = readFileSync(
    join(served.root, '.code-factory', 'tickets', 'CF-1', 'activity.jsonl'),
    'utf8',
  )
  const capture = JSON.parse(history.trim().split('\n').at(-1) ?? '{}') as {
    kind: string
    tree: string
    images: string[]
    scrollbar: number
  }
  const folder = join(served.home, 'captures', 'sample-CF-1', capture.tree)

  expect([capture.kind, capture.images]).toStrictEqual([
    'capture',
    ['tickets-sample-CF-1-light.png', 'tickets-sample-CF-1-dark.png'],
  ])
  expect(capture.images.every((image) => existsSync(join(folder, image)))).toBe(true)
  expect(capture.scrollbar).toBeGreaterThan(0)
})

// CF-531: a page entry naming a section is captured scrolled to it: the capture fails when the
// section's top is not in view, so a capture of Agent runs, the page's last section, passes only
// once it is scrolled into view; a section the page does not have fails
// it, naming the id.
test('e2e_shoot_scrolls_to_the_section_a_page_names', ({ served }) => {
  served.editTicket('CF-1', 'labels: docs\n', 'labels: docs, ui\npages: /flow#agents-heading\n')
  const shoot = () =>
    execFileSync(BINARY, ['shoot', 'CF-1', '--url', served.url], {
      cwd: served.root,
      env: { ...process.env, CODE_FACTORY_HOME: served.home },
      stdio: 'pipe',
    })

  shoot()
  const history = readFileSync(
    join(served.root, '.code-factory', 'tickets', 'CF-1', 'activity.jsonl'),
    'utf8',
  )
  const capture = JSON.parse(history.trim().split('\n').at(-1) ?? '{}') as { images: string[] }
  served.editTicket('CF-1', '/flow#agents-heading', '/flow#no-such-section')
  let refusal = ''
  try {
    shoot()
  } catch (error) {
    refusal = String((error as { stderr?: Buffer }).stderr ?? error)
  }

  expect(capture.images).toStrictEqual([
    'flow-agents-heading-light.png',
    'flow-agents-heading-dark.png',
  ])
  expect(refusal).toContain('/flow shows no section with the id no-such-section')
})
