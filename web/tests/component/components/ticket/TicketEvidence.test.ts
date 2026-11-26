import { afterEach, expect, test, vi } from 'vitest'
import { form, view } from '../../../support/ticketForm'

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

const unchecked = (current_stage: string) => ({
  ...(view as object),
  current_stage,
  check: null,
  checks_configured: false,
})

// CF-1081-R1: a Spec ticket of a repository with no checks command shows no checks row.
test('a_spec_ticket_shows_no_checks_notice', async () => {
  const { page } = await form(unchecked('spec'))

  expect(page.find('[aria-label="Checks"]').exists()).toBe(false)
  expect(page.text()).not.toContain('No checks command')
  page.unmount()
})

// CF-1081-R1: from Build on, the row and its words show.
test('a_build_ticket_keeps_the_checks_notice', async () => {
  const { page } = await form(unchecked('build'))

  expect(page.find('[aria-label="Checks"]').text()).toContain('No checks command')
  page.unmount()
})

// CF-1081-R2, CF-1089-R1: the stage left to the evidence names the stage, in words its panel fits.
test('the_stage_says_which_stage_the_evidence_holds', async () => {
  const { page } = await form({ ...unchecked('spec'), stage: '' })

  const stage = page.find('select[id$="-stage"]')
  expect(stage.find('option[value=""]').text()).toBe('Spec (auto)')
  page.unmount()
})

// CF-1089-R2
test('the_stage_says_who_sets_it', async () => {
  const { page } = await form({ ...unchecked('spec'), stage: '' })

  expect(page.find('select[id$="-stage"]').attributes('title')).toBe(
    "Set by the board from the ticket's evidence",
  )
  expect(page.find('select[id$="-type"]').attributes('title')).toBeUndefined()
  page.unmount()
})

const nothing = { gate: null, verdict: '', capture: null, not_proven: [] }
const gate = { held: true, commit: '1a2b3c4d5e', tree: '5d6e7f8' }
const check = { exit_code: 0, commit: '1a2b3c4d5e' }
const summary = (page: Awaited<ReturnType<typeof form>>['page']) =>
  page.find('[aria-label="Evidence summary"]')

// CF-1087-R1
test('a_merged_ticket_without_a_check_shows_no_checks_row', async () => {
  const { page } = await form({ ...unchecked('merged'), summary: nothing })

  expect(page.find('[aria-label="Checks"]').exists()).toBe(false)
  page.unmount()
})

// CF-1087-R1
test('a_merged_ticket_keeps_its_recorded_check', async () => {
  const { page } = await form({ ...unchecked('merged'), check, summary: nothing })

  expect(page.find('[aria-label="Checks"]').text()).toContain('Checks passed on 1a2b3c4')
  page.unmount()
})

// CF-1087-R2
test('a_merged_ticket_without_records_shows_no_summary', async () => {
  const { page } = await form({ ...unchecked('released'), summary: nothing })

  expect(summary(page).exists()).toBe(false)
  page.unmount()
})

// CF-1087-R2
test('a_merged_ticket_keeps_a_recorded_gate', async () => {
  const { page } = await form({ ...unchecked('merged'), summary: { ...nothing, gate } })

  expect(summary(page).text()).toContain('Gate passed on 1a2b3c4, tree 5d6e7f8')
  page.unmount()
})

// CF-1087-R3
test('a_review_ticket_keeps_its_summary', async () => {
  const { page } = await form({ ...unchecked('review'), summary: nothing })

  expect(summary(page).text()).toContain('Gate not run')
  page.unmount()
})

// CF-1087-R3
test('a_build_ticket_shows_no_summary_even_with_a_gate', async () => {
  const { page } = await form({ ...unchecked('build'), summary: { ...nothing, gate } })

  expect(summary(page).exists()).toBe(false)
  page.unmount()
})

const checklist = [
  { stage: 'spec', required: true, present: true, detail: 'a branch' },
  { stage: 'build', required: true, present: false, detail: 'a commit' },
]

// CF-1206: the strip of steps and the folded list of where the board looks repeat the column and
// Status; the checks stay under their own heading.
test('the_evidence_strip_and_its_fold_are_gone', async () => {
  const { page } = await form({ ...unchecked('build'), checklist })

  expect(page.find('[aria-label="Evidence steps"]').exists()).toBe(false)
  expect(page.find('[aria-label="Evidence checklist"]').exists()).toBe(false)
  expect(page.text()).not.toContain('Where the board looks')
  expect(page.find('#checklist-heading').text()).toBe('Checks')
  page.unmount()
})
