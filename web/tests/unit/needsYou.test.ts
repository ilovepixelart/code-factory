// One word for one thing: "Needs you" names only what is in the Inbox, whose count the sidebar
// shows, so no other page counts something else under it.

import { readdirSync, readFileSync } from 'node:fs'
import { join, relative } from 'node:path'
import { expect, test } from 'vitest'

const SRC = join(import.meta.dirname, '../../src')
const INBOX = ['components/inbox/', 'pages/InboxPage.vue']

function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) return sources(path)
    return /\.(vue|ts)$/.test(entry.name) && !entry.name.endsWith('.test.ts') ? [path] : []
  })
}

test('needs_you_is_said_only_of_the_inbox', () => {
  const sayers = sources(SRC)
    .filter((path) => /needs you/i.test(readFileSync(path, 'utf8')))
    .map((path) => relative(SRC, path))

  expect(sayers.filter((path) => !INBOX.some((inbox) => path.startsWith(inbox)))).toEqual([])
  expect(sayers.some((path) => INBOX.some((inbox) => path.startsWith(inbox)))).toBe(true)
})
