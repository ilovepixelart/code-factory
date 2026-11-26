// @vitest-environment happy-dom

import { afterEach, describe, expect, test, vi } from 'vitest'
import { present } from '../../test/present'
import { form, view } from '../../test/ticketForm'

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

describe('the documents', () => {
  const documented = {
    ...(view as object),
    documents: [
      { stage: 'requirements', html: '<p>The problem.</p>' },
      { stage: 'mock', html: '<p>The board.</p>', files: ['board.png', 'notes.html'] },
      { stage: 'spec', html: '<p>The design.</p>' },
      { stage: 'uat', html: null },
    ],
  }

  // CF-835-R3: the Mock tab shows mock.md, then each image under mock/ drawn from the board's route
  // and each other file by its name.
  test('the_mock_tab_shows_its_drawing_and_files', async () => {
    const { page } = await form(documented)
    const tab = present(
      page.findAll('[role="tab"]').find((t) => t.text() === 'Mock'),
      'the Mock tab',
    )
    await tab.trigger('mousedown', { button: 0 })

    const panel = present(
      page.findAll('[role="tabpanel"]').find((p) => p.text().includes('The board.')),
      'the mock panel',
    )
    const images = panel.findAll('img').map((i) => [i.attributes('src'), i.attributes('alt')])

    expect(images).toEqual([['/api/tickets/sample/CF-1/mock/board.png', 'board.png']])
    expect(panel.text()).toContain('notes.html')
  })

  // CF-1206: only the documents written get a tab; none reads "(missing)".
  test('only_written_documents_get_a_tab', async () => {
    const { page } = await form(documented)

    const labels = page.findAll('[role="tab"]').map((t) => t.text())

    expect(labels.filter((l) => /Requirements|Mock|Spec|UAT/.test(l))).toEqual([
      'Requirements',
      'Mock',
      'Spec',
    ])
    expect(page.text()).not.toContain('missing')
  })

  // CF-1206: a document not written is offered under Add a document, with the file it lives in.
  test('a_missing_document_is_offered_to_add', async () => {
    const { page } = await form(documented)

    const add = page.find('[aria-label="Add a document"]')

    expect(add.text()).toContain('UAT')
    expect(add.text()).toContain('.code-factory/tickets/CF-1/uat.md')
    expect(add.text()).not.toContain('Spec')
  })

  // CF-1206: with every document written there is nothing to add.
  test('no_add_a_document_when_all_are_written', async () => {
    const all = {
      ...(view as object),
      documents: [{ stage: 'spec', html: '<p>The design.</p>' }],
    }
    const { page } = await form(all)

    expect(page.find('[aria-label="Add a document"]').exists()).toBe(false)
  })
})
