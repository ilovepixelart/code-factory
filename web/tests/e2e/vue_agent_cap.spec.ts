// CF-407 acceptance flow: a claude run's tokens reach the board while it works, through the
// telemetry address the board gives each run, so its card's meter moves and the run is stopped at
// its cap. The stand-in for claude reports its model requests as claude's OpenTelemetry export
// does: an OTLP JSON `claude_code.api_request` event, tagged with the run, to the logs endpoint,
// with the run's token in the header its logs export is given.

import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { TIMEOUT, expect, serve, test } from './fixtures'

/**
 * How long the follower may take to stop a run at its cap once its tokens are recorded: it passes
 * within 2 s of a change, but a change that lands during a pass waits for the next one at its
 * floor of 30 s (`FLOOR`, the follower pass minimum), and that pass takes seconds
 * on a loaded machine.
 */
// The follower's 30 s floor plus TIMEOUT, written as one number for the wait-limit guard.
const HALTED = 40_000

/** A stand-in that reports one request, waits for `go`, reports a second, then works on. */
function standIn(folder: string, go: string): string {
  const event = JSON.stringify({
    resourceLogs: [
      {
        resource: { attributes: [{ key: 'code-factory.run', value: { stringValue: 'RUN' } }] },
        scopeLogs: [
          {
            logRecords: [
              {
                body: { stringValue: 'claude_code.api_request' },
                attributes: [
                  { key: 'input_tokens', value: { intValue: 500_000 } },
                  { key: 'output_tokens', value: { intValue: 100_000 } },
                ],
              },
            ],
          },
        ],
      },
    ],
  })
  const script = join(folder, 'claude.sh')
  writeFileSync(
    script,
    [
      `run=$(printf '%s' "$OTEL_RESOURCE_ATTRIBUTES" | tr ',' '\\n' | sed -n 's/^code-factory[.]run=//p')`,
      `body=$(printf '%s' '${event}' | sed "s/RUN/$run/")`,
      `token=$(printf '%s' "$OTEL_EXPORTER_OTLP_LOGS_HEADERS" | sed -n 's/^x-code-factory-token=//p')`,
      // The board refuses (401) a report that lands before it has recorded the run it just
      // spawned, and nothing resends it: retry until it is accepted, as an exporter does.
      `report() { until curl -sf -o /dev/null -H 'content-type: application/json' -H "x-code-factory-token: $token" --data "$body" "$OTEL_EXPORTER_OTLP_LOGS_ENDPOINT"; do sleep 0.2; done; }`,
      'report',
      `while [ ! -e '${go}' ]; do sleep 0.2; done`,
      'report',
      'sleep 60',
      '',
    ].join('\n'),
  )
  return `sh ${script}`
}

test('e2e_a_claude_runs_tokens_move_on_its_card', async ({ page }) => {
  test.setTimeout(60_000 + HALTED)
  const folder = mkdtempSync(join(tmpdir(), 'code-factory-cap-'))
  const go = join(folder, 'go')
  const { served, stop } = await serve('writes', standIn(folder, go))
  writeFileSync(
    join(served.home, 'agents.json'),
    JSON.stringify([
      {
        name: 'writer',
        runtime: 'claude',
        roles: ['spec'],
        max_tokens: 1_000_000,
        max_seconds: 3600,
      },
    ]),
  )
  try {
    await page.goto(`${served.url}/tickets/sample/CF-2`)
    const agent = page.getByRole('region', { name: /^Agent/ })
    await agent.getByRole('button', { name: 'Start agent' }).click()
    await agent.getByText('Iteration 1 on Spec').waitFor({ timeout: TIMEOUT })
    await page.goto(`${served.url}/agents`)
    const writer = page.getByRole('listitem', { name: 'writer' })

    await expect(writer.getByRole('meter', { name: 'writer tokens' })).toHaveText(
      '600 k of 1 M tokens',
      { timeout: TIMEOUT },
    )
    await expect(writer.getByText('claude reports tokens when its run ends')).toHaveCount(0)
    const runs = () =>
      (
        JSON.parse(readFileSync(join(served.home, 'runs.json'), 'utf8')) as {
          agent?: string
          log: string
          halted: string
          tokens: number | null
        }[]
      ).filter((r) => r.agent === 'writer')
    // The request events the board recorded for the run, one line each beside its log.
    const reported = () =>
      runs().map(
        (r) =>
          readFileSync(r.log.replace(/\.log$/, '.usage'), 'utf8')
            .trim()
            .split('\n').length,
      )
    const writers = () => runs().map((r) => [r.halted, r.tokens])
    writeFileSync(go, '')
    await expect.poll(reported, { timeout: TIMEOUT }).toStrictEqual([2])
    // CF-820-R1: the follower stops the run and records why on a pass; the card then reads it.
    await expect
      .poll(writers, { timeout: HALTED })
      .toStrictEqual([['stopped at its cap: writer 1,200,000 of 1,000,000 tokens', 1_200_000]])
    await expect(writer).toContainText('over limit', { timeout: TIMEOUT })
  } finally {
    await page.request.post(`${served.url}/api/agents/stop`)
    stop()
    writeFileSync(go, '')
  }
})
