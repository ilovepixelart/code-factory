import { mount } from '@vue/test-utils'
import { afterEach, expect, test } from 'vitest'
import { defineComponent, h } from 'vue'
import { useReturnFocus } from '@/lib/returnFocus'

const Form = {
  setup() {
    useReturnFocus()
    return () => h('input')
  },
}

const Host = defineComponent({
  props: { open: Boolean },
  setup: (props) => () => h('div', [h('button', 'Open'), props.open ? h(Form) : null]),
})

afterEach(() => {
  document.body.innerHTML = ''
})

function opened() {
  const page = mount(Host, { attachTo: document.body })
  const button = page.get('button')
  ;(button.element as HTMLElement).focus()
  return { page, button }
}

test('closing_a_form_returns_the_keyboard_to_the_button_that_opened_it', async () => {
  const { page, button } = opened()
  await page.setProps({ open: true })
  ;(page.get('input').element as HTMLElement).focus()

  await page.setProps({ open: false })

  expect(document.activeElement).toBe(button.element)
  page.unmount()
})

test('a_form_closing_leaves_focus_where_it_was_moved_meanwhile', async () => {
  const { page } = opened()
  await page.setProps({ open: true })
  const elsewhere = document.createElement('a')
  elsewhere.href = '#'
  document.body.append(elsewhere)
  elsewhere.focus()

  await page.setProps({ open: false })

  expect(document.activeElement).toBe(elsewhere)
  page.unmount()
})

test('a_form_opened_with_no_focused_control_takes_none_back', async () => {
  const page = mount(Host, { attachTo: document.body })
  await page.setProps({ open: true })

  await page.setProps({ open: false })

  expect(document.activeElement).toBe(document.body)
  page.unmount()
})

test('an_opener_that_left_the_page_is_not_focused', async () => {
  const { page, button } = opened()
  await page.setProps({ open: true })
  button.element.remove()

  await page.setProps({ open: false })

  expect(document.activeElement).toBe(document.body)
  page.unmount()
})
