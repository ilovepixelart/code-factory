// CF-373 acceptance flows: the Agents page shows each agent as a card in a grid, a working one
// naming its ticket, served by the server without the run follower so the written claim and
// run stay as written. CF-377: each card says what its agent last did. CF-378: each card says
// whether its connection answers, against a fake model server on a free port of 127.0.0.1.
// CF-389: a card says its model is loaded with too little context, and its run is refused.
// CF-401: an agent's model is tested with a tool call and a JSON answer, and a failed test holds
// its runs.
// CF-395: a run that met a usage limit shows on its ticket's card and its agent's card.

import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { createServer, type Server } from 'node:http'
import type { AddressInfo } from 'node:net'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import type { Locator, Page } from '@playwright/test'
import {
  TIMEOUT,
  box,
  card,
  expect,
  serve,
  test as base,
  toasts,
  Served,
  drawnIn,
} from './fixtures'

/** A pid no process can hold, so nothing a test writes is ever signalled. */
const NO_PROCESS = 2_147_483_647
const TEAM = ['qwen', 'bonsai', 'gemma', 'granite', 'muse']

/** The board with five agents, `qwen` holding CF-2 by a fresh claim and an active run. */
const test = base.extend<{ team: Served }>({
  team: async ({}, use) => {
    const { served, stop } = await serve('writes', 'false', false)
    const now = Date.now() / 1000
    writeFileSync(
      join(served.home, 'agents.json'),
      JSON.stringify(TEAM.map((name) => ({ name, runtime: 'claude', roles: ['spec'] }))),
    )
    writeFileSync(
      join(served.home, 'runs.json'),
      JSON.stringify([
        {
          id: 'r-qwen',
          ticket_id: 'CF-2',
          repository: served.root,
          branch: '',
          worktree: '',
          stage: 'spec',
          pid: NO_PROCESS,
          started_at: now,
          log: '',
          loop: false,
          agent: 'qwen',
        },
      ]),
    )
    writeFileSync(
      join(served.home, 'leases.json'),
      JSON.stringify({
        [`${served.root}:CF-2`]: { agent: 'qwen', runs: ['r-qwen'], claimed_at: now, beat_at: now },
      }),
    )
    await use(served)
    stop()
  },
})

function agentCards(page: Page): Locator {
  return page.getByRole('region', { name: /^Agents/ }).getByRole('listitem')
}

test('e2e_an_agent_card_links_to_its_ticket', async ({ team, page }) => {
  await page.goto(`${team.url}/agents`)
  const qwen = page.getByRole('listitem', { name: 'qwen' })
  await qwen.waitFor({ timeout: TIMEOUT })

  await expect(qwen.getByText('working CF-2')).toBeVisible()
  for (const name of TEAM.slice(1)) {
    await expect(
      page.getByRole('listitem', { name }).getByText('idle', { exact: true }),
    ).toBeVisible()
  }
  await qwen.getByText('working CF-2').getByRole('link', { name: 'CF-2' }).click()

  await expect(page).toHaveURL(`${team.url}/tickets/sample/CF-2`)
})

test('e2e_agent_cards_fill_the_width', async ({ team, page }) => {
  const across: number[] = []
  for (const [width, height] of [
    [1600, 900],
    [1024, 800],
    [390, 844],
  ] as const) {
    await page.setViewportSize({ width, height })
    await page.goto(`${team.url}/agents`)
    await expect(agentCards(page)).toHaveCount(TEAM.length, { timeout: TIMEOUT })
    const tops = await Promise.all(
      (await agentCards(page).all()).map(async (c) => (await box(c)).y),
    )
    across.push(tops.filter((top) => top === tops[0]).length)
  }

  expect(across).toStrictEqual([3, 2, 1])
})

test('e2e_an_agent_is_paused_from_its_card', async ({ team, page }) => {
  await page.goto(`${team.url}/agents`)
  const gemma = page.getByRole('listitem', { name: 'gemma' })
  await gemma.waitFor({ timeout: TIMEOUT })

  await expect(
    page.getByText(
      'Agents start only by hand: no repository sets [agents] slots in .code-factory/config.toml.',
    ),
  ).toBeVisible()
  await gemma.getByRole('button', { name: 'Pause gemma' }).click()
  await expect(gemma.getByText(/^paused \d\d:\d\d$/)).toBeVisible({ timeout: TIMEOUT })
  await page
    .getByRole('listitem', { name: 'qwen' })
    .getByRole('button', { name: 'Pause qwen' })
    .click()
  await expect(page.getByText('finishing CF-2, then paused')).toBeVisible({ timeout: TIMEOUT })
  // The cards keep their places while the pointer or focus is on them (CF-480-R2): leave them.
  await page.mouse.move(1, 1)
  await page.getByRole('heading', { name: 'Agents', level: 1 }).click()
  const order = () =>
    agentCards(page)
      .getByRole('listitem')
      .evaluateAll((cards) => cards.map((card) => card.getAttribute('aria-label')))
  await expect.poll(order).toStrictEqual(['qwen', 'gemma', 'bonsai', 'granite', 'muse'])
  await gemma.getByRole('button', { name: 'Resume gemma' }).click()

  await expect(gemma.getByText('idle', { exact: true })).toBeVisible({ timeout: TIMEOUT })
})

