// The Vue board served by `code-factory serve` over a fresh sample: each test gets a schema of its
// own in the test database (`code-factory sample-prepare` and `sample-load`), its own server on a
// free port, and drops the schema when it stops.

import { test as base, expect, type Locator, type Page } from '@playwright/test'
import { spawn, spawnSync, execFileSync, type ChildProcess } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { createInterface } from 'node:readline'
import { isAbsolute, join, resolve } from 'node:path'
import { present } from '../src/test/present'
import { OWNER_COOKIE } from './owner'

export const ROOT = resolve(import.meta.dirname, '../..')
export const TIMEOUT = 10_000

export const DESIGN_VIEWPORTS = [
  ['desktop', 1440, 960, 'light'],
  ['mobile', 390, 844, 'light'],
  ['dark-desktop', 1440, 960, 'dark'],
  ['dark-mobile', 390, 844, 'dark'],
] as const

export async function captureDesign(page: Page, name: string): Promise<void> {
  const directory = process.env.CODE_FACTORY_DESIGN_CAPTURES
  if (directory)
    await page.screenshot({ path: join(directory, `${name}.png`), animations: 'disabled' })
}

/** The environment every `code-factory` process of a test gets: the test database, in a schema. */
function environment(schema: string, extra: NodeJS.ProcessEnv = {}): NodeJS.ProcessEnv {
  const url = process.env.CODE_FACTORY_DATABASE_URL
  if (!url) {
    throw new Error(
      'CODE_FACTORY_DATABASE_URL is not set: point it at the test database (see README.md)',
    )
  }
  return {
    ...process.env,
    CODE_FACTORY_DATABASE_URL: url,
    CODE_FACTORY_DB_SCHEMA: schema,
    ...extra,
  }
}

/** Run a test board command in the repository's Python environment. */
function command(args: string[], executable = 'code-factory'): [string, string[]] {
  return ['uv', ['run', '--project', ROOT, '--quiet', executable, ...args]]
}

/** Run a `code-factory` command to its end; a failure throws its stderr. */
function codeFactory(args: string[], env: NodeJS.ProcessEnv): string {
  const [file, argv] = command(args)
  return execFileSync(file, argv, { env, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] })
}

interface InboxSeed {
  ticket: string
  webhook?: string
  failingPull?: string
  question?: {
    text: string
    choices?: { text: string; recommended?: boolean; description?: string }[]
    several?: boolean
  }
  rewrite?: { before: string; after: string }
  permission?: { id: string; summary: string }
}

/** Seed an agent's question or permission request in this browser test's own schema. */
export function seedInbox(served: Served, seed: InboxSeed): void {
  const args = [resolve(ROOT, 'tests/browser_question_seed.py'), JSON.stringify(seed)]
  execFileSync(...command(args, 'python'), { env: environment(served.schema), stdio: 'pipe' })
}

/** A board's way to its data: where it is served and the schema its tables live in. */
export class Served {
  readonly url: string
  readonly schema: string
  // The previous implementation's folders, kept so the specs that still read its files compile.
  // An empty path would make `git -C` and every relative write act on the checkout the tests run
  // in, so each access throws until its spec is ported to the API.
  get home(): string {
    return notPorted('served.home')
  }

  get root(): string {
    return notPorted('served.root')
  }

  constructor(url: string, schema: string) {
    this.url = url
    this.schema = schema
  }

