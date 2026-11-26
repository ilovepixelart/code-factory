// The Analytics pages: Flow, then the four Factory pages, under one item of the sidebar, and the
// one range every one of them reads, kept in the address as each tab is chosen.
export const FLOW = '/analytics'

/** Tabs hidden until the evals that feed them exist, so the app offers no tab that can only say
 *  it is not available: their addresses lead to Flow (`router.ts`). Empty the list to show them. */
const HIDDEN_TABS: readonly string[] = ['/analytics/benchmarks', '/analytics/self-improvement']

/** Whether the tab at `path` is shown. */
export const shownTab = (path: string): boolean => !HIDDEN_TABS.includes(path)

export const ANALYTICS_TABS = (
  [
    [FLOW, 'Flow'],
    ['/analytics/factory', 'Factory'],
    ['/analytics/scorers', 'Scorers'],
    ['/analytics/benchmarks', 'Benchmarks'],
    ['/analytics/self-improvement', 'Self-improvement'],
  ] as const
).filter(([path]) => shownTab(path))

export const RANGES = [
  ['24h', '24 hours'],
  ['7d', '7 days'],
  ['30d', '30 days'],
  ['90d', '90 days'],
] as const
export type RangeKey = (typeof RANGES)[number][0]
const DEFAULT_RANGE: RangeKey = '7d'
/** Whole days a range covers, for the pages that read by date. */
export const RANGE_DAYS: Record<RangeKey, number> = { '24h': 1, '7d': 7, '30d': 30, '90d': 90 }

/** The range an address names; anything but one of the four reads as the default. */
export function rangeOf(asked: unknown): RangeKey {
  return RANGES.find(([key]) => key === asked)?.[0] ?? DEFAULT_RANGE
}

/** The address query that names `range`: none for the default. */
export function rangeQuery(range: RangeKey): Record<string, string> {
  return range === DEFAULT_RANGE ? {} : { range }
}