// A button disabled while its own request runs drops focus to the page body: Pause keeps it.
test('e2e_pause_keeps_keyboard_focus', async ({ team, page }) => {
  await page.goto(`${team.url}/agents`)
  const gemma = page.getByRole('listitem', { name: 'gemma' })
  await gemma.waitFor({ timeout: TIMEOUT })

  await gemma.getByRole('button', { name: 'Pause gemma' }).focus()
  await page.keyboard.press('Enter')

  await expect(gemma.getByText(/^paused \d\d:\d\d$/)).toBeVisible({ timeout: TIMEOUT })
  await expect(gemma.getByRole('button', { name: 'Resume gemma' })).toBeFocused()
})

/** A run of `agent` on `ticket` that started `ago` seconds before `now` and has not ended. */
function activeRun(served: Served, agent: string, ticket: string, ago: number, now: number) {
  return {
    id: `r-${agent}`,
    ticket_id: ticket,
    repository: served.root,
    branch: '',
    worktree: '',
    stage: 'spec',
    pid: NO_PROCESS,
    started_at: now - ago,
    log: join(served.home, `${agent}.log`),
    loop: false,
    agent,
  }
}

test('e2e_a_working_agent_shows_its_usage', async ({ page }) => {
  const { served, stop } = await serve('writes', 'false', false)
  const now = Date.now() / 1000
  const limits = { roles: ['spec'], max_tokens: 2_000_000, max_seconds: 3600 }
  writeFileSync(
    join(served.home, 'agents.json'),
    JSON.stringify([
      { name: 'qwen', runtime: 'opencode', ...limits },
      { name: 'bonsai', runtime: 'claude', ...limits },
      { name: 'gemma', runtime: 'claude', ...limits },
    ]),
  )
  const step = { type: 'step_finish', part: { tokens: { input: 500_000, output: 100_000 } } }
  writeFileSync(join(served.home, 'qwen.log'), `${JSON.stringify(step)}\n${JSON.stringify(step)}\n`)
  writeFileSync(
    join(served.home, 'runs.json'),
    JSON.stringify([
      activeRun(served, 'qwen', 'CF-2', 720, now),
      activeRun(served, 'bonsai', 'CF-3', 3600, now),
    ]),
  )
  const lease = (agent: string) => ({ agent, runs: [`r-${agent}`], claimed_at: now, beat_at: now })
  writeFileSync(
    join(served.home, 'leases.json'),
    JSON.stringify({
      [`${served.root}:CF-2`]: lease('qwen'),
      [`${served.root}:CF-3`]: lease('bonsai'),
    }),
  )
  try {
    await page.goto(`${served.url}/agents`)
    const qwen = page.getByRole('listitem', { name: 'qwen' })
    const bonsai = page.getByRole('listitem', { name: 'bonsai' })
    await qwen.waitFor({ timeout: TIMEOUT })

    const qwenTokens = qwen.getByRole('meter', { name: 'qwen tokens' })
    await expect(qwenTokens).toHaveText('1.2 M of 2 M tokens')
    await expect(qwen.getByRole('meter', { name: 'qwen time' })).toHaveText('12 of 60 min')
    expect(await drawnIn(qwenTokens, 'destructive')).toBe(false)
    await expect(bonsai.getByText('claude reports tokens when its run ends')).toBeVisible()
    await expect(bonsai.getByRole('meter')).toHaveCount(1)
    const bonsaiTime = bonsai.getByRole('meter', { name: 'bonsai time' })
    await expect(bonsaiTime).toHaveText('60 of 60 min')
    expect(await drawnIn(bonsaiTime, 'destructive')).toBe(true)
    await expect(page.getByRole('listitem', { name: 'gemma' }).getByRole('meter')).toHaveCount(0)
  } finally {
    stop()
  }
})

