// CF-441: every action the Inbox offers, used in a browser on the metrics sample (an item waiting
// in every section), served unfollowed so the sample stays as written.

import { chmodSync, existsSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import type { Page } from '@playwright/test'
import { TIMEOUT, expect, seedInbox, serve, test, toasts, type Served } from './fixtures'

/** Serve the metrics sample, changed by `prepare`, with `/inbox` open; its board. */
async function openInbox(
  page: Page,
  prepare: (served: Served) => void = () => undefined,
  env: NodeJS.ProcessEnv = {},
): Promise<{ served: Served; stop: () => void }> {
  const { served, stop } = await serve('metrics', 'false', false, env)
  prepare(served)
  await page.goto(`${served.url}/inbox`)
  await page.getByRole('region', { name: 'Ready for review' }).waitFor({ timeout: TIMEOUT })
  return { served, stop }
}

/** The page's status notice says `text`, and focus is on the page, not left on the body. */
async function expectAnnounced(page: Page, text: string): Promise<void> {
  await expect(toasts(page)).toContainText(text, { timeout: TIMEOUT })
  await expect
    .poll(() => page.evaluate(() => document.activeElement?.tagName), { timeout: TIMEOUT })
    .not.toBe('BODY')
}

/** A ticket's activity in the sample's main checkout. */
function activity(served: Served, id: string): string {
  const path = join(served.root, '.code-factory', 'tickets', id, 'activity.jsonl')
  return existsSync(path) ? readFileSync(path, 'utf8') : ''
}

test('e2e_a_permission_request_is_denied_from_the_inbox', async ({ page }) => {
  let request = ''
  const { served, stop } = await openInbox(page, (s) => {
    request = s.writeRequest('CF-7', 'rm -rf build')
  })
  const requests = page.getByRole('region', { name: 'Permission requests' })
  await requests.getByRole('button', { name: 'Deny' }).click()

  await expect(requests).toBeHidden({ timeout: TIMEOUT })
  await expectAnnounced(page, 'Denied Bash on CF-7')
  const answer = readFileSync(join(served.home, 'permissions', `${request}.answer`), 'utf8')
  expect(answer.trim()).toBe('deny')
  stop()
})

test('e2e_a_permission_request_is_allowed_from_the_inbox', async ({ page }) => {
  let request = ''
  const { served, stop } = await openInbox(page, (s) => {
    request = s.writeRequest('CF-7', 'rm -rf build')
  })
  const requests = page.getByRole('region', { name: 'Permission requests' })
  await requests.getByRole('button', { name: 'Allow' }).click()

  await expect(requests).toBeHidden({ timeout: TIMEOUT })
  await expectAnnounced(page, 'Allowed Bash on CF-7')
  const answer = readFileSync(join(served.home, 'permissions', `${request}.answer`), 'utf8')
  expect(answer.trim()).toBe('allow')
  stop()
})

test('e2e_a_rule_is_adopted_from_the_inbox', async ({ page }) => {
  const { served, stop } = await openInbox(page)
  const rules = page.getByRole('region', { name: 'Rules to adopt' })
  await rules.getByRole('button', { name: 'Always allow' }).click()

  await expect(rules).toBeHidden({ timeout: TIMEOUT })
  await expectAnnounced(page, 'Always allowing Bash uv run pytest')
  const adopted = readFileSync(join(served.home, 'permissions', 'rules.json'), 'utf8')
  expect(JSON.parse(adopted)).toContain('Bash uv run pytest')
  stop()
})

test('e2e_screens_are_approved_from_the_inbox', async ({ page }) => {
  const { served, stop } = await openInbox(page)
  const screens = page.getByRole('region', { name: 'Screens to approve' })
  await screens.getByRole('button', { name: 'Approve' }).click()

  await expect(screens).toBeHidden({ timeout: TIMEOUT })
  await expectAnnounced(page, 'Approved the screens of CF-9')
  expect(activity(served, 'CF-9')).toContain('"kind": "capture_approved"')
  stop()
})

test('e2e_screens_are_sent_back_from_the_inbox', async ({ page }) => {
  const { served, stop } = await openInbox(page)
  const screens = page.getByRole('region', { name: 'Screens to approve' })
  await screens.getByRole('button', { name: 'Request changes' }).click()
  const form = page.getByRole('form', { name: 'Request changes to CF-9' })
  await form.getByRole('textbox').fill('Too dark')
  await form.getByRole('button', { name: 'Send back' }).click()

  await expect(screens).toBeHidden({ timeout: TIMEOUT })
  const sent = activity(served, 'CF-9')
  expect(sent).toContain('"kind": "capture_changes"')
  expect(sent).toContain('Too dark')
  stop()
})

test('e2e_request_changes_takes_focus_and_cancel_gives_it_back', async ({ page }) => {
  const { stop } = await openInbox(page)
  const screens = page.getByRole('region', { name: 'Screens to approve' })
  const opener = screens.getByRole('button', { name: 'Request changes' })
  await opener.click()
  const form = page.getByRole('form', { name: 'Request changes to CF-9' })

  await expect(form.getByRole('textbox')).toBeFocused()
  await form.getByRole('button', { name: 'Cancel' }).click()

  await expect(form).toHaveCount(0)
  await expect(opener).toBeFocused()
  stop()
})

test('e2e_a_stopped_agent_is_restarted_from_the_inbox', async ({ page }) => {
  const { served, stop } = await openInbox(page)
  const runsOf = (id: string): number =>
    (
      JSON.parse(readFileSync(join(served.home, 'runs.json'), 'utf8')) as { ticket_id: string }[]
    ).filter((run) => run.ticket_id === id).length
  const before = runsOf('CF-7')
  await page
    .getByRole('region', { name: 'Stopped agents' })
    .getByRole('button', { name: 'Restart agent' })
    .click()

  await expect.poll(() => runsOf('CF-7'), { timeout: TIMEOUT }).toBe(before + 1)
  stop()
})

test('e2e_a_refused_merge_shows_its_reason_from_the_inbox', async ({ page }) => {
  // No test reaches GitHub: the board's gh is a stand-in that refuses.
  const bin = mkdtempSync(join(tmpdir(), 'code-factory-gh-'))
  writeFileSync(
    join(bin, 'gh'),
    '#!/bin/sh\ncase "$*" in *" --json baseRefName") echo \'{"baseRefName":"main"}\'; exit 0;; esac\necho "the stand-in gh refused" >&2\nexit 1\n',
  )
  chmodSync(join(bin, 'gh'), 0o755)
  const { stop } = await openInbox(page, () => undefined, {
    PATH: `${bin}:/usr/bin:/bin:/opt/homebrew/bin`,
  })
  const ready = page.getByRole('region', { name: 'Ready to merge' })
  await ready.getByRole('button', { name: 'Merge' }).click()

  // A refused merge leaves Ready to merge, so its reason shows in the page's notice (CF-539).
  await expect(toasts(page)).toContainText(
    'CF-12 pull request: GitHub refused the merge: the stand-in gh refused',
    { timeout: TIMEOUT },
  )
  await expect(ready).toBeHidden()
  stop()
})

test('e2e_a_failing_check_links_to_its_pull_request', async ({ page }) => {
  const { served, stop } = await openInbox(page)
  const pulls = JSON.parse(readFileSync(join(served.home, 'pull_requests.json'), 'utf8')) as Record<
    string,
    { url: string }
  >
  const wc13 = Object.entries(pulls).find(([key]) => key.endsWith('/CF-13'))?.[1]?.url
  const link = page
    .getByRole('region', { name: 'Failing checks' })
    .getByRole('link', { name: 'Open pull request' })

  expect(wc13).toMatch(/^https:/)
  await expect(link).toHaveAttribute('href', wc13 ?? '')
  stop()
})

// CF-1299: a failing check on a ticket that also holds a question is drawn by its question alone.
test('e2e_a_failing_check_is_not_drawn_for_a_ticket_that_holds_a_question', async ({
  page,
  served,
}) => {
  seedInbox(served, {
    ticket: 'CF-1',
    question: { text: 'Which colour?' },
    failingPull: 'https://github.com/o/r/pull/11',
  })
  seedInbox(served, { ticket: 'CF-2', failingPull: 'https://github.com/o/r/pull/13' })
  await page.goto(`${served.url}/inbox`)
  const failing = page.getByRole('region', { name: 'Failing checks' })

  await expect(page.getByRole('region', { name: 'Questions' })).toContainText('Which colour?')
  await expect(failing).toContainText('A bug in flight')
  await expect(failing).not.toContainText('Specs written')
})

test('e2e_a_question_s_choice_is_answered_from_the_inbox', async ({ page, served }) => {
  seedInbox(served, {
    ticket: 'CF-1',
    question: { text: 'Which colour?', choices: [{ text: 'Red' }, { text: 'Blue' }] },
  })
  await page.goto(`${served.url}/inbox`)
  const questions = page.getByRole('region', { name: 'Questions' })
  await questions.getByRole('radio', { name: 'Blue' }).check()
  await questions.getByRole('button', { name: 'Answer' }).click()

  await expect(questions).toBeHidden({ timeout: TIMEOUT })
  const ticket = await served.api('GET', '/api/tickets/sample/CF-1')
  expect(ticket.json).toMatchObject({ questions: [{ text: 'Which colour?', answer: 'Blue' }] })
})

// CF-1158-R3, R6: a request the board's policy escalated says why beside its ticket.
test('e2e_an_escalated_request_shows_why_in_the_inbox', async ({ page }) => {
  const why = "the board's policy refused 3 requests in a row: /etc/hosts is outside your worktree"
  const { stop } = await openInbox(page, (s) => {
    const id = s.writeRequest('CF-7', 'cat /etc/hosts')
    const path = join(s.home, 'permissions', `${id}.json`)
    const request = JSON.parse(readFileSync(path, 'utf8')) as Record<string, unknown>
    writeFileSync(path, JSON.stringify({ ...request, note: why }))
  })
  const requests = page.getByRole('region', { name: 'Permission requests' })

  await expect(requests.getByText(`· ${why}`)).toBeVisible({ timeout: TIMEOUT })
  stop()
})
