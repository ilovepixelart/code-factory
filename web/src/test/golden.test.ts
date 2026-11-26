import { mkdtempSync, readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { blessing, expectGolden, layout } from './golden'

const GOLDEN = '{\n  "keep": "x",\n  "value": 1\n}\n'

/** A scratch golden holding GOLDEN. */
function scratch(): string {
  const path = join(mkdtempSync(join(tmpdir(), 'golden-')), 'case.golden.json')
  writeFileSync(path, GOLDEN)
  return path
}

describe('the web holds its goldens as CODE_FACTORY_BLESS says', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  // CF-844-R9: only `1` blesses; absent, `0`, `true` and empty compare.
  test('only_the_value_1_blesses', () => {
    const seen = [undefined, '0', 'true', '', '1'].map((value) => {
      vi.stubEnv('CODE_FACTORY_BLESS', value)
      return blessing()
    })

    expect(seen).toStrictEqual([false, false, false, false, true])
  })

  // CF-844-R9: blessing writes what the test produced, in the layout worked by hand.
  test('blessing_writes_the_golden', () => {
    const path = scratch()

    expectGolden(path, { keep: 'x', value: 2 }, true)

    expect(readFileSync(path, 'utf8')).toBe('{\n  "keep": "x",\n  "value": 2\n}\n')
  })

  // CF-844-R9: comparing, a difference fails and the golden's bytes stay as they were.
  test('comparing_fails_and_writes_nothing', () => {
    const path = scratch()

    expect(() => {
      expectGolden(path, { keep: 'x', value: 2 }, false)
    }).toThrow(/case\.golden\.json differs/)
    expect(readFileSync(path, 'utf8')).toBe(GOLDEN)
  })

  // CF-844-R4: a golden whose value equals what the test produced is not written.
  test('an_equal_golden_is_not_written', () => {
    const path = scratch()
    writeFileSync(path, '{"value":1,"keep":"x"}')

    expectGolden(path, { keep: 'x', value: 1 }, true)

    expect(readFileSync(path, 'utf8')).toBe('{"value":1,"keep":"x"}')
  })

  // CF-844-R5: every web golden is in the layout blessing writes, so blessing an unchanged tree
  // writes nothing.
  test('every_web_golden_is_in_the_layout_blessing_writes', () => {
    const folder = join(import.meta.dirname, '../../../tests/golden/formats/display')
    const goldens = readdirSync(folder).filter((name) => name.endsWith('.golden.json'))

    expect(goldens.length).toBeGreaterThan(0)
    for (const name of goldens) {
      const text = readFileSync(join(folder, name), 'utf8')
      expect(layout(JSON.parse(text)), name).toBe(text)
    }
  })
})
