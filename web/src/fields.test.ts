// CF-1275: a form control, and the error under it, is one of shadcn-vue's components in
// components/ui (docs/design.md, The rules the tests hold). A `.vue` file outside that folder holds
// no `<input`, `<textarea`, `<select` and no `<p` carrying `text-destructive` (an error written by
// hand, where FieldError belongs) unless it is on the list below with the reason it cannot move yet.

import { expect, test } from 'vitest'
import { offenders, openingTags, vueFiles, verdict, type Tag } from './test/guard'

const ALLOWED: Record<string, string> = {
  'components/ai/StackTrace/StackTrace.vue':
    "Stack Trace's error line over a failed run, not a field's",
}

const TEXT_ERROR = /(?<![\w-])text-destructive(?![\w/-])/
const hand = (tag: Tag): boolean =>
  ['input', 'textarea', 'select'].includes(tag.name) ||
  (tag.name === 'p' && TEXT_ERROR.test(tag.text))

test('fields_and_their_errors_are_written_through_the_form_components', () => {
  const files = vueFiles()
  const owners = files.filter((file) => file.startsWith('components/ui/'))
  const found = offenders(files, hand, owners)

  expect(files.length).toBeGreaterThan(50)
  expect(owners.length).toBeGreaterThan(4)
  expect(verdict(found, ALLOWED)).toEqual([])
})

test('the_guard_reads_a_tag_across_lines_and_tells_controls_from_look_alikes', () => {
  const source = [
    '<template>',
    '  <input',
    '    :id="x"',
    '    @change="() => go()"',
    '  />',
    '  <textarea rows="2"></textarea><select v-model="p"></select>',
    '  <p',
    '    v-if="e"',
    '    class="w-full text-xs text-destructive"',
    '  >x</p>',
    '  <p class="bg-destructive text-destructive/10">a</p><p class="text-muted-foreground">b</p>',
    '  <pre class="text-destructive">c</pre><span class="text-destructive">d</span><Input v-model="a" />',
    '</template>',
  ].join('\n')

  expect(
    openingTags(source)
      .filter(hand)
      .map((tag) => `${String(tag.line)} ${tag.name}`),
  ).toEqual(['2 input', '6 textarea', '6 select', '7 p'])
})
