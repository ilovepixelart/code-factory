import { beforeEach, expect, test } from 'vitest'
import { build, freshLoad, noteBuild, resetBuild } from './build'

beforeEach(resetBuild)

test('the_same_build_named_again_leaves_the_tab_current', () => {
  noteBuild('aa11')
  noteBuild('aa11')
  expect(build.stale).toBe(false)
  expect(freshLoad('/tickets')).toBeNull()
})

test('a_different_build_makes_the_next_navigation_a_full_load_of_its_target', () => {
  noteBuild('aa11')
  noteBuild('bb22')
  expect(build.stale).toBe(true)
  expect(freshLoad('/tickets/sample/CF-1?tab=x')).toBe('/tickets/sample/CF-1?tab=x')
})

test('an_answer_naming_no_build_changes_nothing', () => {
  noteBuild('aa11')
  noteBuild(null)
  noteBuild('')
  expect(build.stale).toBe(false)
})

test('a_tab_that_never_heard_a_build_is_not_stale', () => {
  noteBuild(null)
  noteBuild('bb22')
  expect(build.stale).toBe(false)
})
