// The CF-1290 style ticket and its neighbours for the long text spec (CF-1292): one 60 character
// token in each field a card, the panel and the list show, a merged ticket, and a session.

import { execFileSync } from 'node:child_process'
import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { BINARY, Served, git, serve, test as base } from './fixtures'

const DAY = 86_400
const token = (letter: string): string => letter.repeat(60)
const HASH = '61e69803928ab346da3b833c44980c74d9a37f44'
const TITLE = `Main fails web-unused at ${token('t')}`
const SOURCE = `automation:main-failed@${token('s')}`
const BRANCH = `ticket/${token('b').slice(7)}`
const LABEL = token('l')
const ASSIGNEE = token('a')
const SESSION = `s-${token('x')}`
const COMMAND = `cargo test ${'--flag '.repeat(40)}`.slice(0, 200)
const LONG_TOOL = `mcp__${token('m')}__call`
const AGENT = `agent-${token('g').repeat(2)}`.slice(0, 90)
const MODEL = `model-${token('o')}`
const CONNECTION = `connection-${token('c')}`
const KEY_VARIABLE = 'MY_COMPANY_ANTHROPIC_API_KEY_FOR_CODE_FACTORY_PRODUCTION_USE'
const ADDRESS = `https://example.invalid/${'v1/'.repeat(23)}`.slice(0, 71)
export const PULL = 'https://github.com/owner/repo/pull/1185'
// Long enough that the ticket scrolls in its panel and as a page, with the hash in its text.
const DESCRIPTION = Array.from(
  { length: 30 },
  (_, n) => `Paragraph ${String(n)} of the failure on ${HASH}${token('d')}.\n\n`,
).join('')
export const WIDE = { width: 1440, height: 900 }
// The widths at which the properties sit as a column beside the content (CF-1293): the side panel
// from 1544 px (its container reaches 48rem), the ticket page from 1492 px.
export const PANEL_RAIL = { width: 1600, height: 900 }
export const PAGE_RAIL = { width: 1492, height: 900 }
export const SIZES = [WIDE, { width: 390, height: 844 }]
export const THEMES = ['light', 'dark']

export const test = base.extend<{ served: Served }>({
  served: async ({}, use) => {
    const { served, stop } = await serve('writes', 'false', false)
    writeFileSync(join(served.home, 'runs.json'), '[]')
    longText(served)
    await use(served)
    stop()
  },
})

const stamp = (at: number): string => new Date(at * 1000).toISOString().replace(/\.\d{3}Z$/, 'Z')

function ticket(served: Served, id: string, fields: string, records: object[], body = ''): void {
  const folder = join(served.root, '.code-factory', 'tickets', id)
  mkdirSync(folder, { recursive: true })
  writeFileSync(join(folder, 'ticket.md'), `---\nid: ${id}\n${fields}---\n${body}`)
  const lines = records.map((r) => JSON.stringify(r))
  writeFileSync(join(folder, 'activity.jsonl'), lines.join('\n') + '\n')
}

/** CF-90 in Build with a 60 character token in each field a card, the panel and the list show,
 *  CF-91 merged today through git, and a session with a 200 character tool summary. */
function longText(served: Served): void {
  const now = Date.now() / 1000
  const today = Math.floor(now / DAY) * DAY
  ticket(
    served,
    'CF-90',
    `title: ${TITLE}\ntype: bug\nstage: build\nbranch: ${BRANCH}\nlabels: ${LABEL}\n` +
      `assignee: ${ASSIGNEE}\nsource: ${SOURCE}\ncaused_by: CF-1281, CF-1282\n`,
    [
      { at: stamp(now - 600), kind: 'pull_request', url: PULL },
      { at: stamp(now - 300), kind: 'merged_pull_request', url: PULL },
      { at: stamp(now - 200), kind: 'pull_request', url: 'https://example.test/pull/9' },
    ],
    DESCRIPTION,
  )
  ticket(served, 'CF-91', `title: Main fails web-unused at ${HASH}${token('h')}\nstage: merged\n`, [
    { at: stamp(today - 3600), kind: 'created', type: 'bug' },
    { at: stamp(today + 1), kind: 'stage', to: 'merged' },
  ])
  const main = git(served.root, 'rev-parse', '--abbrev-ref', 'HEAD')
  git(served.root, 'checkout', '-q', '-b', 'ticket/cf-91')
  writeFileSync(join(served.root, 'shipped.txt'), 'shipped\n')
  git(served.root, 'add', 'shipped.txt')
  git(served.root, 'commit', '-q', '-m', 'CF-91: ship it')
  git(served.root, 'checkout', '-q', main)
  git(
    served.root,
    'merge',
    '-q',
    '--no-ff',
    '-m',
    'Merge pull request #1185 from o/ticket/cf-91',
    'ticket/cf-91',
  )
  const hook = (event: object): void => {
    execFileSync(BINARY, ['capture'], {
      input: JSON.stringify({ session_id: SESSION, cwd: served.root, ...event }),
      env: { ...process.env, CODE_FACTORY_HOME: served.home },
    })
  }
  hook({ hook_event_name: 'SessionStart' })
  hook({ hook_event_name: 'UserPromptSubmit', prompt: COMMAND })
  hook({
    hook_event_name: 'PreToolUse',
    tool_name: 'Bash',
    tool_use_id: 't1',
    tool_input: { command: COMMAND },
  })
  hook({
    hook_event_name: 'PreToolUse',
    tool_name: LONG_TOOL,
    tool_use_id: 't2',
    tool_input: { command: COMMAND },
  })
}

/** An agent with a 90 character name, model and connection, and a connection with a long name,
 *  address and key variable: the Agents page's rows and cards (CF-1292). */
export function longAgents(served: Served): void {
  writeFileSync(
    join(served.home, 'agents.json'),
    JSON.stringify([
      { name: AGENT, runtime: 'claude', connection: CONNECTION, model: MODEL, roles: ['build'] },
    ]),
  )
  writeFileSync(
    join(served.home, 'connections.json'),
    JSON.stringify([
      { name: CONNECTION, kind: 'openai', base_url: ADDRESS, key_env: KEY_VARIABLE },
    ]),
  )
}
