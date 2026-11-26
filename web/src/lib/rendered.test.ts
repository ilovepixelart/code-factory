// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import { defineComponent, h, withDirectives } from 'vue'
import { vRendered } from './rendered'

function rendered(html: string, top?: string) {
  const Doc = defineComponent({
    render: () => withDirectives(h('div', { class: 'typeset-doc' }), [[vRendered, html, top]]),
  })
  return mount(Doc)
}

// A table in a document scrolls inside its own frame on a narrow screen instead of pushing the
// page sideways: it sits in typeset's `typeset-scroll` wrapper.
test('a_rendered_table_sits_in_the_typeset_scroll_wrapper', () => {
  const view = rendered('<p>Intro</p><table><tr><th>ID</th></tr></table><p>After</p>')

  const table = view.get('table')
  expect(table.element.parentElement?.classList.contains('typeset-scroll')).toBe(true)
  expect(view.findAll('.typeset-scroll')).toHaveLength(1)
  expect(view.text()).toContain('Intro')
  view.unmount()
})

// Headings still drop under the section that shows the text.
test('the_text_h1_takes_the_level_the_directive_names', () => {
  const view = rendered('<h1>Title</h1>', '3')

  expect(view.find('h3').text()).toBe('Title')
  view.unmount()
})
