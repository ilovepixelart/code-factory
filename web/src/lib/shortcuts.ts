// The keyboard shortcuts, one registry: the shortcut sheet lists them by group, the command menu
// shows them beside the entry that does the same (an `id` names the ones it has an entry for), the
// app follows the `to` of a Go to key and a ticket presses the control its `target` names. A page's
// own keys are added here as a group of their own.

export type ShortcutGroup = 'Everywhere' | 'Go to' | 'Ticket' | 'Inbox'

export interface Shortcut {
  id?: string
  label: string
  keys: string[]
  group: ShortcutGroup
  /** A Go to key's page. */
  to?: string
  /** A ticket key's control, the element carrying `data-shortcut` of this name. */
  target?: string
}

/** The sheet's groups, in the order it lists them. */
export const GROUPS: ShortcutGroup[] = ['Everywhere', 'Go to', 'Ticket', 'Inbox']

const goTo = (id: string, name: string, key: string, to: string): Shortcut => ({
  id,
  label: `Go to ${name}`,
  keys: ['g', key],
  group: 'Go to',
  to,
})

export const SHORTCUTS: Shortcut[] = [
  { label: 'Command menu', keys: ['⌘', 'K'], group: 'Everywhere' },
  { label: 'Filter cards', keys: ['/'], group: 'Everywhere' },
  { id: 'new', label: 'New ticket', keys: ['n'], group: 'Everywhere' },
  { label: 'Toggle sidebar', keys: ['['], group: 'Everywhere' },
  { label: 'This sheet', keys: ['?'], group: 'Everywhere' },
  { label: 'Close a dialog or the ticket panel', keys: ['esc'], group: 'Everywhere' },
  goTo('sessions', 'Sessions', 's', '/'),
  goTo('tickets', 'Tickets', 't', '/tickets'),
  goTo('inbox', 'Inbox', 'i', '/inbox'),
  goTo('analytics', 'Analytics', 'a', '/analytics'),
  goTo('archive', 'Archive', 'r', '/archive'),
  goTo('memory', 'Memory', 'm', '/memory'),
  goTo('agents', 'Agents', 'g', '/agents'),
  goTo('team', 'Team', 'e', '/team'),
  { id: 'ticket-start', label: 'Start agent', keys: ['s'], group: 'Ticket', target: 'start' },
  { label: 'Run checks', keys: ['r'], group: 'Ticket', target: 'checks' },
  { label: 'Edit the title', keys: ['e'], group: 'Ticket', target: 'title' },
  { label: 'Next and previous item', keys: ['j', 'k'], group: 'Inbox' },
  { label: 'Pick that choice', keys: ['1', '…', '9'], group: 'Inbox' },
  { label: 'Accept the recommended choice', keys: ['a'], group: 'Inbox' },
  { label: 'Allow or deny a permission', keys: ['y', 'n'], group: 'Inbox' },
  { label: 'Open the item’s ticket', keys: ['enter'], group: 'Inbox' },
]

/** The keys of the shortcut `id`, none when the entry has no shortcut. */
export function keysOf(id: string): string[] {
  return SHORTCUTS.find((s) => s.id === id)?.keys ?? []
}

/** The page each key after `g` goes to. */
export const AFTER_G: Record<string, string> = Object.fromEntries(
  SHORTCUTS.flatMap((s) => (s.to && s.keys[1] ? [[s.keys[1], s.to]] : [])),
)

/** The control each ticket key presses, by its `data-shortcut` name. */
export const TICKET_KEYS: Record<string, string> = Object.fromEntries(
  SHORTCUTS.flatMap((s) =>
    s.group === 'Ticket' && s.target && s.keys[0] ? [[s.keys[0], s.target]] : [],
  ),
)
