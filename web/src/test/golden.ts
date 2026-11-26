// The web's golden comparisons (CF-844): a test holds what it produced to a committed JSON file,
// and `CODE_FACTORY_BLESS=1` makes it write what it produced there instead.

import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { isDeepStrictEqual } from 'node:util'
import { expect } from 'vitest'

/** Whether golden comparisons write what the tests produced: only `CODE_FACTORY_BLESS=1` does. */
export const blessing = (): boolean => process.env.CODE_FACTORY_BLESS === '1'

/** The text blessing writes: JSON with two spaces and one trailing newline. */
export const layout = (value: unknown): string => `${JSON.stringify(value, null, 2)}\n`

/**
 * Hold the JSON golden at `path` to `produced`. Blessing writes `produced` there when its value
 * differs and asserts what was written; comparing fails on a difference and writes nothing.
 */
export function expectGolden(path: string, produced: unknown, bless = blessing()): void {
  const golden: unknown = existsSync(path) ? JSON.parse(readFileSync(path, 'utf8')) : undefined
  if (!bless) {
    expect(
      golden,
      `${path} differs; CODE_FACTORY_BLESS=1 writes it, then read the diff`,
    ).toStrictEqual(produced)
    return
  }
  if (!isDeepStrictEqual(golden, produced)) {
    writeFileSync(path, layout(produced))
  }
  expect(JSON.parse(readFileSync(path, 'utf8'))).toStrictEqual(produced)
}