test('e2e_claude_code_agents_are_shown_global_and_local', async ({ page }) => {
  const claude = mkdtempSync(join(tmpdir(), 'code-factory-claude-'))
  mkdirSync(join(claude, 'agents'))
  writeFileSync(
    join(claude, 'agents', 'code-reviewer.md'),
    '---\nname: code-reviewer\ndescription: >-\n  Reviews a diff.\ntools: Read, Grep\n---\n',
  )
  const { served, stop } = await serve(
    'writes',
    'false',
    false,
    { CLAUDE_CONFIG_DIR: claude },
    true,
  )
  mkdirSync(join(served.root, '.claude', 'agents'), { recursive: true })
  writeFileSync(
    join(served.root, '.claude', 'agents', 'ticket-worker.md'),
    '---\nname: ticket-worker\ndescription: Takes one ticket.\nmodel: sonnet\n---\n',
  )
  try {
    await page.goto(`${served.url}/agents`)
    const section = page.getByRole('region', { name: /^Claude Code agents/ })
    const rows = section.getByRole('listitem')
    await expect(rows).toHaveCount(2, { timeout: TIMEOUT })

    await expect(rows).toHaveText([
      /code-reviewerglobalinherits model · Read, Grep/,
      /ticket-workersamplesonnet · all tools/,
    ])
    await expect(section.getByRole('button')).toHaveCount(0)
  } finally {
    stop()
  }
})

/** A server on a free port of 127.0.0.1 answering `answer`; its address. */
async function listening(answer: Parameters<typeof createServer>[1]): Promise<{
  address: string
  server: Server
}> {
  const server = createServer(answer)
  await new Promise<void>((done) => server.listen(0, '127.0.0.1', done))
  const { port } = server.address() as AddressInfo
  return { address: `http://127.0.0.1:${String(port)}`, server }
}

async function closed(server: Server): Promise<void> {
  server.closeAllConnections()
  await new Promise<void>((done) => {
    server.close(() => {
      done()
    })
  })
}

test('e2e_a_card_says_whether_its_connection_answers', async ({ page }) => {
  const studio = await listening((request, response) => {
    if (request.url !== '/api/v0/models') {
      response.writeHead(404)
      response.end()
      return
    }
    response.writeHead(200, { 'content-type': 'application/json' })
    response.end(JSON.stringify({ data: [{ id: 'qwen3-coder', type: 'llm' }] }))
  })
  // A port that was free a moment ago and has nothing listening now.
  const nothing = await listening(() => undefined)
  await closed(nothing.server)
  const { served, stop } = await serve('writes', 'false', false)
  writeFileSync(
    join(served.home, 'connections.json'),
    JSON.stringify([
      { name: 'local', kind: 'lm-studio', base_url: studio.address, key_env: '' },
      { name: 'down', kind: 'lm-studio', base_url: nothing.address, key_env: '' },
      {
        name: 'cloud',
        kind: 'openrouter',
        base_url: 'https://openrouter.ai/api',
        key_env: 'OPENROUTER_WC378_API_KEY',
      },
    ]),
  )
  const agent = (name: string, connection: string, model: string) => ({
    name,
    runtime: 'claude',
    connection,
    model,
    roles: ['spec'],
  })
  writeFileSync(
    join(served.home, 'agents.json'),
    JSON.stringify([
      agent('qwen', 'local', 'qwen3-coder'),
      agent('bonsai', 'local', 'prism-ml/bonsai-27b'),
      agent('gemma', 'down', 'google/gemma-4-e4b'),
      agent('granite', 'cloud', 'ibm/granite-4'),
      agent('muse', '', ''),
    ]),
  )
  try {
    await page.goto(`${served.url}/agents`)
    const card = (name: string) => page.getByRole('listitem', { name })
    await expect(card('qwen').getByText('answers', { exact: true })).toBeVisible({
      timeout: TIMEOUT,
    })

    await expect(card('bonsai').getByText('model not listed', { exact: true })).toBeVisible()
    await expect(card('gemma').getByText('does not answer', { exact: true })).toBeVisible()
    await expect(card('granite').getByText('key missing', { exact: true })).toBeVisible()
    await expect(
      card('muse').getByText('claude harness · no connection', { exact: true }),
    ).toBeVisible()
    await expect(card('muse').getByRole('button', { name: 'Check muse' })).toHaveCount(0)
    const order = await agentCards(page)
      .getByRole('listitem')
      .evaluateAll((cards) => cards.map((c) => c.getAttribute('aria-label')))
    expect(order).toStrictEqual(['bonsai', 'gemma', 'granite', 'qwen', 'muse'])

    await closed(studio.server)
    await card('qwen').getByLabel('More actions for qwen').click()
    await card('qwen').getByRole('button', { name: 'Check qwen' }).click()
    await expect(card('qwen').getByText('does not answer', { exact: true })).toBeVisible({
      timeout: TIMEOUT,
    })
  } finally {
    stop()
    await closed(studio.server)
  }
})

