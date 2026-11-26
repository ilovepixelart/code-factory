// CF-1292: only a pull request address of GitHub becomes a link, shown as `#<number>`; every other
// address, and every other shape of github.com, stays the text it is.

import { expect, test } from 'vitest'
import { textParts } from './addresses'

const PULL = 'https://github.com/owner/repo/pull/1185'

test('a_pull_request_address_is_a_link_with_its_number', () => {
  expect(textParts(`Pull request opened (${PULL})`)).toEqual([
    { text: 'Pull request opened (', href: null },
    { text: '#1185', href: PULL },
    { text: ')', href: null },
  ])
})

test('a_github_address_that_is_no_pull_request_stays_text', () => {
  for (const address of [
    'https://github.com/owner/repo',
    'https://github.com/owner/repo/issues/9',
    'https://github.com/owner/repo/pull/9/files',
    'https://github.com/owner/repo/pull/abc',
    'https://github.com/x',
  ]) {
    expect(textParts(`See ${address}`), address).toEqual([{ text: `See ${address}`, href: null }])
  }
})

test('an_address_off_github_or_off_https_stays_text', () => {
  for (const address of [
    'https://github.com.evil.test/owner/repo/pull/1',
    'http://github.com/owner/repo/pull/1',
    'https://example.test/owner/repo/pull/1',
  ]) {
    expect(textParts(`Opened (${address})`).filter((part) => part.href)).toEqual([])
  }
})

test('two_pull_requests_in_one_sentence_are_two_links', () => {
  const other = 'https://github.com/owner/repo/pull/2'

  expect(textParts(`${PULL} and ${other}`).map((part) => part.text)).toEqual([
    '#1185',
    ' and ',
    '#2',
  ])
})