  /** The API's answer to a request the signed-in owner makes: its status and JSON. */
  async api(
    method: string,
    path: string,
    body?: object,
  ): Promise<{ status: number; json: unknown }> {
    const answer = await fetch(`${this.url}${path}`, {
      method,
      headers: {
        Cookie: OWNER_COOKIE,
        Origin: this.url,
        ...(body ? { 'Content-Type': 'application/json' } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    })
    return { status: answer.status, json: await answer.json().catch(() => null) }
  }

  /** A ticket's fields as its page reads them (the ticket of `repository`). */
  async fields(id: string, repository = 'sample'): Promise<Record<string, string | boolean>> {
    const page = (await this.api('GET', `/api/tickets/${repository}/${id}`)).json as {
      ticket: Record<string, string | boolean>
    }
    return page.ticket
  }

  // Each takes the arguments of the previous implementation's helper, which wrote files.
  // eslint-disable-next-line @typescript-eslint/no-unused-vars -- the old helper's arguments
  ticket(..._args: [id: string, repository?: string]): string {
    return notPorted('served.ticket')
  }

  // eslint-disable-next-line @typescript-eslint/no-unused-vars -- the old helper's arguments
  editTicket(..._args: [id: string, from: string, to: string, repository?: string]): void {
    notPorted('served.editTicket')
  }

  // eslint-disable-next-line @typescript-eslint/no-unused-vars -- the old helper's arguments
  writeMemory(..._args: [entries: Record<string, string>]): string {
    return notPorted('served.writeMemory')
  }

  // eslint-disable-next-line @typescript-eslint/no-unused-vars -- the old helper's arguments
  writeRequest(..._args: [ticket: string, summary: string, id?: string]): string {
    return notPorted('served.writeRequest')
  }
}

function notPorted(what: string): never {
  throw new Error(`${what} read files of the previous implementation: port this spec to the API`)
}

/**
 * Run git at `root` with no global or system configuration, a fixed identity and signing off;
 * its trimmed output. Throws when git fails.
 */
export function git(root: string, ...args: string[]): string {
  // `git -C ''` and a relative folder act on the checkout the tests run in.
  if (!isAbsolute(root)) {
    throw new Error(`git needs an absolute folder, not ${JSON.stringify(root)}`)
  }
  const run = spawnSync('git', ['-c', 'commit.gpgsign=false', '-C', root, ...args], {
    encoding: 'utf8',
    env: {
      ...process.env,
      GIT_AUTHOR_NAME: 'code-factory',
      GIT_AUTHOR_EMAIL: 'fixtures@code-factory.invalid',
      GIT_COMMITTER_NAME: 'code-factory',
      GIT_COMMITTER_EMAIL: 'fixtures@code-factory.invalid',
      GIT_CONFIG_GLOBAL: '/dev/null',
      GIT_CONFIG_NOSYSTEM: '1',
    },
  })
  if (run.status !== 0) throw new Error(`git ${args.join(' ')}: ${run.stderr || String(run.error)}`)
  return run.stdout.trim()
}

/** Every board `start` spawned that no `stop` ended yet. */
const running = new Set<ChildProcess>()

/** End every board still running: a test that failed before its `stop` leaves its board here. */
export function stopAll(): void {
  for (const server of running) server.kill()
  running.clear()
}

// Playwright ends a worker after a failed test; its boards end with it (CF-551).
process.once('exit', stopAll)

/**
 * Start `code-factory serve` on a free port and wait for the address it prints. The board reads
 * its standard input, a pipe this process holds, and stops at its end: a worker ended by a
 * signal, SIGKILL included, never runs `stopAll`, but the kernel closes the pipe (CF-816).
 */
export async function start(
  schema: string,
  options: { env?: NodeJS.ProcessEnv } = {},
): Promise<{ url: string; stop: () => void; server: ChildProcess }> {
  const [file, argv] = command(['serve'])
  const server = spawn(file, argv, {
    env: environment(schema, {
      CODE_FACTORY_PORT: '0',
      CODE_FACTORY_STOP_AT_EOF: '1',
      CODE_FACTORY_OPEN: 'false',
      ...options.env,
    }),
    stdio: ['pipe', 'pipe', 'inherit'],
  })
  running.add(server)
  const lines = createInterface({ input: server.stdout })
  const first = await new Promise<string>((done, fail) => {
    lines.once('line', done)
    server.once('error', fail)
    // A board that ends before it prints its address says how, instead of timing the test out.
    server.once('exit', (code, signal) => {
      fail(new Error(`the board ended (${String(code ?? signal)}) before it printed its address`))
    })
  }).catch((error: unknown) => {
    running.delete(server)
    throw error
  })
  // The board names itself by the loopback address it prints; the cookie in playwright.config.ts
  // is held for it and for `localhost`.
  const found = /^serving on (http:\/\/127\.0\.0\.1:\d+)$/.exec(first)
  if (!found?.[1]) throw new Error(`the board did not start: ${first}`)
  return {
    url: found[1],
    stop: () => {
      running.delete(server)
      server.kill()
    },
    server,
  }
}

/** Make a schema of its own for a sample and load it, `extra` in its environment; its name. */
export function prepareSample(sample: string, extra: NodeJS.ProcessEnv = {}): string {
  const schema = `e2e_${randomBytes(6).toString('hex')}`
  const env = environment(schema, extra)
  try {
    codeFactory(['sample-prepare'], env)
    codeFactory(['sample-load', sample], env)
  } catch (error) {
    dropSample(schema)
    throw error
  }
  return schema
}

/** Drop a sample's schema. */
export function dropSample(schema: string): void {
  spawnSync(...command(['sample-drop']), { env: environment(schema), stdio: 'ignore' })
}

// The previous implementation's executable: the specs that run its hook commands (`capture`,
// `track`) have no command to call yet and fail at that call, by name.
export const BINARY = 'code-factory-command-not-ported'

/**
 * Serve a sample until `stop` is called, then drop its schema. The arguments after `sample` are
 * the previous implementation's (agent stand-in, follower, environment, working folder); they
 * change nothing here and go when the specs that pass them are ported.
 */
export async function serve(
  sample = 'empty',
  // eslint-disable-next-line @typescript-eslint/no-unused-vars -- the old helper's arguments
  ..._previous: [agent?: string, follow?: boolean, env?: NodeJS.ProcessEnv, inRoot?: boolean]
): Promise<{ served: Served; stop: () => void }> {
  const schema = prepareSample(sample)
  const started = await start(schema).catch((error: unknown) => {
    dropSample(schema)
    throw error
  })
  const { url, stop } = started
  return {
    served: new Served(url, schema),
    stop: () => {
      stop()
      dropSample(schema)
    },
  }
}

export const test = base.extend<
  { follow: boolean; held: boolean; served: Served; writesBoard: Page },
  { api: Served }
>({
  // The api sample, unfollowed, shared by a worker's tests that only read it.
  api: [
    async ({}, use) => {
      const { served, stop } = await serve('board')
      await use(served)
      stop()
    },
    { scope: 'worker' },
  ],
  // The follower ends the sample's run (its pid is not an agent of this board) on its first tick.
  follow: [true, { option: true }],
  // The board page's animations held at their start, as a machine too loaded to draw leaves them.
  held: [false, { option: true }],
  served: async ({}, use) => {
    const { served, stop } = await serve('board')
    await use(served)
    stop()
  },
  writesBoard: async ({ browser, held, served }, use) => {
    const context = await browser.newContext()
    await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: served.url })
    const page = await context.newPage()
    if (held) await hold(page)
    await page.goto(`${served.url}/tickets`)
    await boardLoaded(page)
    await use(page)
    await context.close()
  },
})

