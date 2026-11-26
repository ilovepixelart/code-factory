// @vitest-environment happy-dom
// CF-364: docs/ui.md (The kanban), a ticket with a branch shows its Changes: the branch against
// its default branch, at most 400 lines, and each kept or added line has a comment form of its
// own whose comment names the file and line.

import { flushPromises, mount, type DOMWrapper, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { clear, notice } from '../lib/notice'
import type { TicketChanges as Changes } from '../lib/ticket'
import { answer, stubFetch } from '../test/board'
import { present } from '../test/present'
import TicketChanges from './TicketChanges.vue'

const CHANGES: Changes = {
  files: [
    {
      path: 'src/app.ts',
      lines: [
        { kind: 'kept', number: 1, text: 'import x' },
        { kind: 'removed', number: null, text: 'old()' },
        { kind: 'added', number: 2, text: 'fresh()' },
      ],
    },
    { path: '', lines: [{ kind: 'removed', number: null, text: 'gone' }] },
  ],
  cut: false,
  limit: 400,
  branch: 'feature/CF-9',
  default_branch: 'main',
}

function changesOf(
  diff: (url: string) => Response | Promise<Response> = () => answer(CHANGES),
  comment: () => Response | Promise<Response> = () => answer({ notice: 'Comment added' }),
) {
  return stubFetch((url, init) => (init?.method === 'POST' ? comment() : diff(url)))
}

async function shown(props: {
  repository: string
  id: string
  revision: number
  merged?: boolean
}) {
  const wrapper = mount(TicketChanges, { props, attachTo: document.body })
  await flushPromises()
  return wrapper
}

const SAMPLE = { repository: 'sample', id: 'CF-9', revision: 1 }
const hint = (wrapper: VueWrapper) => wrapper.get('[data-slot="section-description"]').text()
const triggerName = (d: DOMWrapper<Element>) =>
  d.element.querySelector('[data-slot="collapsible-trigger"]')?.getAttribute('aria-label')
const form = (wrapper: VueWrapper, line: number) =>
  present(
    wrapper
      .findAll('table [data-slot="collapsible"]')
      .find((d) => triggerName(d) === `Comment on src/app.ts line ${String(line)}`),
    `the form for line ${String(line)}`,
  )

afterEach(() => {
  vi.unstubAllGlobals()
  clear()
  document.body.innerHTML = ''
})

describe('the changes', () => {
  test('the_changes_are_read_for_the_ticket_named_in_the_address_percent_encoded', async () => {
    const sent = changesOf()

    await shown({ repository: 'r#x', id: 'CF 9', revision: 1 })

    expect(sent.map((s) => s.url)).toEqual(['/api/tickets/r%23x/CF%209/diff'])
  })

  test('the_header_counts_the_files_and_names_both_branches', async () => {
    changesOf()
    const wrapper = await shown(SAMPLE)

    expect(wrapper.get('h2').text()).toBe('Changes, 2')
    expect(hint(wrapper)).toBe('files, feature/CF-9 against main')
  })

  test('one_file_is_counted_as_a_file', async () => {
    changesOf(() => answer({ ...CHANGES, files: CHANGES.files.slice(0, 1) }))
    const wrapper = await shown(SAMPLE)

    expect(hint(wrapper)).toBe('file, feature/CF-9 against main')
  })

  test('a_cut_diff_says_where_it_was_cut', async () => {
    changesOf(() => answer({ ...CHANGES, cut: true }))
    const wrapper = await shown(SAMPLE)

    expect(hint(wrapper)).toBe('files, feature/CF-9 against main, cut at 400 lines')
  })

  test('each_line_shows_its_number_mark_and_text', async () => {
    changesOf()
    const wrapper = await shown(SAMPLE)
    const rows = wrapper
      .get('table[aria-label="src/app.ts"]')
      .findAll('tr')
      .map((tr) => {
        const [number, mark, text] = tr.findAll('td')
        return [
          number?.text(),
          mark?.attributes('aria-label'),
          mark?.text(),
          text?.get('span').text(),
        ]
      })

    expect(rows).toEqual([
      ['1', 'kept', '', 'import x'],
      ['', 'removed', '-', 'old()'],
      ['2', 'added', '+', 'fresh()'],
    ])
  })

  test('a_removed_file_is_named_as_such', async () => {
    changesOf()
    const wrapper = await shown(SAMPLE)

    expect(wrapper.findAll('h3').map((h) => h.text())).toEqual(['src/app.ts', 'a removed file'])
  })

  test('the_changed_files_show_as_a_folder_tree_that_leads_to_each_diff', async () => {
    changesOf()
    const wrapper = await shown(SAMPLE)
    const tree = wrapper.get('nav[aria-label="Changed files"]')

    const names = tree.findAll('button').map((b) => b.text())
    await present(
      tree.findAll('button').find((b) => b.text() === 'app.ts'),
      'the file app.ts',
    ).trigger('click')

    expect(names).toEqual(['src', 'app.ts', 'a removed file'])
    expect(document.activeElement?.querySelector('h3')?.textContent.trim()).toBe('src/app.ts')
    wrapper.unmount()
  })

  test('only_kept_and_added_lines_take_a_comment', async () => {
    changesOf()
    const wrapper = await shown(SAMPLE)

    expect(
      wrapper
        .findAll('table [data-slot="collapsible-trigger"]')
        .map((s) => s.attributes('aria-label')),
    ).toEqual(['Comment on src/app.ts line 1', 'Comment on src/app.ts line 2'])
  })

  test('a_line_comment_button_is_an_icon_that_adds_no_text_to_the_diff', async () => {
    changesOf()
    const wrapper = await shown(SAMPLE)

    const triggers = wrapper.findAll('table [data-slot="collapsible-trigger"]')
    expect(triggers.map((t) => t.text())).toEqual(['', ''])
    expect(triggers.every((t) => t.find('svg').exists())).toBe(true)
  })

  test('a_branch_without_changes_says_so', async () => {
    changesOf(() => answer({ ...CHANGES, files: [] }))
    const wrapper = await shown(SAMPLE)

    expect(wrapper.text()).toContain('No changes on feature/CF-9 yet.')
  })

  test('a_merged_branch_without_changes_says_it_is_merged', async () => {
    changesOf(() => answer({ ...CHANGES, files: [] }))
    const wrapper = await shown({ ...SAMPLE, merged: true })

    expect(wrapper.text()).toContain('feature/CF-9 is merged into main.')
    expect(wrapper.text()).not.toContain('yet')
  })

  test('a_ticket_the_board_does_not_know_shows_no_changes', async () => {
    changesOf(() => answer({ detail: 'no such ticket' }, 404))
    const wrapper = await shown(SAMPLE)

    expect(wrapper.find('#changes').exists()).toBe(false)
  })

  test('a_new_revision_reads_the_changes_again', async () => {
    let files = CHANGES.files.slice(0, 1)
    const sent = changesOf(() => answer({ ...CHANGES, files }))
    const wrapper = await shown(SAMPLE)

    files = CHANGES.files
    await wrapper.setProps({ revision: 2 })
    await flushPromises()

    expect(sent).toHaveLength(2)
    expect(wrapper.get('h2').text()).toBe('Changes, 2')
  })

  test('an_answer_for_a_ticket_no_longer_shown_is_dropped', async () => {
    let late: (response: Response) => void = () => undefined
    changesOf((url) =>
      url.includes('/CF-1/')
        ? new Promise<Response>((resolve) => (late = resolve))
        : answer({ ...CHANGES, branch: 'feature/CF-2' }),
    )
    const wrapper = mount(TicketChanges, { props: { ...SAMPLE, id: 'CF-1' } })

    await wrapper.setProps({ id: 'CF-2' })
    await flushPromises()
    late(answer({ ...CHANGES, branch: 'feature/CF-1' }))
    await flushPromises()

    expect(hint(wrapper)).toBe('files, feature/CF-2 against main')
  })
})

describe('commenting on a line', () => {
  test('a_comment_names_its_file_and_line_and_the_form_empties_and_closes', async () => {
    const sent = changesOf()
    const wrapper = await shown(SAMPLE)
    const details = form(wrapper, 2)
    await details.get('[data-slot="collapsible-trigger"]').trigger('click')

    await details.get('textarea').setValue('Name this better')
    await details.get('form').trigger('submit')
    await flushPromises()

    expect(sent.filter((s) => s.method === 'POST')).toEqual([
      {
        method: 'POST',
        url: '/api/tickets/sample/CF-9/comments',
        body: { text: 'Name this better', path: 'src/app.ts', line: 2 },
      },
    ])
    expect((details.get('textarea').element as HTMLTextAreaElement).value).toBe('')
    expect(details.attributes('data-state')).toBe('closed')
    expect(wrapper.emitted('commented')).toHaveLength(1)
  })

  test('a_refused_comment_keeps_its_text_and_form_and_shows_why', async () => {
    changesOf(undefined, () => answer({ detail: 'the ticket is archived' }, 409))
    const wrapper = await shown(SAMPLE)
    const details = form(wrapper, 1)
    await details.get('[data-slot="collapsible-trigger"]').trigger('click')

    await details.get('textarea').setValue('Keep me')
    await details.get('form').trigger('submit')
    await flushPromises()

    expect((details.get('textarea').element as HTMLTextAreaElement).value).toBe('Keep me')
    expect(details.attributes('data-state')).toBe('open')
    expect(notice.text).toBe('the ticket is archived')
  })

  test('only_the_line_being_sent_has_its_send_disabled', async () => {
    let reply: (response: Response) => void = () => undefined
    changesOf(undefined, () => new Promise<Response>((resolve) => (reply = resolve)))
    const wrapper = await shown(SAMPLE)

    await form(wrapper, 2).get('textarea').setValue('Busy')
    await form(wrapper, 2).get('form').trigger('submit')
    const during = [1, 2].map((line) =>
      form(wrapper, line).get('button[type="submit"]').attributes('disabled'),
    )
    reply(answer({ notice: '' }))
    await flushPromises()

    expect(during).toEqual([undefined, ''])
    expect(form(wrapper, 2).get('button[type="submit"]').attributes('disabled')).toBeUndefined()
  })
})
