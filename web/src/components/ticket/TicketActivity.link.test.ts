// @vitest-environment happy-dom
// CF-1229, CF-1292: an activity sentence's pull request address on GitHub is a link opening in a new
// tab, drawn as `#<number>`; any other address, and any markup, stays text.

import { afterEach, expect, test, vi } from 'vitest'
import { form, view } from '../../test/ticketForm'

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

const PULL = 'https://github.com/owner/repo/pull/1078'

async function entry(sentence: string) {
  const { page } = await form({
    ...(view as object),
    activity: [{ at: 0, sentence, kind: 'pull_request', text: '' }],
  })
  const item = page.get('[aria-label="Activity"] li')
  const links = item.findAll('a').map((a) => ({
    text: a.text(),
    href: a.attributes('href'),
    target: a.attributes('target'),
    rel: a.attributes('rel'),
  }))
  const text = item.text()
  page.unmount()
  return { links, text }
}

test('a_pull_request_address_in_a_sentence_is_a_short_link', async () => {
  const { links, text } = await entry(`Pull request opened (${PULL})`)

  expect(links).toEqual([
    { text: '#1078', href: PULL, target: '_blank', rel: 'noopener noreferrer' },
  ])
  expect(text).toContain('Pull request opened (#1078)')
  expect(text).not.toContain('github.com')
})

test('an_address_off_github_or_off_https_stays_text', async () => {
  for (const address of [
    'https://example.test/pull/20',
    'http://github.com/owner/repo/pull/1',
    'https://github.com.evil.test/owner/repo',
    'javascript:alert(1)',
  ]) {
    const { links, text } = await entry(`Pull request opened (${address})`)

    expect(links).toEqual([])
    expect(text).toContain(address)
  }
})

test('markup_in_a_sentence_stays_text_and_only_a_pull_request_links', async () => {
  const { links, text } = await entry(
    `Commented <a href="https://github.com/x">here</a> on ${PULL}`,
  )

  expect(links.map((l) => [l.text, l.href])).toEqual([['#1078', PULL]])
  expect(text).toContain('Commented <a href="https://github.com/x">here</a>')
})
