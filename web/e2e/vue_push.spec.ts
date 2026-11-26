// CF-397 acceptance flow: a push target in the state folder's push.json on the writes sample, served
// with its run follower. The push receiver is a fake on a free port of 127.0.0.1 that records
// each request and answers with the status the test sets.

import { writeFileSync } from 'node:fs'
import { createServer, type IncomingHttpHeaders, type Server } from 'node:http'
import type { AddressInfo } from 'node:net'
import { join } from 'node:path'
import { TIMEOUT, expect, test } from './fixtures'

/** Two passes of the board's 5 second push schedule, with room for the first. */
const TWO_PASSES = 15_000

const servers: Server[] = []

test.afterEach(() => {
  for (const server of servers.splice(0)) server.close()
})

interface Received {
  status: number
  headers: IncomingHttpHeaders
  body: string
}

/** A receiver answering `answer.status`; every request it got, with the status it answered. */
async function receiver(): Promise<{
  url: string
  answer: { status: number }
  got: Received[]
}> {
  const answer = { status: 500 }
  const got: Received[] = []
  const server = createServer((request, response) => {
    let body = ''
    request.on('data', (chunk: Buffer) => (body += chunk.toString()))
    request.on('end', () => {
      got.push({ status: answer.status, headers: request.headers, body })
      response.writeHead(answer.status)
      response.end()
    })
  })
  servers.push(server)
  await new Promise<void>((done) => server.listen(0, '127.0.0.1', done))
  const { port } = server.address() as AddressInfo
  return { url: `http://127.0.0.1:${String(port)}`, answer, got }
}

test('e2e_a_failing_push_target_shows_on_the_inbox', async ({ served, writesBoard }) => {
  const push = await receiver()
  const target = { format: 'ntfy', url: `${push.url}/wc_topic-1` }
  writeFileSync(join(served.home, 'push.json'), JSON.stringify(target))
  await writesBoard.goto(`${served.url}/inbox`)
  const notice = writesBoard.getByRole('region', { name: 'Push notifications fail' })

  await expect(notice).toBeVisible({ timeout: TWO_PASSES })
  await expect(notice).toHaveText(
    /Sending to 127\.0\.0\.1 failed at \d\d:\d\d:\d\d: HTTP 500\. What waits is sent again on the next try\./,
  )
  await expect(writesBoard.getByText('Push to 127.0.0.1', { exact: true })).toBeVisible()

  push.answer.status = 200
  await expect(notice).toBeHidden({ timeout: TWO_PASSES })
  const waiting = async (): Promise<number> => {
    const answer = await writesBoard.request.get(`${served.url}/api/inbox/count`)
    return ((await answer.json()) as { count: number }).count
  }
  const delivered = (): Received[] => push.got.filter((r) => r.status === 200)
  await expect
    .poll(async () => delivered().length - (await waiting()), { timeout: TWO_PASSES })
    .toBe(0)

  expect(delivered().length).toBeGreaterThan(0)
  for (const message of delivered()) {
    expect(message.headers.title).toBe('code-factory')
    // CF-1244: the board links to itself by the name it prints.
    const port = new URL(served.url).port
    expect(message.headers.click).toMatch(
      new RegExp(`^http://(?:localhost|127\\.0\\.0\\.1):${port}/inbox#[\\w.-]+$`),
    )
    expect(message.body).toMatch(/^(CF-\d+[: ]|A session waits for permission$)/)
  }
  await expect(writesBoard.getByText('Push to 127.0.0.1', { exact: true })).toBeVisible({
    timeout: TIMEOUT,
  })
})
