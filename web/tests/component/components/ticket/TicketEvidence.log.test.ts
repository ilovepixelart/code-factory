// CF-1229: a failed check's output shows its failing lines and folds the whole output behind a
// closed disclosure.

import { afterEach, expect, test, vi } from 'vitest'
import { form, view } from '../../../support/ticketForm'

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

const LOG = [
  '        PASS [   0.016s] code-factory-infra tests::a_failed_current_exe_refuses',
  '        PASS [   0.010s] code-factory-core tests::refuses_on_fail',
  '    failures:',
  '        FAIL [   0.022s] code-factory-infra serving::tests::a_socket_is_handed_over',
  "    thread 'serving::tests::a_socket_is_handed_over' panicked at src/serving.rs:297:83:",
  'warning: 16/372 tests were not run due to test failure',
  'error: test run failed',
  'gate: rust-test failed (exit 100) after 9s',
].join('\n')

async function evidence(log: string) {
  const { page } = await form({
    ...(view as object),
    current_stage: 'build',
    check: { at: '', commit: 'abc1234', exit_code: 1, log: '/checks/a.log', tree: '' },
    check_log: log,
  })
  const failing = page.find('[aria-label="Failing lines"]')
  const whole = page.get('[aria-label="Checks output"]')
  const fold = whole.element.closest('[data-slot="trace-collapsible"]')
  const read = {
    failing: failing.exists() ? failing.element.textContent : null,
    whole: whole.element.textContent,
    folded: fold !== null && fold.getAttribute('data-state') === 'closed',
    summary: fold?.querySelector('[data-slot="trace-collapsible-trigger"]')?.textContent.trim(),
  }
  page.unmount()
  return read
}

test('the_failing_lines_show_and_the_whole_output_is_folded', async () => {
  expect(await evidence(LOG)).toEqual({
    failing: [
      '        FAIL [   0.022s] code-factory-infra serving::tests::a_socket_is_handed_over',
      "    thread 'serving::tests::a_socket_is_handed_over' panicked at src/serving.rs:297:83:",
      'error: test run failed',
      'gate: rust-test failed (exit 100) after 9s',
    ].join('\n'),
    whole: LOG,
    folded: true,
    summary: 'Whole output, 8 lines',
  })
})

test('an_output_naming_no_failure_shows_its_last_line', async () => {
  const read = await evidence('line 1\nline 2\nline 3')

  expect([read.failing, read.summary]).toEqual(['line 3', 'Whole output, 3 lines'])
})
