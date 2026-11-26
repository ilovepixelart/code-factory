// Every read the app keeps, named once: the key TanStack Query caches it under and, for a read
// that is polled, how often. A change invalidates by these keys; a channel that pushes changes
// can turn a poll off here and invalidate or set the same keys instead.

/** The cache key of each read. A key's first part is its family: invalidating `['sessions']`
 *  reaches every session list and every session's timeline. */
export const keys = {
  board: ['board'] as const,
  /** The repositories tickets can be filed in: tracked ones and those tickets name. */
  repositories: ['repositories'] as const,
  inboxCount: ['inbox', 'count'] as const,
  inbox: ['inbox', 'items'] as const,
  sessions: (address: string) => ['sessions', 'list', address] as const,
  sessionUsage: (where: string) => ['sessions', 'usage', where] as const,
  /** One timeline a session: how many entries it asks for is read inside its read. */
  session: (id: string) => ['sessions', 'timeline', id] as const,
  agents: ['agents', 'list'] as const,
  harnesses: ['agents', 'harnesses'] as const,
  connections: ['agents', 'connections'] as const,
  claudeAgents: ['agents', 'claude'] as const,
  scorers: ['agents', 'scorers'] as const,
  team: ['team'] as const,
  halt: ['agents', 'halt'] as const,
  memory: (address: string) => ['memory', address] as const,
  preview: (path: string) => ['preview', path] as const,
  ticket: (repository: string, id: string) => ['tickets', repository, id] as const,
  /** Under the ticket's key, so invalidating a ticket reaches its findings too. */
  findings: (repository: string, id: string) => ['tickets', repository, id, 'findings'] as const,
  factory: (path: string) => ['factory', path] as const,
  flow: (range: string) => ['flow', range] as const,
  archive: (address: string) => ['archive', address] as const,
}

/** Milliseconds between the reads of each polled query; `false` would stop that poll. */
export const POLL = {
  board: 3000,
  inboxCount: 5000,
  inbox: 5000,
  sessions: 3000,
  session: 3000,
  agents: 3000,
  team: 3000,
  preview: 5000,
  ticket: 5000,
} as const satisfies Record<string, number | false>