export { expect, present }

/** Where `locator` is drawn; a failure when it is not drawn. */
export async function box(locator: Locator) {
  return present(await locator.boundingBox(), 'its bounding box')
}

/**
 * Hold the page's animations at their start through CDP, as a machine too loaded to draw a frame
 * leaves them: a wait that needs a drawn frame to see an animation end then runs out (CF-1020).
 */
export async function hold(page: Page): Promise<void> {
  const cdp = await page.context().newCDPSession(page)
  await cdp.send('Animation.enable')
  await cdp.send('Animation.setPlaybackRate', { playbackRate: 0 })
}

/** Switch the page to a theme and wait until its colours, which ease into a theme, rest. */
export async function useTheme(page: Page, theme: string): Promise<void> {
  await page.evaluate((name) => {
    document.documentElement.classList.toggle('dark', name === 'dark')
    document.documentElement.classList.toggle('light', name !== 'dark')
  }, theme)
  await settle(page)
}

/**
 * Finish now the animations of the elements `selector` matches, or of the whole document without
 * one, so a box or colour read next is where it rests. A wait for them to end re-checks only when
 * the page draws a frame, which a loaded machine may not do for seconds (CF-1020). An endless
 * animation has no end to finish at.
 */
export function settle(page: Page, selector?: string): Promise<void> {
  return page.evaluate((within) => {
    const running = within
      ? [...document.querySelectorAll(within)].flatMap((e) => e.getAnimations())
      : document.getAnimations()
    for (const a of running) if (a.effect?.getComputedTiming().endTime !== Infinity) a.finish()
  }, selector)
}

/**
 * The contrast of `element`'s text, or with `fill` of its own background, against the
 * backgrounds painted under it, composited.
 */
export function contrast(element: Locator, fill = false): Promise<number> {
  return element.evaluate((e, ownFill) => {
    const canvas = document.createElement('canvas')
    canvas.width = canvas.height = 1
    const paint = canvas.getContext('2d', { willReadFrequently: true })
    if (!paint) throw new Error('the page has no 2d canvas')
    const layers: string[] = []
    for (let at = ownFill ? e.parentElement : e; at; at = at.parentElement) {
      const colour = getComputedStyle(at).backgroundColor
      if (colour !== 'rgba(0, 0, 0, 0)') layers.unshift(colour)
    }
    const read = (): number[] => [...paint.getImageData(0, 0, 1, 1).data].slice(0, 3)
    paint.fillStyle = '#fff'
    paint.fillRect(0, 0, 1, 1)
    for (const layer of layers) {
      paint.fillStyle = layer
      paint.fillRect(0, 0, 1, 1)
    }
    const back = read()
    paint.fillStyle = ownFill ? getComputedStyle(e).backgroundColor : getComputedStyle(e).color
    paint.fillRect(0, 0, 1, 1)
    const fore = read()
    const lum = (rgb: number[]): number => {
      const [r = 0, g = 0, b = 0] = rgb.map((v) => {
        const c = v / 255
        return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
      })
      return 0.2126 * r + 0.7152 * g + 0.0722 * b
    }
    const [hi = 0, lo = 0] = [lum(back), lum(fore)].sort((a, b) => b - a)
    return (hi + 0.05) / (lo + 0.05)
  }, fill)
}

