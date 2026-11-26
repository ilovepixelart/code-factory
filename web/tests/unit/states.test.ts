// CF-1276: a badge, a loading indicator, an alert block and an empty state are shadcn-vue's Badge,
// Spinner, Alert and Empty (docs/design.md, The rules the tests hold). A source outside components/ui that writes its own
// fails here, unless listed with the reason; a listed source that no longer offends fails too, so
// the list only shrinks.

import { describe, expect, test } from 'vitest'
import { sourceOffenders, verdict, vueFiles } from '../support/guard'

// A class attribute, static or bound, over as many lines as it takes.
const CLASS_ATTRIBUTE = /(?::class|\bclass)=(?:"[^"]*"|'[^']*')/g
// An opening tag of a paragraph, a list item or a table cell, then the text before the next tag.
const TEXT_OF = /<(?:p|li|td)\b(?:"[^"]*"|'[^']*'|[^>"'])*>([^<]*)/g

// A word of daisyUI's component with its modifiers, as a whole word of a class list or a map.
const word = (base: string): RegExp =>
  new RegExp(
    `(?<![\\w-])${base}-(?:xs|sm|md|lg|soft|ghost|dash|outline|neutral|primary|secondary|accent|info|success|warning|error)(?![\\w-])`,
  )
const bare = (base: string): RegExp => new RegExp(`(?<![\\w-])${base}(?![\\w-])`)

const inClasses = (source: string, rule: RegExp): boolean =>
  (source.match(CLASS_ATTRIBUTE) ?? []).some((attribute) => rule.test(attribute))

const owns = (base: string) => (source: string) =>
  word(base).test(source) || inClasses(source, bare(base))
const badge = owns('badge')
const loading = owns('loading')
const alert = owns('alert')
const emptyText = (source: string): boolean =>
  [...source.matchAll(TEXT_OF)].some((m) => /^(?:No |Nothing)/.test((m[1] ?? '').trim()))

// File to the reason it still writes its own. A reason is a constraint, never "later".
const ALLOWED_EMPTY_TEXT: Record<string, string> = {
  'components/AgentCard.vue':
    "No runs yet is the value of the card's Last row, one line among its rows (owner decision); a centred Empty block left a tall gap in every new agent's card",
}

// A status is a StatusBadge (docs/design.md, Theme): its tone from the status map, its word in
// sentence case. A Badge that takes a status variant itself, or a status word that opens in lower
// case, is how one status came to read in two casings on two pages.
const BADGE_TAG = /<Badge\b(?:"[^"]*"|'[^']*'|[^>"'])*>/g
const statusOnBadge = (source: string): boolean =>
  (source.match(BADGE_TAG) ?? []).some((tag) =>
    /TONE_VARIANTS|statusVariant\(|variant="destructive"/.test(tag),
  )
const LOWER_STATUS =
  /<StatusBadge\b(?:"[^"]*"|'[^']*'|[^>"'])*(?<!\/)>\s*(?:<HugeiconsIcon\b(?:"[^"]*"|'[^']*'|[^>"'])*\/>\s*)?(?:<span\b[^>]*>\s*)?[a-z]/
const lowerStatus = (source: string): boolean => LOWER_STATUS.test(source)

describe('the states are written through shadcn-vue', () => {
  const files = vueFiles().filter((file) => !file.startsWith('components/ui/'))

  test('a_badge_is_a_Badge', () => {
    expect(files.length).toBeGreaterThan(50)
    expect(verdict(sourceOffenders(files, badge), {})).toEqual([])
  })

  test('a_loading_ring_is_a_Spinner', () => {
    expect(verdict(sourceOffenders(files, loading), {})).toEqual([])
  })

  test('an_alert_is_an_Alert', () => {
    expect(verdict(sourceOffenders(files, alert), {})).toEqual([])
  })

  test('a_status_is_a_StatusBadge', () => {
    const others = files.filter((file) => file !== 'components/StatusBadge.vue')
    expect(verdict(sourceOffenders(others, statusOnBadge), {})).toEqual([])
  })

  test('a_status_word_opens_with_a_capital', () => {
    expect(verdict(sourceOffenders(files, lowerStatus), {})).toEqual([])
  })

  test('an_empty_text_is_an_Empty', () => {
    const found = sourceOffenders(files, emptyText)
    expect(verdict(found, ALLOWED_EMPTY_TEXT)).toEqual([])
    expect(Object.values(ALLOWED_EMPTY_TEXT).every((reason) => reason.length > 20)).toBe(true)
  })
})

describe('the rules', () => {
  test('the_status_rules_flag_a_status_on_a_Badge_and_a_lower_case_word_and_pass_the_right_form', () => {
    expect([
      statusOnBadge('<Badge :variant="TONE_VARIANTS.warning">No source</Badge>'),
      statusOnBadge('<Badge\n  :variant="statusVariant(x)"\n>{{ x }}</Badge>'),
      statusOnBadge('<Badge variant="outline">lesson</Badge>'),
      statusOnBadge('<Badge v-if="x" variant="destructive">left out</Badge>'),
      lowerStatus('<StatusBadge tone="warning">no source</StatusBadge>'),
      lowerStatus(
        '<StatusBadge\n  tone="info"\n  ><HugeiconsIcon :icon="BotIcon" data-icon="inline-start" />agent</StatusBadge>',
      ),
      lowerStatus('<StatusBadge tone="warning">No source</StatusBadge>'),
      lowerStatus('<StatusBadge :state="s.state" />'),
      lowerStatus('<StatusBadge state="blocked" /><span>waiting 3m</span>'),
      lowerStatus('<StatusBadge tone="info">{{ statusWord(x) }}</StatusBadge>'),
    ]).toEqual([true, true, false, true, true, true, false, false, false, false])
  })

  test('the_empty_text_rule_reads_tags_across_lines_and_skips_other_words', () => {
    expect(emptyText('<p\n  class="muted"\n  :title="a > b"\n>\n  Nothing here yet.\n</p>')).toBe(
      true,
    )
    expect(emptyText('<p>Nobody asked</p><li>Not now</li>')).toBe(false)
  })

  test('the_class_rules_read_a_class_across_lines_and_a_map_and_skip_look_alikes', () => {
    expect(badge('<span class="x badge\n badge-sm">a</span>')).toBe(true)
    expect(loading('<i :class="{ \'loading\': a }"></i>')).toBe(true)
    expect(alert('<div class="alert">a</div>')).toBe(true)
    expect(badge('<img loading="lazy" class="bg-badge-quiet"><p hint="a badge">x</p>')).toBe(false)
    expect(loading('<img loading="lazy" class="bg-badge-quiet">')).toBe(false)
  })
})
