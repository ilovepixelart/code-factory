// CF-1274: a button is shadcn-vue's Button (components/ui), a sidebar entry its SidebarMenuButton. A `.vue` file
// holds no `<button` tag and no `btn` class of its own unless it is on the list below with the
// reason it cannot move yet (docs/design.md, The rules the tests hold).

import { expect, test } from 'vitest'
import {
  offenders,
  openingTags,
  readVue,
  vueFiles,
  verdict,
  withParents,
  type Tag,
} from '../support/guard'

const UI = vueFiles().filter((file) => file.startsWith('components/ui/'))
const OWNERS = UI

const ALLOWED: Record<string, string> = {
  'components/BoardColumn.vue': 'the column heading is a text toggle with no button look',
}

const hand = (tag: Tag): boolean => tag.name === 'button' || /(?<![\w-])btn\b/.test(tag.text)

test('buttons_are_written_through_the_shared_components', () => {
  const files = vueFiles()
  const found = offenders(files, hand, OWNERS)

  expect(files.length).toBeGreaterThan(50)
  expect(verdict(found, ALLOWED)).toEqual([])
})

// shadcn-vue's icon button: a `size` of `icon`, `icon-xs`, `icon-sm` or `icon-lg`.
const iconOnly = (tag: Tag): boolean =>
  tag.name === 'Button' && /\ssize="icon(?:-(?:xs|sm|lg))?"/.test(tag.text)
const unnamed = (tag: Tag): boolean => iconOnly(tag) && !/(?<![\w-]):?aria-label=/.test(tag.text)

// shadcn-vue's own close buttons are named by a `sr-only` span, as its CLI wrote them.
test('an_icon_button_carries_an_aria_label', () => {
  const tags = vueFiles()
    .filter((file) => !UI.includes(file))
    .flatMap((file) =>
      openingTags(readVue(file))
        .filter(iconOnly)
        .map((tag) => ({ file, tag })),
    )

  expect(tags.length).toBeGreaterThan(5)
  expect(
    tags.filter(({ tag }) => unnamed(tag)).map(({ file, tag }) => `${file}:${String(tag.line)}`),
  ).toEqual([])
})

test('the_icon_rule_flags_an_icon_only_button_with_no_name_and_nothing_else', () => {
  const tag = (text: string): Tag => ({ name: 'Button', text, line: 1 })

  expect(unnamed(tag('<Button size="icon">'))).toBe(true)
  expect(unnamed(tag('<Button variant="ghost" size="icon-xs"\n @click="x">'))).toBe(true)
  expect(unnamed(tag('<Button size="icon" aria-label="Close">'))).toBe(false)
  expect(unnamed(tag('<Button size="icon-sm" :aria-label="`Open ${id}`">'))).toBe(false)
  expect(unnamed(tag('<Button>'))).toBe(false)
  expect(unnamed(tag('<Button size="xs" data-size="icon">'))).toBe(false)
})

test('the_guard_reads_a_tag_across_lines_and_through_a_quoted_greater_than', () => {
  const source = [
    '<template>',
    '  <button',
    '    type="button"',
    '    class="btn"',
    '    @click="x => go(x)"',
    '  >',
    '  </button>',
    '  <div class="surface"></div>',
    '</template>',
  ].join('\n')
  const tags = openingTags(source)

  expect(tags.map((t) => [t.name, t.line])).toEqual([
    ['template', 1],
    ['button', 2],
    ['div', 8],
  ])
  expect(tags.filter(hand).map((t) => t.name)).toEqual(['button'])
})

test('the_guard_ignores_the_script_and_flags_a_btn_class_on_any_tag', () => {
  const source =
    '<script setup>\nconst a = "<button class=\'btn\'>"\n</script>\n<summary class="btn btn-ghost">'
  const tags = openingTags(source)

  expect(tags.map((t) => t.name)).toEqual(['summary'])
  expect(tags.filter(hand).map((t) => t.line)).toEqual([4])
  expect(hand({ name: 'span', text: '<span class="button-like">', line: 1 })).toBe(false)
})

test('the_list_fails_for_a_new_offender_and_for_a_file_that_no_longer_offends', () => {
  const found = new Map([['a.vue', ['a.vue:3 <button>']]])

  expect(verdict(found, {})).toEqual(['not allowed: a.vue:3 <button>'])
  expect(verdict(found, { 'a.vue': 'why' })).toEqual([])
  expect(verdict(new Map(), { 'a.vue': 'why' })).toEqual([
    'no longer offends, remove it from the list: a.vue (why)',
  ])
})

// shadcn-vue's Button sets no `type`, so one in a form submits it: a Button that does not submit
// says `type="button"`. One rendered through `as-child`, or the child of a `*Trigger as-child`,
// is not a <button> of its own or takes the trigger's `type="button"`.
const untyped = (tag: Tag & { parent: string }, parentAsChild: boolean): boolean =>
  tag.name === 'Button' &&
  !/\sas-child\b/.test(tag.text) &&
  !/(?<![\w-]):?type=/.test(tag.text) &&
  !(parentAsChild && tag.parent.endsWith('Trigger'))

function untypedIn(source: string): number[] {
  const tags = withParents(source)
  return tags
    .filter((tag, at) => {
      const parent = tags
        .slice(0, at)
        .reverse()
        .find((t) => t.name === tag.parent)
      return untyped(tag, parent !== undefined && /\sas-child\b/.test(parent.text))
    })
    .map((tag) => tag.line)
}

test('a_button_that_does_not_submit_says_type_button', () => {
  const found = vueFiles()
    .filter((file) => !UI.includes(file))
    .flatMap((file) => untypedIn(readVue(file)).map((line) => `${file}:${String(line)}`))

  expect(found).toEqual([])
})

test('the_type_rule_flags_an_untyped_button_and_passes_a_typed_or_triggered_one', () => {
  const source = [
    '<template>',
    '  <Button variant="ghost" @click="x">A</Button>',
    '  <Button type="button">B</Button>',
    '  <Button :type="kind">C</Button>',
    '  <Button as-child><a href="/">D</a></Button>',
    '  <DropdownMenuTrigger as-child><Button variant="ghost">E</Button></DropdownMenuTrigger>',
    '  <DropdownMenuTrigger><Button variant="ghost">F</Button></DropdownMenuTrigger>',
    '</template>',
  ].join('\n')

  expect(untypedIn(source)).toEqual([2, 7])
})