function pageOf(scope: Page | Locator): Page {
  return 'goto' in scope ? scope : scope.page()
}

/** The board's cards within `scope`: each list item holding a card's actions menu. */
export function cards(scope: Page | Locator): Locator {
  return scope.getByRole('listitem').filter({ has: pageOf(scope).getByLabel(/^Actions for /) })
}

/** The card a person knows by its id and repository. */
export function card(scope: Page | Locator, id: string, repository = 'sample'): Locator {
  const page = pageOf(scope)
  return scope
    .getByRole('listitem')
    .filter({ has: page.getByLabel(`Actions for ${id}`, { exact: true }) })
    .filter({ has: page.getByText(repository, { exact: true }) })
}

/**
 * Hold the board's next poll read unanswered; resolves once it is held. The poll schedules its
 * next read only after the current one is answered (web/src/lib/poll.ts), so from then on only a
 * change's own refresh reads the board, whatever the machine's speed.
 */
export async function holdPoll(page: Page): Promise<void> {
  let held = false
  await page.route('**/api/board', async (route) => {
    if (held) {
      await route.fallback()
      return
    }
    held = true
  })
  await expect.poll(() => held, { timeout: TIMEOUT }).toBe(true)
}

/** Wait until the board shows its cards. */
export async function boardLoaded(page: Page): Promise<void> {
  await expect(cards(page)).not.toHaveCount(0, { timeout: TIMEOUT })
}

export async function menu(page: Page, id: string, repository = 'sample'): Promise<Locator> {
  await card(page, id, repository).hover()
  await card(page, id, repository)
    .getByLabel(`Actions for ${id}`, { exact: true })
    .filter({ visible: true })
    .click()
  return page.getByRole('menu', { name: `Actions for ${id}` })
}

/** Open the submenu `name` of the open menu `items`; the submenu, a menu of its own. */
export async function submenu(items: Locator, name: string): Promise<Locator> {
  await items.getByRole('menuitem', { name, exact: true }).click()
  return items.page().getByRole('menu', { name, exact: true })
}

/** shadcn-vue's Button writes `data-variant` only when a variant is passed: one with none is its
 *  `default`, the board's primary action (docs/design.md, Buttons). */
export const PRIMARY =
  '[data-slot="button"]:not([data-variant]), [data-slot="button"][data-variant="default"]'

/** vue-sonner's toasts, the region that says what a change did (web/src/lib/noticeToasts.ts). */
export function toasts(page: Page): Locator {
  return page.getByRole('region', { name: /^Notifications/ })
}

/** The open Sheet or Dialog: Reka's content, drawn while its state is open. */
export const OPEN_OVERLAY = '[role="dialog"][data-state="open"]'

/** The area below the shell's header that a page scrolls in (web/src/App.vue). */
export function scroller(page: Page): Locator {
  // eslint-disable-next-line playwright/no-raw-locators -- the scroller has no role of its own
  return page.locator('[data-scroller]')
}

/** The variant a shadcn-vue Badge or Button draws: one with no `data-variant` is its default. */
export async function variant(locator: Locator): Promise<string> {
  return (await locator.getAttribute('data-variant')) ?? 'default'
}

/** Add each label to the Labels tags input in `scope`, as typing it and pressing Enter does. */
export async function addLabels(scope: Locator, ...labels: string[]): Promise<void> {
  const field = scope.getByLabel('Labels', { exact: true })
  for (const label of labels) {
    await field.fill(label)
    await field.press('Enter')
  }
}

/** Whether `locator`'s CSS colour `property` is the theme's colour `token` (`destructive`, ...). */
export function drawnIn(locator: Locator, token: string, property = 'color'): Promise<boolean> {
  return locator.evaluate(
    (e, [name, prop]) => {
      const probe = document.createElement('span')
      probe.style.color = `var(--${name})`
      document.body.append(probe)
      const want = getComputedStyle(probe).color
      probe.remove()
      return getComputedStyle(e).getPropertyValue(prop) === want
    },
    [token, property] as const,
  )
}

/** The desktop sidebar's state, `expanded` or `collapsed` (shadcn-vue's Sidebar). */
export function sidebar(page: Page): Locator {
  // eslint-disable-next-line playwright/no-raw-locators -- its state is on an element with no role
  return page.locator('[data-slot="sidebar"]:not([data-mobile])')
}

/** The shell's header: the page title, the board's live state and the page's controls. Inside
 *  the Sidebar's `main` it is no banner landmark. */
export function header(page: Page): Locator {
  // eslint-disable-next-line playwright/no-raw-locators -- a header inside main has no role
  return page.locator('[data-slot="sidebar-inset"] > header')
}
