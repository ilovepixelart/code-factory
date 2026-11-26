import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { runInThisContext } from 'node:vm'
import { afterEach, describe, expect, test, vi } from 'vitest'

// public/theme-early.js runs before paint: dark mode is the `dark` class on <html> alone, from the
// saved choice, else from the OS preference.
const SCRIPT = readFileSync(join(import.meta.dirname, '../../public/theme-early.js'), 'utf8')
const html = document.documentElement

function runWith(saved: string | null, prefersDark: boolean): void {
  html.className = ''
  delete html.dataset.theme
  localStorage.clear()
  if (saved) localStorage.setItem('codeFactoryTheme', saved)
  vi.stubGlobal('matchMedia', () => ({ matches: prefersDark }))
  runInThisContext(SCRIPT)
}

afterEach(() => {
  vi.unstubAllGlobals()
  html.className = ''
})

describe('the theme before paint', () => {
  test('a_saved_dark_theme_sets_the_dark_class_over_a_light_preference', () => {
    runWith('dark', false)

    expect([html.classList.contains('dark'), html.dataset.theme]).toEqual([true, undefined])
  })

  test('a_saved_light_theme_leaves_the_dark_class_off_over_a_dark_preference', () => {
    runWith('light', true)

    expect([html.classList.contains('dark'), html.dataset.theme]).toEqual([false, undefined])
  })

  test('with_nothing_saved_the_os_preference_decides', () => {
    runWith(null, true)
    const dark = html.classList.contains('dark')
    runWith(null, false)

    expect([dark, html.classList.contains('dark')]).toEqual([true, false])
  })
})
