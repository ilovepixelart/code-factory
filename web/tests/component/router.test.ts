// CF-318: a page chunk that fails to load (a tab opened before an upgrade) loads the address
// afresh, once; any other routing error does not.

import { afterEach, describe, expect, test, vi } from 'vitest'
import { clear, notice } from '@/lib/notice'
import { PAGES, reloadForStaleChunk, router } from '@/router'
import { ANALYTICS_TABS } from '@/lib/analytics'
import { Analytics01Icon } from '@hugeicons/core-free-icons'

afterEach(() => {
  vi.restoreAllMocks()
  sessionStorage.clear()
  clear()
})

describe('a page chunk the build no longer has', () => {
  test('a_missing_page_chunk_reloads_its_address_once', () => {
    const assign = vi.spyOn(window.location, 'assign').mockImplementation(() => undefined)
    const chrome = new TypeError(
      'Failed to fetch dynamically imported module: http://localhost:4000/assets/FlowPage-OLD.js',
    )
    const safari = new TypeError('Importing a module script failed.')

    reloadForStaleChunk(chrome, { fullPath: '/flow' })
    reloadForStaleChunk(chrome, { fullPath: '/flow' })
    reloadForStaleChunk(safari, { fullPath: '/inbox' })
    reloadForStaleChunk(new Error('navigation cancelled'), { fullPath: '/memory' })

    expect(assign.mock.calls).toEqual([['/flow'], ['/inbox']])
  })

  test('a_page_chunk_still_missing_after_its_reload_says_the_board_was_updated', () => {
    const assign = vi.spyOn(window.location, 'assign').mockImplementation(() => undefined)
    const chrome = new TypeError(
      'Failed to fetch dynamically imported module: http://localhost:4000/assets/FlowPage-OLD.js',
    )

    reloadForStaleChunk(chrome, { fullPath: '/flow' })
    expect(notice.text).toBe('')
    reloadForStaleChunk(chrome, { fullPath: '/flow' })

    expect(assign.mock.calls).toEqual([['/flow']])
    expect(notice).toMatchObject({
      text: 'The board was updated; reload the page to see it.',
      error: true,
    })
  })
})

// Flow and the four Factory pages sit under one sidebar entry, Analytics, each with its own address.
describe('the Analytics pages', () => {
  test('the_sidebar_has_one_Analytics_entry_and_no_Flow_or_Factory_entry', () => {
    const names = PAGES.map((page) => page.name)

    expect(PAGES.find((page) => page.path === '/analytics')).toStrictEqual({
      path: '/analytics',
      name: 'Analytics',
      icon: Analytics01Icon,
    })
    expect(names.filter((name) => name === 'Analytics')).toHaveLength(1)
    expect(names.some((name) => ['Flow', 'Factory'].includes(name))).toBe(false)
  })

  test.each([
    ['/analytics', 'Flow'],
    ['/analytics/factory', 'Factory'],
    ['/analytics/scorers', 'Scorers'],
  ])('the_address_%s_is_the_page_titled_%s', (path, title) => {
    const found = router.resolve(path)

    expect(found.meta.title).toBe(title)
    expect(found.matched).toHaveLength(1)
  })

  test.each([
    ['/flow?range=30d#agents-heading', '/analytics?range=30d#agents-heading'],
    ['/factory', '/analytics/factory'],
    ['/factory?range=7d', '/analytics/factory?range=7d'],
    ['/factory/scorers', '/analytics/scorers'],
    // Benchmarks and Self-improvement are hidden until the evals that feed them exist.
    ['/factory/self-improvement', '/analytics'],
    ['/analytics/benchmarks?range=30d', '/analytics?range=30d'],
    ['/analytics/self-improvement', '/analytics'],
  ])('the_old_address_%s_leads_to_%s', async (old, now) => {
    await router.push(old)

    expect(router.currentRoute.value.fullPath).toBe(now)
  })

  test('the_analytics_switch_offers_no_tab_whose_evals_do_not_exist_yet', () => {
    expect(ANALYTICS_TABS.map(([, name]) => name)).toEqual(['Flow', 'Factory', 'Scorers'])
  })
})
