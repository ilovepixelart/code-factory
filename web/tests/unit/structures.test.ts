// CF-1277: a menu is shadcn-vue's DropdownMenu or Popover, a switch between views its Tabs or
// ToggleGroup, a disclosure its Collapsible and a table its Table. A `.vue` file holds no dropdown or
// popover class, no tab class or tab role, no radio drawn as a button, no `<details>` and no
// `<table>` of its own unless it is on a list below with the reason it cannot move yet
// (docs/design.md, The rules the tests hold). Each list only shrinks: a listed file
// that no longer offends fails the test.

import { describe, expect, test } from 'vitest'
import { offenders, verdict, vueFiles, openingTags, type Tag } from '../support/guard'

const classes = (tag: Tag): string[] =>
  [...tag.text.matchAll(/(?:^|\s):?class="([^"]*)"/g)].flatMap((m) => (m[1] ?? '').split(/[^\w-]+/))

const menu = (tag: Tag): boolean =>
  classes(tag).some((c) => c === 'popover' || c === 'dropdown' || c.startsWith('dropdown-'))
const tabbed = (tag: Tag): boolean =>
  classes(tag).some((c) => c === 'tabs' || c === 'tab' || /^tabs?-/.test(c)) ||
  /\srole="tab(list)?"/.test(tag.text)
const radioButton = (tag: Tag): boolean =>
  tag.name === 'input' && /\stype="radio"/.test(tag.text) && classes(tag).includes('join-item')
const disclosure = (tag: Tag): boolean => tag.name === 'details'
const table = (tag: Tag): boolean => tag.name === 'table'
// ARIA allows an article no listitem role (axe aria-allowed-role): a list's item is a `div` with it.
const articleListItem = (tag: Tag): boolean =>
  (tag.name === 'article' || /\sas="article"/.test(tag.text)) && /\srole="listitem"/.test(tag.text)

const ALLOWED_DETAILS: Record<string, string> = {
  'components/MemoryEntry.vue':
    'a record row: the summary holds the statement and its badges, the details its why and actions',
}
// A data table is the shared DataTable on TanStack Table (docs/design.md); shadcn-vue's Table
// directly only where sorting, paging and a Columns menu could add nothing.
const shadcnTable = (tag: Tag): boolean => tag.name === 'Table'
// A page's grid of sections has one track that may shrink below its widest child: without
// grid-cols-1 the track grows to that child's width, and on a phone every section scrolls
// sideways with it.
const shrinklessPageGrid = (tag: Tag): boolean => {
  const names = classes(tag)
  return names.includes('page-wide') && names.includes('grid') && !names.includes('grid-cols-1')
}
const DATA_TABLE = ['components/data-table/DataTable.vue']
const ALLOWED_PLAIN_TABLES: Record<string, string> = {
  'components/factory/CostTables.vue':
    'two fixed aggregates of four rows each, in an order that means something',
  'components/ScorersSection.vue': 'one row per configured scorer, a handful at most',
  'pages/design/DesignComponents.vue': 'the design page shows shadcn-vue Table itself',
}
const ALLOWED_TABLES: Record<string, string> = {
  'components/TicketChanges.vue':
    'a diff, one row per line with a line number and a mark, with no `table` class and no header',
}

// shadcn-vue's own components, as its CLI wrote them.
const UI = vueFiles().filter((file) => file.startsWith('components/ui/'))

const OWNERS = {
  menu: UI,
  tabbed: UI,
  disclosure: UI,
  table: UI,
}

