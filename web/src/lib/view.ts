// What the board shows of the view model under the address's settings: filters, lanes, the
// list's order and the card search.

import { PRIORITIES, STAGES, type Board, type Card, type FilterGroup, type Column } from './board'

const GROUPS: FilterGroup[] = ['type', 'priority', 'label', 'assignee', 'repository']
const FLAGS = ['blocked', 'questions', 'agent'] as const
export type Pairs = [string, string][]

/** The query's pairs in order, blank values kept. */
export function pairsOf(search: string): Pairs {
  return [...new URLSearchParams(search).entries()]
}

/** A URL path with the pairs as its query. */
export function urlOf(path: string, pairs: Pairs): string {
  const query = new URLSearchParams(pairs).toString()
  return query ? `${path}?${query}` : path
}

/** The filter pairs alone: the groups and flags, values present. */
export function filterPairs(pairs: Pairs): Pairs {
  const known = new Set<string>([...GROUPS, ...FLAGS])
  return pairs.filter(([key, value]) => known.has(key) && value !== '')
}

/** How many values and flags are chosen. */
export function filterCount(pairs: Pairs): number {
  const groups = new Set<string>(GROUPS)
  const chosen = filterPairs(pairs)
  const flags = new Set(chosen.filter(([key]) => !groups.has(key)).map(([key]) => key))
  return chosen.filter(([key]) => groups.has(key)).length + flags.size
}

/** Whether a card passes every group and flag; values in a group widen, groups narrow. */
function matches(card: Card, pairs: Pairs): boolean {
  const chosen = filterPairs(pairs)
  const values = (key: string) => chosen.filter(([k]) => k === key).map(([, v]) => v)
  const group = (key: FilterGroup, own: string[]) => {
    const wanted = values(key)
    return wanted.length === 0 || own.some((value) => wanted.includes(value))
  }
  return (
    group('type', [card.type]) &&
    group('priority', [card.priority]) &&
    group('label', card.labels) &&
    group('assignee', [card.assignee]) &&
    group('repository', [card.repository]) &&
    (values('blocked').length === 0 || card.blocked !== '') &&
    (values('agent').length === 0 || card.runs.length > 0) &&
    (values('questions').length === 0 || card.open_questions > 0)
  )
}

/** The pairs with one pair removed when present, else appended; order kept. */
export function toggled(pairs: Pairs, key: string, value: string): Pairs {
  const present = pairs.some(([k, v]) => k === key && v === value)
  return present ? pairs.filter(([k, v]) => !(k === key && v === value)) : [...pairs, [key, value]]
}

/** The text the card search reads: what the card shows. */
function searchText(card: Card): string {
  return [
    card.id,
    card.parent,
    card.type,
    card.priority,
    card.title,
    card.blocked,
    ...card.labels,
    card.repository,
    card.branch,
    card.assignee,
  ]
    .join(' ')
    .toLowerCase()
}

/** Whether a card shows under the search box's text. */
function found(card: Card, needle: string): boolean {
  const text = needle.trim().toLowerCase()
  return text === '' || searchText(card).includes(text)
}

/** Every column with only the cards that pass the filter and the search. */
export function shown(board: Board, pairs: Pairs, needle: string): Record<Column, Card[]> {
  return Object.fromEntries(
    STAGES.map((stage) => [
      stage,
      board.columns[stage].filter((c) => matches(c, pairs) && found(c, needle)),
    ]),
  ) as Record<Column, Card[]>
}

const UNASSIGNED = 'Unassigned'
export type Lanes = '' | 'repository' | 'assignee'

function laneOf(card: Card, lanes: Exclude<Lanes, ''>): string {
  return lanes === 'repository' ? card.repository : card.assignee || UNASSIGNED
}

/** The columns split into lanes, Unassigned last; every lane has every stage. */
export function groupLanes(
  columns: Record<Column, Card[]>,
  lanes: Exclude<Lanes, ''>,
): [string, Record<Column, Card[]>][] {
  const names = [...new Set(STAGES.flatMap((s) => columns[s].map((c) => laneOf(c, lanes))))]
  names.sort(
    (a, b) =>
      Number(a === UNASSIGNED) - Number(b === UNASSIGNED) ||
      compareText(a.toLowerCase(), b.toLowerCase()),
  )
  return names.map((name) => [
    name,
    Object.fromEntries(
      STAGES.map((s) => [s, columns[s].filter((c) => laneOf(c, lanes) === name)]),
    ) as Record<Column, Card[]>,
  ])
}

/** Text order by code point, not by locale. */
function compareText(a: string, b: string): number {
  if (a < b) return -1
  return a > b ? 1 : 0
}

/** CF-2 before CF-10: digit runs compare by value. */
function compareNatural(a: string, b: string): number {
  const parts = (id: string) => id.split(/(\d+)/)
  const [left, right] = [parts(a), parts(b)]
  for (let i = 0; i < Math.min(left.length, right.length); i++) {
    const [x = '', y = ''] = [left[i], right[i]]
    const order =
      i % 2 === 1
        ? Number(BigInt(x) > BigInt(y)) - Number(BigInt(x) < BigInt(y))
        : compareText(x, y)
    if (order !== 0) return order
  }
  return left.length - right.length
}

export const SORTS = ['id', 'title', 'type', 'stage', 'priority', 'assignee', 'repository'] as const
export type Sort = (typeof SORTS)[number]

function sortKey(card: Card, sort: Sort): string | number {
  switch (sort) {
    case 'title':
      return card.title.toLowerCase()
    case 'type':
      return card.type
    case 'stage':
      return STAGES.indexOf(card.stage as Column)
    case 'priority': {
      const at = (PRIORITIES as readonly string[]).indexOf(card.priority)
      return at < 0 ? PRIORITIES.length : at
    }
    case 'assignee':
      return card.assignee.toLowerCase()
    case 'repository':
      return card.repository
    default:
      return card.id
  }
}

/** The list's rows ordered by a column, ascending unless `desc`; else in board order. */
export function sortCards(cards: Card[], sort: string, direction: string): Card[] {
  if (!(SORTS as readonly string[]).includes(sort)) return [...cards]
  const by = sort as Sort
  // A descending sort keeps equal rows in their order: flip the comparison, not the result.
  const sign = direction === 'desc' ? -1 : 1
  return [...cards].sort((a, b) => {
    if (by === 'id') return sign * compareNatural(a.id, b.id)
    const [x, y] = [sortKey(a, by), sortKey(b, by)]
    return (
      sign *
      (typeof x === 'number' && typeof y === 'number' ? x - y : compareText(String(x), String(y)))
    )
  })
}
