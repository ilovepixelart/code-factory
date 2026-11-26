// CF-760, CF-997: a pushed reply link, opened at a phone's width with no sign-in.

import { createServer, type Server } from 'node:http'
import type { AddressInfo } from 'node:net'
import { TIMEOUT, expect, seedInbox, serve, test } from './fixtures'

const PHONE = { width: 390, height: 844 }
const REFUSAL = 'this link was used, has expired or is not known'
/** One 5-second push pass and its delivery, twice over. */
const PUSHED_WITHIN = 15_000

test.use({ storageState: { cookies: [], origins: [] }, viewport: PHONE })

/** A local webhook receiver and the bodies it was sent. */
async function receiver(): Promise<{ server: Server; address: string; bodies: unknown[] }> {
  const bodies: unknown[] = []
  const server = createServer((request, response) => {
    let text = ''
    request.on('data', (chunk: Buffer) => (text += chunk.toString()))
    request.on('end', () => {
      bodies.push(JSON.parse(text))
      response.end()
    })
  })
  await new Promise<void>((listening) => server.listen(0, '127.0.0.1', listening))
  return {
    server,
    address: `http://127.0.0.1:${String((server.address() as AddressInfo).port)}`,
    bodies,
  }
}

/** The reply link the board pushed for the request `id`, once it has. */
async function pushedLink(bodies: unknown[], id: string): Promise<string> {
  const found = (): { reply?: string } | undefined =>
    (bodies as { link?: string; reply?: string }[]).find((b) => b.link?.endsWith(`#perm-${id}`))
  await expect.poll(() => found()?.reply ?? '', { timeout: PUSHED_WITHIN }).toMatch(/\/reply\//)
  return found()?.reply ?? ''
}

// CF-760-R7, CF-760-R2, CF-760-R3, CF-760-R4 (CF-760-A1, A2, A3): the page opened from the push
// shows the request and acts only on the press; the link then says it is spent.
test('e2e_a_permission_is_allowed_from_its_reply_link', async ({ page }) => {
  const hook = await receiver()
  const { served, stop } = await serve('board')
  try {
    const id = 'aaaaaaaaaaaa'
    seedInbox(served, {
      ticket: 'CF-1',
      webhook: hook.address,
      permission: { id, summary: 'pnpm --dir web test' },
    })
    const link = await pushedLink(hook.bodies, id)
    const asked: string[] = []
    page.on('request', (sent) => {
      const path = new URL(sent.url()).pathname
      if (path.startsWith('/api/')) asked.push(path)
    })

    await page.goto(link)

    await expect(page.getByText('CF-1', { exact: true })).toBeVisible({ timeout: TIMEOUT })
    await expect(page.getByText('pnpm --dir web test')).toBeVisible()
    await expect(page.getByText('Bash', { exact: true })).toBeVisible()
    await expect(page.getByRole('navigation')).toHaveCount(0)
    expect((await served.api('GET', '/api/inbox/count')).json).toMatchObject({ count: 1 })
    const sideways = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)
    expect(sideways).toBe(false)

    await page.getByRole('button', { name: 'Allow' }).click()

    await expect(page.getByText('Allowed', { exact: true })).toBeVisible({ timeout: TIMEOUT })
    await expect(page.getByRole('button')).toHaveCount(0)
    expect((await served.api('GET', '/api/inbox/count')).json).toMatchObject({ count: 0 })
    const own = new URL(link).pathname
    expect(asked.every((path) => path === `/api${own}`)).toBe(true)

    await page.reload()

    await expect(page.getByText(REFUSAL)).toBeVisible({ timeout: TIMEOUT })
    await expect(page.getByRole('button')).toHaveCount(0)
  } finally {
    stop()
    hook.server.close()
  }
})

// CF-760-R4: an unknown link says what a used one says, offers nothing, and an address that cannot
// be a link is no page at all.
test('e2e_an_unknown_reply_link_is_refused', async ({ page }) => {
  const { served, stop } = await serve('board')
  try {
    await page.goto(`${served.url}/reply/${'0'.repeat(64)}`)
    await expect(page.getByText(REFUSAL)).toBeVisible({ timeout: TIMEOUT })
    await expect(page.getByRole('button')).toHaveCount(0)
    await page.goto(`${served.url}/reply/abc`)
    await expect(page.getByText('There is no page at')).toBeVisible({ timeout: TIMEOUT })
  } finally {
    stop()
  }
})

// CF-997-R6 (CF-997-A1, A2): a question is answered from its link, and the link is then spent.
test('e2e_a_question_is_answered_from_its_reply_link', async ({ page }) => {
  const hook = await receiver()
  const { served, stop } = await serve('board')
  try {
    seedInbox(served, {
      ticket: 'CF-1',
      webhook: hook.address,
      question: {
        text: 'Which page shows it?',
        choices: [{ text: 'Flow' }, { text: 'Board' }],
      },
    })
    const found = (): { reply?: string } | undefined =>
      (hook.bodies as { kind?: string; ticket?: string; reply?: string }[]).find(
        (b) => b.kind === 'question' && b.ticket === 'CF-1',
      )
    await expect.poll(() => found()?.reply ?? '', { timeout: PUSHED_WITHIN }).toMatch(/\/reply\//)

    await page.goto(found()?.reply ?? '')

    await expect(page.getByText('Which page shows it?', { exact: true })).toBeVisible({
      timeout: TIMEOUT,
    })
    const other = page.getByRole('textbox', { name: /Other answer/ })
    const send = page.getByRole('button', { name: 'Send' })
    await expect(send).toBeDisabled()
    const posted: string[] = []
    page.on('request', (request) => {
      if (request.method() === 'POST') posted.push(request.url())
    })
    await other.press('Enter')
    await expect(send).toBeDisabled()
    await expect(other).toBeVisible()
    await page.getByRole('radio', { name: 'Flow' }).check()
    await send.click()

    await expect(page.getByText('Answered', { exact: true })).toBeVisible({ timeout: TIMEOUT })
    expect(posted).toHaveLength(1)
    const ticket = await served.api('GET', '/api/tickets/sample/CF-1')
    expect(ticket.json).toMatchObject({ questions: [{ answer: 'Flow' }] })

    await page.reload()

    await expect(page.getByText(REFUSAL)).toBeVisible({ timeout: TIMEOUT })
  } finally {
    stop()
    hook.server.close()
  }
})