describe('the structures are written through their shared components', () => {
  const files = vueFiles()

  test('a_menu_is_a_dropdown_menu_or_a_popover', () => {
    expect(files.length).toBeGreaterThan(50)
    expect(verdict(offenders(files, menu, OWNERS.menu), {})).toEqual([])
  })

  test('a_switch_between_views_is_tabs_or_a_toggle_group', () => {
    expect(verdict(offenders(files, tabbed, OWNERS.tabbed), {})).toEqual([])
  })

  test('a_radio_drawn_as_a_button_is_a_toggle_group', () => {
    expect(verdict(offenders(files, radioButton, OWNERS.tabbed), {})).toEqual([])
  })

  test('a_disclosure_is_a_Collapsible', () => {
    expect(verdict(offenders(files, disclosure, OWNERS.disclosure), ALLOWED_DETAILS)).toEqual([])
  })

  test('a_table_is_a_shadcn_Table', () => {
    expect(verdict(offenders(files, table, OWNERS.table), ALLOWED_TABLES)).toEqual([])
  })

  test('a_page_grid_lets_its_track_shrink_to_the_screen', () => {
    expect(verdict(offenders(files, shrinklessPageGrid), {})).toEqual([])
  })

  test('a_list_item_is_not_an_article', () => {
    expect(verdict(offenders(files, articleListItem), {})).toEqual([])
  })

  test('a_data_table_is_the_shared_DataTable', () => {
    expect(
      verdict(offenders(files, shadcnTable, [...UI, ...DATA_TABLE]), ALLOWED_PLAIN_TABLES),
    ).toEqual([])
  })
})

describe('the rules', () => {
  const tags = (source: string): Tag[] => openingTags(`<template>${source}</template>`).slice(1)
  const hits = (rule: (tag: Tag) => boolean, source: string): number =>
    tags(source).filter(rule).length

  test('the_menu_rule_flags_dropdown_and_popover_classes_only', () => {
    expect(hits(menu, '<details class="dropdown dropdown-end">')).toBe(1)
    expect(hits(menu, '<ul class="x popover w-56">')).toBe(1)
    expect(hits(menu, '<ul :class="{ \'popover\': open }">')).toBe(1)
    expect(hits(menu, '<ul class="popovers dropdownish">')).toBe(0)
    expect(hits(menu, '<div data-popover="x" aria-label="dropdown">')).toBe(0)
  })

  test('the_tab_rule_flags_tab_classes_and_roles_but_not_a_tab_query_or_a_tab_panel', () => {
    expect(hits(tabbed, '<div class="tabs tabs-border">')).toBe(1)
    expect(hits(tabbed, '<input class="tab" />')).toBe(1)
    expect(hits(tabbed, '<div class="tab-content">')).toBe(1)
    expect(hits(tabbed, '<div role="tablist">')).toBe(1)
    expect(hits(tabbed, '<button role="tab">')).toBe(1)
    expect(hits(tabbed, '<a to="/agents?tab=connections" data-tab="write" tabindex="-1">')).toBe(0)
    expect(hits(tabbed, '<div role="tabpanel" class="stable tabular-nums">')).toBe(0)
  })

  test('the_radio_rule_flags_only_a_radio_drawn_as_a_joined_button', () => {
    expect(hits(radioButton, '<input type="radio" class="btn join-item">')).toBe(1)
    expect(hits(radioButton, '<input type="radio" class="radio">')).toBe(0)
    expect(hits(radioButton, '<input type="checkbox" class="join-item">')).toBe(0)
    expect(hits(radioButton, '<a class="join-item">')).toBe(0)
  })

  test('the_page_grid_rule_flags_only_a_page_grid_without_one_shrinking_track', () => {
    expect(hits(shrinklessPageGrid, '<div class="page-wide grid gap-6">')).toBe(1)
    expect(hits(shrinklessPageGrid, '<div class="page-wide grid grid-cols-1 gap-6">')).toBe(0)
    expect(hits(shrinklessPageGrid, '<div class="page-wide flex gap-6">')).toBe(0)
    expect(hits(shrinklessPageGrid, '<div class="grid gap-6">')).toBe(0)
  })

  test('the_list_item_rule_flags_only_an_article_with_the_listitem_role', () => {
    expect(hits(articleListItem, '<Item as="article" role="listitem" size="sm">')).toBe(1)
    expect(hits(articleListItem, '<article role="listitem">')).toBe(1)
    expect(hits(articleListItem, '<Item role="listitem" size="sm">')).toBe(0)
    expect(hits(articleListItem, '<Item as="article" size="sm">')).toBe(0)
  })

  test('the_disclosure_and_table_rules_flag_the_bare_elements', () => {
    expect(hits(disclosure, '<details open>')).toBe(1)
    expect(hits(disclosure, '<Collapsible>')).toBe(0)
    expect(hits(table, '<table class="x">')).toBe(1)
    expect(hits(table, '<Table>')).toBe(0)
  })
})