test('e2e_a_card_says_its_model_is_loaded_short', async ({ page }) => {
  const studio = await listening((request, response) => {
    if (request.url !== '/api/v0/models') {
      response.writeHead(404)
      response.end()
      return
    }
    const loaded = (id: string, context: number) => ({
      id,
      type: 'llm',
      state: 'loaded',
      max_context_length: 131_072,
      loaded_context_length: context,
    })
    response.writeHead(200, { 'content-type': 'application/json' })
    response.end(
      JSON.stringify({
        data: [loaded('ibm/granite-4.1-8b', 8192), loaded('qwen/qwen3.8-27b', 131_072)],
      }),
    )
  })
  const { served, stop } = await serve('writes', 'false', false)
  writeFileSync(
    join(served.home, 'connections.json'),
    JSON.stringify([{ name: 'local', kind: 'lm-studio', base_url: studio.address, key_env: '' }]),
  )
  const agent = (name: string, model: string, role: string) => ({
    name,
    runtime: 'claude',
    connection: 'local',
    model,
    roles: [role],
  })
  writeFileSync(
    join(served.home, 'agents.json'),
    JSON.stringify([
      agent('qwen', 'qwen/qwen3.8-27b', 'build'),
      agent('granite', 'ibm/granite-4.1-8b', 'spec'),
    ]),
  )
  try {
    await page.goto(`${served.url}/agents`)
    const card = (name: string) => page.getByRole('listitem', { name })
    await expect(card('granite').getByText('context 8,192 of 64,000', { exact: true })).toBeVisible(
      { timeout: TIMEOUT },
    )
    await expect(card('qwen').getByText('answers', { exact: true })).toBeVisible()
    const order = await agentCards(page)
      .getByRole('listitem')
      .evaluateAll((cards) => cards.map((c) => c.getAttribute('aria-label')))
    expect(order).toStrictEqual(['granite', 'qwen'])

    await page.goto(`${served.url}/tickets/sample/CF-2`)
    const section = page.getByRole('region', { name: /^Agent/ })
    await section.getByRole('button', { name: 'Start agent' }).click()
    await expect(
      toasts(page).getByText(
        'connection local: ibm/granite-4.1-8b is loaded with context 8,192 of 64,000; load it with a larger context',
      ),
    ).toBeVisible({ timeout: TIMEOUT })
    const runs = join(served.home, 'runs.json')
    expect(existsSync(runs) ? readFileSync(runs, 'utf8') : '').not.toContain('"CF-2"')
  } finally {
    stop()
    await closed(studio.server)
  }
})

test('e2e_an_agent_card_says_what_it_last_did', async ({ team, page }) => {
  const now = Math.floor(Date.now() / 1000)
  const ended = (id: string, agent: string, stage: string, ago: number, exit: number) => ({
    id,
    ticket_id: 'CF-2',
    repository: team.root,
    branch: '',
    worktree: '',
    stage,
    pid: NO_PROCESS,
    started_at: now - ago - 60,
    log: '',
    loop: false,
    agent,
    exit_code: exit,
    ended_at: now - ago,
  })
  const qwen = {
    ...ended('r-qwen', 'qwen', 'spec', 0, 0),
    started_at: now,
    exit_code: null,
    ended_at: null,
  }
  writeFileSync(
    join(team.home, 'runs.json'),
    JSON.stringify([
      qwen,
      ended('r-bonsai', 'bonsai', 'build', 7500, 0),
      ended('r-gemma', 'gemma', 'spec', 842, 1),
      ended('r-granite', 'granite', 'spec', 3600, -15),
    ]),
  )
  await page.clock.setFixedTime(now * 1000)
  await page.goto(`${team.url}/agents`)
  const card = (name: string) => page.getByRole('listitem', { name })
  await card('qwen').waitFor({ timeout: TIMEOUT })

  await expect(card('qwen')).toContainText('Last: CF-2 Spec, started 0s ago, running')
  await expect(card('bonsai')).toContainText('Last: CF-2 Build, ended 2.1h ago, finished')
  await expect(card('gemma')).toContainText('Last: CF-2 Spec, ended 14m ago, failed')
  await expect(card('granite')).toContainText('Last: CF-2 Spec, ended 1h ago, stopped')
  await expect(card('muse')).toContainText('No runs yet')
  await expect(card('muse').getByRole('link')).toHaveCount(0)
  await card('bonsai').getByRole('link', { name: 'CF-2' }).click()

  await expect(page).toHaveURL(`${team.url}/tickets/sample/CF-2`)
})

