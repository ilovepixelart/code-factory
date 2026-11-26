// CF-551: a board a test starts and never stops ends with `stopAll`, which runs when the test's
// worker exits. CF-816: it also ends when the worker's end of its standard input closes, as it
// does when the worker is killed.

import { dropSample, expect, prepareSample, present, start, stopAll, test } from './fixtures'

test('a board a test never stopped ends with stopAll', async ({ request }) => {
  const schema = prepareSample('empty')
  const { url } = await start(schema)
  expect((await request.get(`${url}/`)).status()).toBe(200)

  stopAll()

  await expect
    .poll(async () => {
      try {
        await request.get(`${url}/`)
        return 'answers'
      } catch {
        return 'gone'
      }
    })
    .toBe('gone')
  dropSample(schema)
})

// CF-816-R2
test('a board a test starts stops when its standard input closes', async ({ request }) => {
  const schema = prepareSample('empty')
  const { url, server } = await start(schema)
  expect((await request.get(`${url}/`)).status()).toBe(200)

  // The worker holds the pipe's write end: an input of /dev/null would end at once.
  present(server.stdin, "the board's standard input").end()

  await expect.poll(() => server.exitCode).toBe(0)
  await expect
    .poll(async () => {
      try {
        await request.get(`${url}/`)
        return 'answers'
      } catch {
        return 'gone'
      }
    })
    .toBe('gone')
  stopAll()
  dropSample(schema)
})
