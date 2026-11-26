// CF-387: the README's recordings, made from a real run. The board serves the demo sample, each
// test drives one page's flow, and its recording becomes docs/demo/<name>.gif;
// docs/demo/manifest.json lists the tickets each one showed.

import { execFileSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import {
  ROOT,
  TIMEOUT,
  boardLoaded,
  cards,
  dropSample,
  expect,
  prepareSample,
  start,
  test,
} from '../e2e/fixtures'

const SAMPLE = 'demo'
const OUT = join(ROOT, 'docs', 'demo')
/** A pause long enough for a viewer to read what the step showed. */
const READ_MS = 1200
const shown: Record<string, string[]> = {}

// Loading the demo writes git repositories and runs checks: it takes a while.
const LOAD_MS = 180_000

/**
 * The sample served for a recording, with a state folder of its own: the demo writes repositories,
 * transcripts and captures there, which the default folder of the owner's board must not get.
 */
async function served(): Promise<{ url: string; stop: () => void }> {
  test.setTimeout(LOAD_MS)
  const state = mkdtempSync(join(tmpdir(), 'cf-record-'))
  const env = { CODE_FACTORY_STATE_DIR: state }
  const schema = prepareSample(SAMPLE, env)
  const started = await start(schema, { env })
  return {
    url: started.url,
    stop: () => {
      started.stop()
      dropSample(schema)
      rmSync(state, { recursive: true, force: true })
    },
  }
}

// The connection check answers what it really found, less the model servers on this machine's
// default ports, which are the recording machine's, not the sample's.
test.beforeEach(async ({ page }) => {
  await page.route('**/api/connection-status', async (route) => {
    const response = await route.fetch()
    const answer = (await response.json()) as Record<string, unknown>
    await route.fulfill({ response, json: { ...answer, local: [] } })
  })
})

test.afterEach(async ({ page }, info) => {
  const video = page.video()
  await page.context().close()
  if (!video) throw new Error('the demo config records no video')
  mkdirSync(OUT, { recursive: true })
  const palette =
    'fps=8,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse'
  execFileSync('ffmpeg', [
    '-y',
    '-loglevel',
    'error',
    '-i',
    await video.path(),
    '-vf',
    palette,
    join(OUT, `${info.title}.gif`),
  ])
})

test.afterAll(() => {
  writeFileSync(
    join(OUT, 'manifest.json'),
    `${JSON.stringify({ sample: SAMPLE, shown }, null, 2)}\n`,
  )
})

test('board', async ({ page }) => {
  const { url, stop } = await served()
  await page.goto(`${url}/tickets`)
  await boardLoaded(page)
  await page.waitForTimeout(READ_MS)
  const first = cards(page.getByRole('region', { name: 'Spec', exact: true })).first()
  const id = (await first.getAttribute('data-ticket')) ?? ''
  // A card opens its ticket in a dialog over the board, so no frame shows a page reloading.
  await first.getByRole('link').click()
  const opened = page.getByRole('form', { name: `Edit ticket ${id}` })
  await expect(opened).toBeVisible({ timeout: TIMEOUT })
  await page.waitForTimeout(READ_MS * 2)
  await page.keyboard.press('Escape')
  await expect(opened).toBeHidden({ timeout: TIMEOUT })
  await page.waitForTimeout(READ_MS)
  shown.board = [id]
  stop()
})

test('agents', async ({ page }) => {
  const { url, stop } = await served()
  await page.goto(`${url}/agents`)
  // The reviewer holds no ticket, so its pause takes effect at once.
  const reviewer = page.getByRole('listitem', { name: 'reviewer' })
  await reviewer.waitFor({ timeout: TIMEOUT })
  await page.waitForTimeout(READ_MS)
  await reviewer.getByRole('button', { name: 'Pause reviewer' }).click()
  await expect(reviewer.getByText(/^paused \d\d:\d\d$/)).toBeVisible({ timeout: TIMEOUT })
  await expect(page.getByRole('region', { name: /Found on this machine/ })).toHaveCount(0)
  await page.waitForTimeout(READ_MS * 2)
  shown.agents = []
  stop()
})

test('inbox', async ({ page }) => {
  const { url, stop } = await served()
  await page.goto(`${url}/inbox`)
  const questions = page.getByRole('region', { name: 'Questions' })
  await questions.waitFor({ timeout: TIMEOUT })
  await page.waitForTimeout(READ_MS)
  const asked = questions.getByRole('listitem').first()
  const id = (await asked.getByRole('link').first().textContent())?.split(' ')[0] ?? ''
  const before = await questions.getByRole('article').count()
  await asked
    .getByRole('group', { name: /^Choices for / })
    .getByRole('button')
    .first()
    .click()
  await expect(questions.getByRole('article')).toHaveCount(before - 1, { timeout: TIMEOUT })
  await page.waitForTimeout(READ_MS * 2)
  shown.inbox = [id]
  stop()
})
