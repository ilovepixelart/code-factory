// CF-359 acceptance flow: a connection to a model server is added on the Agents page and chosen
// for an agent, served by the server over the writes sample state with a stand-in agent. The
// model server is a fake on a free port of 127.0.0.1.

import { readFileSync } from 'node:fs'
import { createServer, type Server } from 'node:http'
import type { AddressInfo } from 'node:net'
import { join } from 'node:path'
import { PRIMARY, TIMEOUT, expect, test, toasts } from './fixtures'

const servers: Server[] = []

test.afterEach(() => {
  for (const server of servers.splice(0)) server.close()
})

/** A fake LM Studio: its REST list of models, one that runs an agent and one embedding model. */
async function modelServer(): Promise<string> {
  const server = createServer((request, response) => {
    if (request.url === '/api/v0/models') {
      response.writeHead(200, { 'content-type': 'application/json' })
      response.end(
        JSON.stringify({
          object: 'list',
          data: [
            { id: 'qwen3-coder', type: 'llm', max_context_length: 262_144 },
            { id: 'text-embedding-nomic', type: 'embeddings', max_context_length: 2048 },
          ],
        }),
      )
      return
    }
    response.writeHead(404)
    response.end()
  })
  servers.push(server)
  await new Promise<void>((done) => server.listen(0, '127.0.0.1', done))
  const { port } = server.address() as AddressInfo
  return `http://127.0.0.1:${String(port)}`
}

test('e2e_a_connection_is_added_and_chosen_for_an_agent', async ({ served, writesBoard }) => {
  const address = await modelServer()
  const notice = toasts(writesBoard)
  await writesBoard
    .getByRole('navigation', { name: 'Pages' })
    .getByRole('link', { name: 'Agents' })
    .click()
  await writesBoard
    .getByRole('tablist', { name: 'Show' })
    .getByRole('tab', { name: 'Connections' })
    .click()
  const connections = writesBoard.getByRole('region', { name: /^Connections/ })
  await writesBoard.getByRole('button', { name: 'New connection' }).click()
  const form = writesBoard.getByRole('form', { name: 'New connection' })
  await form.getByRole('textbox', { name: 'Name' }).fill('local')
  await form.getByRole('combobox', { name: 'Kind' }).selectOption({ label: 'LM Studio' })
  await form.getByRole('textbox', { name: 'Address' }).fill(address)
  await form.getByRole('button', { name: 'Add' }).click()
  const local = connections.getByRole('listitem', { name: 'local' })
  await local.waitFor({ timeout: TIMEOUT })

  await expect(notice.getByText('Added local')).toBeVisible()
  await expect(local.getByText('answers')).toBeVisible({ timeout: TIMEOUT })
  await local.getByText('1 model', { exact: true }).click()
  await expect(local.getByText('qwen3-coder')).toBeVisible()
  await expect(local.getByText('text-embedding-nomic')).toHaveCount(0)

  await writesBoard
    .getByRole('tablist', { name: 'Show' })
    .getByRole('tab', { name: 'Agents' })
    .click()
  await writesBoard.getByRole('button', { name: 'New agent' }).click()
  const agent = writesBoard.getByRole('form', { name: 'New agent' })
  await agent.getByRole('textbox', { name: 'Name' }).fill('writer')
  await agent.getByRole('checkbox', { name: 'Spec' }).check()
  await agent.getByRole('combobox', { name: 'Connection' }).selectOption('local')
  await expect(agent.getByRole('option', { name: 'qwen3-coder', includeHidden: true })).toHaveCount(
    1,
  )
  await agent.getByRole('combobox', { name: 'Model' }).fill('qwen3-coder')
  await agent.getByRole('button', { name: 'Add' }).click()
  const writer = writesBoard
    .getByRole('region', { name: /^Agents/ })
    .getByRole('listitem', { name: 'writer' })
  await writer.waitFor({ timeout: TIMEOUT })

  await expect(writer.getByText('claude harness · local')).toBeVisible()
  expect(JSON.parse(readFileSync(join(served.home, 'agents.json'), 'utf8'))).toMatchObject([
    { name: 'writer', connection: 'local', model: 'qwen3-coder' },
  ])
})

test('e2e_new_connection_is_the_headers_primary_and_its_form_takes_and_returns_focus', async ({
  served,
  writesBoard,
}) => {
  await writesBoard.goto(`${served.url}/agents?tab=connections`)
  const opener = writesBoard.getByRole('button', { name: 'New connection' })
  await opener.waitFor({ timeout: TIMEOUT })
  const last = await writesBoard.evaluate(() =>
    document.getElementById('header-controls')?.lastElementChild?.textContent.trim(),
  )
  const primaries = await writesBoard
    .getByRole('button')
    .evaluateAll(
      (all, primary) => all.filter((b) => b.matches(primary)).map((b) => b.textContent.trim()),
      PRIMARY,
    )

  expect([last, primaries]).toStrictEqual(['New connection', ['New connection']])
  await opener.click()
  const form = writesBoard.getByRole('form', { name: 'New connection' })
  await expect(form.getByRole('textbox', { name: 'Name' })).toBeFocused()
  await form.getByRole('button', { name: 'Cancel' }).click()
  await expect(opener).toBeFocused()

  await opener.click()
  await form.getByRole('textbox', { name: 'Name' }).fill('local')
  await form.getByRole('textbox', { name: 'Address' }).fill('http://127.0.0.1:9')
  await form.getByRole('button', { name: 'Add' }).click()
  await expect(form).toHaveCount(0, { timeout: TIMEOUT })
  await expect(opener).toBeFocused()
})

test('e2e_new_agent_takes_focus_and_gives_it_back', async ({ served, writesBoard }) => {
  await writesBoard.goto(`${served.url}/agents`)
  const opener = writesBoard.getByRole('button', { name: 'New agent' })
  await opener.waitFor({ timeout: TIMEOUT })

  await opener.click()
  const form = writesBoard.getByRole('form', { name: 'New agent' })
  await expect(form.getByRole('textbox', { name: 'Name' })).toBeFocused()
  await form.getByRole('button', { name: 'Cancel' }).click()
  await expect(opener).toBeFocused()

  await opener.click()
  await form.getByRole('textbox', { name: 'Name' }).fill('writer')
  await form.getByRole('checkbox', { name: 'Spec' }).check()
  await form.getByRole('button', { name: 'Add' }).click()
  await expect(form).toHaveCount(0, { timeout: TIMEOUT })
  await expect(opener).toBeFocused()
})
