import { RouterLinkStub } from '@vue/test-utils'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { form, view } from '../../../support/ticketForm'

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

describe('ticket links', () => {
  test('removing_a_link_names_it_in_the_path_and_sends_no_body', async () => {
    const shown = structuredClone(view) as { ticket: Record<string, unknown> }
    shown.ticket.blocked_by = 'CF-2'
    const { page, changes, bodies } = await form(shown)

    await page.get('[aria-label="Remove CF-2 from Blocked by"]').trigger('click')

    expect(changes).toEqual(['DELETE /api/tickets/sample/CF-1/links/blocked_by/CF-2'])
    expect(bodies).toEqual([null])
    page.unmount()
  })

  // A ticket of another repository has no stage the page knows: no empty badge stands for it.
  test('a_link_of_unknown_stage_draws_no_badge', async () => {
    const shown = structuredClone(view) as { ticket: Record<string, unknown> }
    shown.ticket.blocked_by = 'WEB-9'
    const { page } = await form(shown, true)

    const row = page.get('[aria-labelledby="links-heading"] dd ul[aria-label="Blocked by"]')
    expect(row.text()).toContain('WEB-9')
    expect(row.findAll('[data-slot="badge"]').filter((b) => b.text() === '')).toHaveLength(0)
    page.unmount()
  })

  test('a_link_to_another_repository_leads_there_with_its_title_and_stage', async () => {
    const shown = structuredClone(view) as {
      ticket: Record<string, unknown>
      linked: Record<string, unknown>
    }
    shown.ticket.blocked_by = 'CF-14'
    shown.linked = { 'CF-14': { repository: 'web', title: 'Show the balance', stage: 'build' } }
    const { page } = await form(shown, true)

    const row = page.get('[aria-labelledby="links-heading"] dd ul[aria-label="Blocked by"]')
    const link = row.getComponent(RouterLinkStub)
    expect(link.props('to')).toBe('/tickets/web/CF-14')
    expect(link.text()).toBe('CF-14Show the balanceBuild')
    page.unmount()
  })

  // A dd takes no group role (axe definition-list, aria-allowed-role): each kind's tickets are a list.
  test('each_kind_lists_its_tickets_as_list_items_inside_a_plain_dd', async () => {
    const shown = structuredClone(view) as { ticket: Record<string, unknown> }
    shown.ticket.blocked_by = 'CF-2'
    const { page } = await form(shown, true)

    const dds = page.findAll('[aria-labelledby="links-heading"] dl > dd')
    expect(dds.map((dd) => dd.attributes('role'))).toEqual(dds.map(() => undefined))
    const blocked = page.get('[aria-labelledby="links-heading"] dd > ul[aria-label="Blocked by"]')
    expect(blocked.findAll(':scope > li').map((li) => li.text())).toEqual([
      expect.stringContaining('CF-2'),
    ])
    page.unmount()
  })
})
