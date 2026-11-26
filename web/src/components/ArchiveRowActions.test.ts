// @vitest-environment happy-dom
// An archived row's Restore and Delete share the row's busy state: the one pressed shows a
// Spinner while the row is sent, disabled with the other.

import { mount } from '@vue/test-utils'
import { describe, expect, test } from 'vitest'
import ArchiveRowActions from './ArchiveRowActions.vue'

const actions = (busy: boolean) =>
  mount(ArchiveRowActions, { props: { id: 'CF-7', archived: true, busy } })

const button = (view: ReturnType<typeof actions>, name: string) =>
  view.get(`[aria-label="${name}"]`)

describe('an archived row being sent', () => {
  test('the_pressed_button_shows_a_spinner_and_both_are_disabled', async () => {
    const view = actions(false)

    await button(view, 'Restore CF-7').trigger('click')
    await view.setProps({ busy: true })

    expect(button(view, 'Restore CF-7').find('[role="status"]').exists()).toBe(true)
    expect(button(view, 'Delete CF-7').find('[role="status"]').exists()).toBe(false)
    expect(
      ['Restore CF-7', 'Delete CF-7'].map((name) => button(view, name).attributes('disabled')),
    ).toEqual(['', ''])
    expect(view.emitted('restore')).toHaveLength(1)
  })

  test('no_spinner_shows_once_the_row_is_sent', async () => {
    const view = actions(false)
    await button(view, 'Delete CF-7').trigger('click')
    await view.setProps({ busy: true })

    await view.setProps({ busy: false })

    expect(view.find('[role="status"]').exists()).toBe(false)
    expect(view.emitted('remove')).toHaveLength(1)
  })
})