/** A Messages API answer: a call of `add` with 2 and 3 when `tools` are offered, else `text`. */
function messages(body: { tools?: unknown[] }, calls: boolean): object {
  const content = !calls
    ? [{ type: 'text', text: 'I would add them: 5.' }]
    : body.tools
      ? [{ type: 'tool_use', id: 't-1', name: 'add', input: { a: 2, b: 3 } }]
      : [{ type: 'text', text: '{"sum": 5}' }]
  return { type: 'message', role: 'assistant', model: 'm-1', content, stop_reason: 'end_turn' }
}

test('e2e_a_model_check_is_shown_and_holds_runs', async ({ page }) => {
  let calls = false
  const studio = await listening((request, response) => {
    let text = ''
    request.on('data', (chunk: Buffer) => (text += chunk.toString()))
    request.on('end', () => {
      response.writeHead(200, { 'content-type': 'application/json' })
      if (request.method === 'POST' && request.url === '/v1/messages') {
        response.end(JSON.stringify(messages(JSON.parse(text) as { tools?: unknown[] }, calls)))
      } else {
        response.end(
          JSON.stringify({
            data: [{ id: 'm-1', type: 'llm', loaded_context_length: 64_000 }],
          }),
        )
      }
    })
  })
  const { served, stop } = await serve('writes', 'false', false)
  writeFileSync(
    join(served.home, 'connections.json'),
    JSON.stringify([{ name: 'local', kind: 'lm-studio', base_url: studio.address, key_env: '' }]),
  )
  writeFileSync(
    join(served.home, 'agents.json'),
    JSON.stringify([
      { name: 'gemma', runtime: 'claude', connection: 'local', model: 'm-1', roles: ['spec'] },
    ]),
  )
  try {
    await page.goto(`${served.url}/agents`)
    const gemma = page.getByRole('listitem', { name: 'gemma' })
    await expect(gemma.getByText('Model check: not checked')).toBeVisible({ timeout: TIMEOUT })

    await gemma.getByLabel('More actions for gemma').click()
    await gemma.getByRole('button', { name: 'Test model gemma' }).click()
    await expect(gemma).toContainText(/Model check: fails, .* ago, answered without a tool call/, {
      timeout: TIMEOUT,
    })
    await page.goto(`${served.url}/tickets/sample/CF-2`)
    await page
      .getByRole('region', { name: /^Agent/ })
      .getByRole('button', { name: 'Start agent' })
      .click()
    await expect(
      toasts(page).getByText(
        'agent gemma: m-1 failed its model check (answered without a tool call); test it again on the Agents page',
      ),
    ).toBeVisible({ timeout: TIMEOUT })
    const runs = join(served.home, 'runs.json')
    expect(existsSync(runs) ? readFileSync(runs, 'utf8') : '').not.toContain('"CF-2"')

    calls = true
    await page.goto(`${served.url}/agents`)
    await gemma.getByLabel('More actions for gemma').click()
    await gemma.getByRole('button', { name: 'Test model gemma' }).click()
    await expect(gemma).toContainText(/Model check: passes, .* ago/, { timeout: TIMEOUT })
  } finally {
    stop()
    await closed(studio.server)
  }
})

test('e2e_a_usage_limit_shows_on_the_ticket_and_agent_cards', async ({ team, page }) => {
  const now = Math.floor(Date.now() / 1000)
  writeFileSync(
    join(team.home, 'runs.json'),
    JSON.stringify([
      {
        id: 'r-qwen',
        ticket_id: 'CF-2',
        repository: team.root,
        branch: '',
        worktree: '',
        stage: 'spec',
        pid: NO_PROCESS,
        started_at: now - 120,
        log: '',
        loop: true,
        agent: 'qwen',
        exit_code: 1,
        ended_at: now - 60,
        limited_until: now + 7200,
      },
    ]),
  )
  await page.clock.setFixedTime(now * 1000)
  await page.goto(`${team.url}/tickets`)
  const ticket = card(page, 'CF-2')
  await ticket.waitFor({ timeout: TIMEOUT })

  await expect(ticket).toContainText('Usage limit: resumes in 2h')
  await page.goto(`${team.url}/agents`)
  await expect(page.getByRole('listitem', { name: 'qwen' })).toContainText(
    'Last: CF-2 Spec, ended 1m ago, usage limit, resumes in 2h',
  )
})
