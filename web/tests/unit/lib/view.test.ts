import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, test } from 'vitest'
import { STAGES, type Board } from '@/lib/board'
import { groupLanes, pairsOf, shown, sortCards, type Lanes } from '@/lib/view'

const GOLDENS = join(import.meta.dirname, '../../../../tests/support/golden/formats')

interface View {
  columns: Record<string, string[]>
  lanes: [string, Record<string, string[]>][] | null
  rows: string[]
}

const golden = JSON.parse(readFileSync(join(GOLDENS, 'api/board.golden.json'), 'utf8')) as Board & {
  views: Record<string, View>
}

describe('the board under each address', () => {
  test('board_views_match_the_goldens', () => {
    const queries = Object.keys(golden.views)
    expect(queries.length).toBeGreaterThan(20)
    for (const query of queries) {
      const expected = golden.views[query]
      const pairs = pairsOf(query)
      const settings = Object.fromEntries(pairs)
      const columns = shown(golden, pairs, '')
      const ids = Object.fromEntries(STAGES.map((s) => [s, columns[s].map((c) => c.id)]))
      expect(ids, query).toEqual(expected?.columns)
      const lanes = settings.lanes as Lanes | undefined
      const grouped =
        lanes === 'repository' || lanes === 'assignee'
          ? groupLanes(columns, lanes).map(([name, cells]) => [
              name,
              Object.fromEntries(STAGES.map((s) => [s, cells[s].map((c) => c.id)])),
            ])
          : null
      expect(grouped, query).toEqual(expected?.lanes)
      const rows = sortCards(
        STAGES.flatMap((s) => columns[s]),
        settings.sort ?? '',
        settings.dir ?? '',
      )
      expect(
        rows.map((c) => c.id),
        query,
      ).toEqual(expected?.rows)
    }
  })
})
