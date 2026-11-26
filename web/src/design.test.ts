// shadcn-vue's rules for this app (docs/design.md), checked mechanically over the source: each rule
// runs over every file outside components/ui, which stays as shadcn-vue's CLI wrote it, and its own
// cases prove it flags the breach and passes the correct form.

import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { join, relative } from 'node:path'
import { describe, expect, test } from 'vitest'
import { present } from './test/present'
import { readVue, verdict, vueFiles, withParents, type Tag } from './test/guard'
import { sizedStrings, typeBreaches } from './test/typeRoles'

const SRC = import.meta.dirname
const ROOT = join(SRC, '../..')

function files(folder: string, ending: RegExp): string[] {
  return readdirSync(folder, { withFileTypes: true }).flatMap((entry) => {
    const path = join(folder, entry.name)
    if (entry.isDirectory()) return files(path, ending)
    return ending.test(entry.name) && !entry.name.endsWith('.test.ts') ? [path] : []
  })
}

const read = (path: string): string => readFileSync(path, 'utf8')
const name = (path: string): string => relative(SRC, path)
const OURS = files(SRC, /\.(vue|ts)$/).filter((path) => !name(path).startsWith('components/ui/'))
// The files are read once at load, outside any test's timeout: a case then only runs a regex over
// text in memory, so a slow disk under load cannot time it out.
const TEXTS = OURS.map((path): [string, string] => [name(path), read(path)])
const VUE = TEXTS.filter(([where]) => where.endsWith('.vue'))

/** The class lists of a template: static `class` values and the quoted strings of `:class`. */
function classLists(source: string): string[] {
  const statics = [...source.matchAll(/(?<![:\w-])class="([^"]*)"/g)].map((m) => m[1] ?? '')
  const bound = [...source.matchAll(/:class="([^"]*)"/g)].flatMap((m) =>
    [...(m[1] ?? '').matchAll(/'([^']*)'/g)].map((q) => q[1] ?? ''),
  )
  return [...statics, ...bound]
}
/** A class without its variants (`hover:`, `md:`, `group-data-[x]/a:`). */
const bare = (token: string): string => token.replace(/^(?:[^:\s]*:)+/, '')

/** Where `found` names a breach in each source, as `file: what`. */
function breaches(texts: [string, string][], found: (text: string) => string[]): string[] {
  return texts.flatMap(([where, text]) => found(text).map((what) => `${where}: ${what}`))
}

// shadcn-vue's styling rule: colours are the theme's semantic tokens, never a palette colour, a
// literal white or black, an arbitrary colour or a `dark:` override.
const COLOUR_UTILITY = String.raw`(?:bg|text|border|ring|outline|divide|fill|stroke|from|via|to|decoration|placeholder|caret|accent|shadow)`
const PALETTE = new RegExp(
  String.raw`(?<![\w-])${COLOUR_UTILITY}-(?:(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3}|white|black|\[(?:#|rgb|hsl|oklch|color|var\(--color))`,
  'g',
)
const DARK = /(?<![\w-])dark:/g
const colours = (text: string): string[] => [
  ...[...text.matchAll(PALETTE)].map((m) => m[0]),
  ...[...text.matchAll(DARK)].map(() => 'dark:'),
]

// daisyUI's component classes and the board's old tokens, whole classes of a class list.
const OLD_COMPONENTS = new Set(
  (
    'alert avatar badge breadcrumbs btn card carousel chat checkbox countdown diff divider dock ' +
    'drawer dropdown fieldset file-input footer hero indicator input join kbd label link loading ' +
    'mask menu mockup modal navbar progress radial-progress radio range rating select skeleton ' +
    'stack stat status steps swap tab tabs textarea timeline toast toggle tooltip validator ' +
    'pill surface muted faint mono eyebrow long-text icon segmented popover hit-corner trace-row ' +
    'property property-column'
  ).split(' '),
)
const OLD_PREFIXED =
  /^(?:(?:btn|badge|menu|card|alert|input|select|textarea|toggle|checkbox|radio|tabs?|table|join|loading|link|dropdown|modal|collapse|divider|kbd|steps?|stat|tooltip|overlay|indicator|swap|status|label|range|rating)-(?!none$|all$|auto$|text$|disc$|decimal$|inside$|outside$|image)[\w-]+|rounded-(?:box|field|selector)|text-(?:2xs|3xs|dense)|shadow-float)$/
const OLD_TOKEN = new RegExp(
  String.raw`(?<![\w-])${COLOUR_UTILITY}-(?:base-(?:100|200|300|content)|neutral(?:-content)?|(?:primary|secondary|accent)-content|(?:info|success|warning)-content|error(?:-content)?|stage-[\w-]+|label-(?:rose|orange|amber|lime|emerald|teal|sky|indigo|violet|pink)|tone-[\w-]+|brand|control|selected|segment[\w-]*)(?![\w-])`,
  'g',
)
const oldClasses = (text: string): string[] => [
  ...classLists(text)
    .flatMap((list) => list.split(/\s+/))
    .filter((token) => OLD_COMPONENTS.has(bare(token)) || OLD_PREFIXED.test(bare(token))),
  ...[...text.matchAll(OLD_TOKEN)].map((m) => m[0]),
]

// shadcn-vue's styling rule: gap, never space-x or space-y.
const SPACE = /(?<![\w-])-?space-[xy]-[\w.[\]]+/g
const spaces = (text: string): string[] => [...text.matchAll(SPACE)].map((m) => m[0])

// shadcn-vue's styling rule: `class` on a component is for layout, never its colour or type; a
// look comes from a variant or a size. These are the components whose look is their variant.
const VARIANT_COMPONENTS = new Set([
  'Button',
  'Badge',
  'Alert',
  'Card',
  'Item',
  'Toggle',
  'ToggleGroupItem',
  'Empty',
  'Kbd',
])
const LOOK =
  /^(?:font-(?:thin|extralight|light|normal|medium|semibold|bold|extrabold|black|mono|sans|serif)|text-(?:xs|sm|base|lg|xl|\dxl|\[.*\]|primary|secondary|muted|muted-foreground|accent|destructive|foreground|card-foreground|primary-foreground|background)(?:\/\d+)?|bg-\S+|border-(?!0$|t$|b$|l$|r$|x$|y$|2$|dashed$|none$)\S+|shadow(?:-\S+)?|rounded(?:-\S+)?|ring-(?!0$)\S+)$/
// The one exception: a table header's sort Button takes the header's text size, so a header reads
// alike whether it sorts or not (the Data Table example); it is marked data-header-sort.
const HEADER_SORT = (tag: Tag, token: string): boolean =>
  tag.name === 'Button' && /\sdata-header-sort[\s>]/.test(tag.text) && token === 'text-sm'
const looks = (tag: Tag): string[] =>
  VARIANT_COMPONENTS.has(tag.name)
    ? (/(?<![:\w-])class="([^"]*)"/.exec(tag.text)?.[1] ?? '')
        .split(/\s+/)
        .filter((token) => LOOK.test(bare(token)) && !HEADER_SORT(tag, token))
    : []

// shadcn-vue's icon rule: an icon inside a component that sizes its icons takes no size class. A
// component sizes them when its source, or the variants it reads, style the `svg` it holds.
const UI = join(SRC, 'components/ui')
const SIZERS = new Set(
  readdirSync(UI).flatMap((folder) => {
    const index = join(UI, folder, 'index.ts')
    const variantsSize = existsSync(index) && read(index).includes('svg')
    return readdirSync(join(UI, folder))
      .filter((file) => file.endsWith('.vue'))
      .filter((file) => {
        const source = read(join(UI, folder, file))
        return source.includes('svg') || (variantsSize && source.includes('Variants('))
      })
      .map((file) => file.replace(/\.vue$/, ''))
  }),
)
const ICON = 'HugeiconsIcon'
const sizedIcon = (tag: Tag & { parent: string }): boolean =>
  tag.name === ICON &&
  SIZERS.has(tag.parent) &&
  /(?<![:\w-])class="[^"]*(?<![\w-])(?:size|w|h)-[\w.[\]]+/.test(tag.text)
// shadcn-vue's icon rule: an icon is passed as an object, never a string key.
const keyedIcon = (tag: Tag): boolean => tag.name === ICON && !/\s:icon="[^"]+"/.test(tag.text)

// docs/components/empty.md: an EmptyTitle is a short title and the sentence is its
// EmptyDescription. A title's literal words, or each quoted string of its expression, may hold no
// colon, no second sentence and at most TITLE_MOST characters.
const TITLE_MOST = 50
// The Item docs' list: default Items in an ItemGroup (a `div` of role list), so no outlined Item
// and no Item drawn as an `li`.
const listBreaches = (text: string): string[] =>
  [...text.matchAll(/<Item\b[^>]*?(?:variant="outline"|as="li")/g)].map((m) =>
    m[0].includes('as="li"') ? 'Item as li' : 'outlined Item',
  )
function longTitles(text: string): string[] {
  return [...text.matchAll(/<EmptyTitle[^>]*>([\s\S]*?)<\/EmptyTitle/g)].flatMap(
    ([, inside = '']) => {
      const words = inside.includes('{{')
        ? [...inside.matchAll(/(['`"])((?:(?!\1).)*)\1/g)].map((m) => m[2] ?? '')
        : [inside.replace(/<[^>]*>/g, '')]
      return words
        .map((title) =>
          title
            .replace(/\$\{[^}]*\}/g, 'x')
            .replace(/\s+/g, ' ')
            .trim(),
        )
        .filter(
          (title) => title.includes(':') || /\.\s+\S/.test(title) || title.length > TITLE_MOST,
        )
    },
  )
}

// One surface level per section (the owner): inside a Card, a Sheet's or a Dialog's content there
// is no Card, no component that draws one, and no bordered box; a list there is plain Items.
const SURFACE = /<(Card|SheetContent|DialogContent|AlertDialogContent)(?=[\s>])/g
const templateOf = (text: string): string =>
  /<template>([\s\S]*)<\/template>\s*$/.exec(text)?.[1] ?? ''
/** The class lists of a template's bordered boxes: a border and a rounding, not a swatch or a picture. */
const borderedBoxes = (template: string): string[][] =>
  [...template.matchAll(/<([a-zA-Z][\w-]*)\b[^<>]*?(?<![:\w-])class="([^"]*)"/g)]
    .filter((m) => m[1] !== 'img')
    .map((m) => (m[2] ?? '').split(/\s+/))
    .filter(
      (classes) =>
        classes.some((c) => c === 'border' || c === 'border-dashed') &&
        classes.some((c) => c.startsWith('rounded')) &&
        !classes.some((c) => c.startsWith('size-')),
    )
/** Whether each component draws a Card or a bordered box, itself or through a component it holds. */
function cardDrawers(texts: [string, string][]): Set<string> {
  const templates = new Map(
    texts.map(([where, text]) => [/([^/]+)\.vue$/.exec(where)?.[1] ?? where, templateOf(text)]),
  )
  const draws = new Set<string>()
  let grew = true
  while (grew) {
    grew = false
    for (const [component, template] of templates) {
      if (draws.has(component)) continue
      const held = [...template.matchAll(/<([A-Z]\w+)/g)].map((m) => m[1] ?? '')
      if (
        /<Card(?=[\s>])/.test(template) ||
        borderedBoxes(template).length > 0 ||
        held.some((tag) => draws.has(tag))
      ) {
        draws.add(component)
        grew = true
      }
    }
  }
  return draws
}
/** The text inside each surface of a template, up to its own closing tag. */
function surfaces(template: string): [string, string][] {
  return [...template.matchAll(SURFACE)].map((open) => {
    const tag = open[1] ?? ''
    const from = open.index + open[0].length
    let depth = 1
    for (const step of template.slice(from).matchAll(new RegExp(`<(/?)${tag}(?=[\\s>])`, 'g'))) {
      depth += step[1] ? -1 : 1
      if (depth === 0) return [tag, template.slice(from, from + step.index)]
    }
    return [tag, template.slice(from)]
  })
}
function nested(text: string, drawers: Set<string>): string[] {
  return surfaces(templateOf(text)).flatMap(([surface, inside]) => {
    const tags = [...new Set([...inside.matchAll(/<([A-Z]\w+)(?=[\s>/])/g)].map((m) => m[1] ?? ''))]
    const boxes = borderedBoxes(inside)
    return [
      ...tags
        .filter((tag) => tag === 'Card' || drawers.has(tag))
        .map((tag) => `${tag} in ${surface}`),
      ...boxes.map((classes) => `bordered box (${classes.join(' ')}) in ${surface}`),
    ]
  })
}

describe('shadcn-vue rules over the source', () => {
  test('colours_are_the_theme_s_semantic_tokens', () => {
    expect(TEXTS.length).toBeGreaterThan(100)
    expect(breaches(TEXTS, colours)).toEqual([])
  })

  test('no_daisyui_class_and_no_old_token_anywhere', () => {
    expect(breaches(TEXTS, oldClasses)).toEqual([])
  })

  test('spacing_is_gap_never_space', () => {
    expect(breaches(TEXTS, spaces)).toEqual([])
  })

  test('class_on_a_variant_component_sets_layout_only', () => {
    const tags = VUE.flatMap(([where, text]) =>
      withParents(text).map((tag): [string, Tag] => [where, tag]),
    ).filter(([, tag]) => VARIANT_COMPONENTS.has(tag.name))
    const found = tags
      .filter(([, tag]) => looks(tag).length)
      .map(([where, tag]) => `${where}:${String(tag.line)} <${tag.name}> ${looks(tag).join(' ')}`)

    expect(tags.length).toBeGreaterThan(100)
    expect(found).toEqual([])
  })

  test('icons_are_objects_and_a_component_sizes_the_ones_it_holds', () => {
    const icons = vueFiles()
      .filter((file) => !file.startsWith('components/ui/'))
      .flatMap((file) => withParents(readVue(file)).map((tag) => ({ file, tag })))
      .filter(({ tag }) => tag.name === ICON)
    const found = icons
      .filter(({ tag }) => sizedIcon(tag) || keyedIcon(tag))
      .map(({ file, tag }) => `${file}:${String(tag.line)} in <${tag.parent}>`)

    expect(icons.length).toBeGreaterThan(80)
    expect(SIZERS.has('Button') && SIZERS.has('DropdownMenuItem') && SIZERS.has('Badge')).toBe(true)
    expect(SIZERS.has('CardContent')).toBe(false)
    expect(found).toEqual([])
  })

  // An Empty with a title shows its icon in EmptyMedia, so it never reads as all clear where empty
  // means no data or work to do.
  test('every_titled_empty_state_shows_its_icon', () => {
    const found = VUE.flatMap(([where, text]) =>
      [...text.matchAll(/<EmptyHeader>([\s\S]*?)<\/EmptyHeader>/g)]
        .map(([, inside = '']) => inside)
        .filter((inside) => inside.includes('<EmptyTitle') && !inside.includes('<EmptyMedia'))
        .map((inside) => `${where}: ${inside.replace(/\s+/g, ' ').trim().slice(0, 60)}`),
    )

    expect(found).toEqual([])
  })

  test('one_surface_level_per_section', () => {
    const drawers = cardDrawers(VUE)
    expect(drawers.has('TicketCard')).toBe(true)
    expect(breaches(VUE, (text) => nested(text, drawers))).toEqual([])
  })

  test('every_item_list_is_plain_items_in_an_item_group', () => {
    expect(breaches(VUE, listBreaches)).toEqual([])
  })

  // Keep the gate identity for the Agents card grid as it moves to shared Card surfaces.
  test('every_card_grid_on_the_list_really_draws_outlined_cards', () => {
    const agent = read(join(SRC, 'components/AgentCard.vue'))
    const roster = read(join(SRC, 'pages/AgentsPage.vue'))
    expect(agent).toMatch(/<ContentCard\s+role="listitem"/)
    expect(agent).not.toMatch(/<Item\b[^>]*\bvariant="outline"/)
    expect(roster).toMatch(
      /<ItemGroup[\s\S]*?aria-label="Agents"[\s\S]*?md:grid-cols-2[\s\S]*?<AgentCard\b/,
    )
  })

  test('an_empty_title_is_short_and_its_sentence_the_description', () => {
    expect(breaches(VUE, longTitles)).toEqual([])
  })
})

describe('the rules flag the breach and pass the correct form', () => {
  test('the_colour_rule', () => {
    expect(
      colours(
        '<p class="text-emerald-600 bg-white dark:bg-zinc-900 border-[#fff] fill-[oklch(1_0_0)]">',
      ),
    ).toEqual(['text-emerald-600', 'bg-white', 'bg-zinc-900', 'border-[#', 'fill-[oklch', 'dark:'])
    expect(
      colours(
        '<p class="text-muted-foreground bg-primary/80 border-border ring-ring/50 bg-chart-3 text-destructive">',
      ),
    ).toEqual([])
  })

  test('the_old_class_rule', () => {
    expect(
      oldClasses(
        '<span class="pill btn-ghost hover:surface"><i :class="{ \'menu-active\': a, faint: b }" class="bg-base-200 text-error/50 rounded-box"></i>',
      ),
    ).toEqual([
      'pill',
      'btn-ghost',
      'hover:surface',
      'rounded-box',
      'menu-active',
      'bg-base-200',
      'text-error',
    ])
    expect(oldClasses("const DOT = 'bg-stage-spec'")).toEqual(['bg-stage-spec'])
    expect(
      oldClasses(
        '<p class="list-disc select-none select-all table collapse text-muted-foreground bg-chart-1">Copy link</p>',
      ),
    ).toEqual([])
  })

  test('the_nesting_rule', () => {
    const drawers = cardDrawers([
      ['components/Row.vue', '<template><Card><slot /></Card></template>'],
    ])
    const page = (inside: string) =>
      `<template><Card><CardContent>${inside}</CardContent></Card></template>`

    expect([
      nested(page('<Card><CardContent>x</CardContent></Card>'), drawers),
      nested(page('<Row />'), drawers),
      nested(page('<div class="rounded-lg border p-3">x</div>'), drawers),
      nested('<template><SheetContent><Card>x</Card></SheetContent></template>', drawers),
    ]).toEqual([
      ['Card in Card'],
      ['Row in Card'],
      ['bordered box (rounded-lg border p-3) in Card'],
      ['Card in SheetContent'],
    ])
    expect([
      nested(page('<ItemGroup><Item role="listitem">x</Item></ItemGroup>'), drawers),
      nested('<template><Card>a</Card><Card>b</Card><Row /></template>', drawers),
      nested(page('<span class="size-6 rounded-md border bg-primary"></span>'), drawers),
      nested(page('<img\n  src="a.png"\n  class="w-full rounded-xl border"\n/>'), drawers),
    ]).toEqual([[], [], [], []])
    expect(
      nested(
        page('<Framed />'),
        cardDrawers([
          ['components/Framed.vue', '<template><p class="rounded-xl border">x</p></template>'],
        ]),
      ),
    ).toEqual(['Framed in Card'])
  })

  test('the_item_list_rule', () => {
    expect(
      listBreaches(
        '<Item\n  as="li"\n  size="sm"\n>' + '<Item role="listitem" variant="outline" size="sm">',
      ),
    ).toEqual(['Item as li', 'outlined Item'])
    expect(
      listBreaches(
        '<ItemGroup><Item role="listitem" size="sm" :variant="selected ? \'muted\' : \'default\'">' +
          '<Badge variant="outline">x</Badge></ItemGroup>',
      ),
    ).toEqual([])
  })

  test('the_empty_title_rule', () => {
    expect(
      longTitles(
        '<EmptyTitle>No agents defined: every run uses the default agent.</EmptyTitle>' +
          '<EmptyTitle\n  >Benchmarks compare models. They arrive later.</EmptyTitle\n>' +
          "<EmptyTitle>{{ filter ? 'Nothing: a colon' : `No ${kind} sessions` }}</EmptyTitle>" +
          '<EmptyTitle>A title far longer than any short title should ever be</EmptyTitle>',
      ),
    ).toEqual([
      'No agents defined: every run uses the default agent.',
      'Benchmarks compare models. They arrive later.',
      'Nothing: a colon',
      'A title far longer than any short title should ever be',
    ])
    expect(
      longTitles(
        '<EmptyTitle>No tickets match the filter.</EmptyTitle>' +
          "<EmptyTitle>{{ narrowed ? `No archived ticket matches ${query}` : 'No archived tickets' }}</EmptyTitle>" +
          '<EmptyTitle>No ticket {{ id }}</EmptyTitle>',
      ),
    ).toEqual([])
  })

  test('the_space_rule', () => {
    expect(spaces('<div class="space-y-4 md:-space-x-2">')).toEqual(['space-y-4', '-space-x-2'])
    expect(spaces('<div class="flex flex-col gap-4" data-space="x">')).toEqual([])
  })

  test('the_layout_rule', () => {
    const tag = (text: string): Tag => ({ name: /<(\w+)/.exec(text)?.[1] ?? '', text, line: 1 })

    expect(
      looks(tag('<Card class="max-w-md bg-blue-100 text-blue-900 font-bold hover:bg-muted">')),
    ).toEqual(['bg-blue-100', 'font-bold', 'hover:bg-muted'])
    expect(
      looks(tag('<Button class="text-xs text-destructive border-input rounded-full">')),
    ).toEqual(['text-xs', 'text-destructive', 'border-input', 'rounded-full'])
    expect(
      looks(tag('<Card class="mx-auto mt-4 w-full gap-1.5 border-t text-left whitespace-normal">')),
    ).toEqual([])
    expect(looks(tag('<CardTitle class="text-2xl font-semibold">'))).toEqual([])
  })

  test('the_icon_rule', () => {
    const icons = (source: string) =>
      withParents(`<template>${source}</template>`).filter((tag) => tag.name === ICON)
    const flagged = (source: string) => icons(source).map((tag) => sizedIcon(tag) || keyedIcon(tag))

    expect(
      flagged(
        '<Button type="button"><HugeiconsIcon :icon="PlusSignIcon" class="size-4" />New</Button>' +
          '<span><HugeiconsIcon icon="plus" class="size-4" /></span>',
      ),
    ).toEqual([true, true])
    expect(
      flagged(
        '<Button type="button"><HugeiconsIcon :icon="PlusSignIcon" data-icon="inline-start" />New</Button>' +
          '<span class="flex"><HugeiconsIcon\n  :icon="Clock01Icon"\n  class="size-3.5 shrink-0"\n/></span>' +
          '<CardContent><HugeiconsIcon :icon="BotIcon" class="size-4" /></CardContent>',
      ),
    ).toEqual([false, false, false])
  })
})

test('design_docs_cite_files_that_exist', () => {
  const cited =
    /`((?:web|tests|crates|docs|scripts|layouts)\/[\w./-]+)`|\(((?:web|layouts)\/[\w./-]+)\)/g
  const header = (text: string): string => text.split('\n').slice(0, 12).join('\n')
  const texts: [string, string][] = [
    ['docs/design.md', readFileSync(join(ROOT, 'docs/design.md'), 'utf8')],
    ...VUE.map(([where, text]): [string, string] => [where, header(text)]),
  ]
  const missing = texts.flatMap(([where, text]) =>
    [...text.matchAll(cited)]
      .map((match) => present(match[1] ?? match[2], 'a cited path').replace(/[.,]$/, ''))
      .filter((path) => !existsSync(join(ROOT, path)))
      .map((path) => `${where}: ${path}`),
  )

  expect(missing).toEqual([])
})

// CF-349: a page long enough to scroll keeps the board's width: its scroll area reserves the gutter.
test('the_page_scroll_area_keeps_its_scrollbar_gutter', () => {
  const scroller = present(
    /<div\s+ref="scroller"[^>]*>/.exec(read(join(SRC, 'App.vue')))?.[0],
    'the page scroller',
  )

  expect(scroller).toContain('overflow-auto')
  expect(scroller).toContain('[scrollbar-gutter:stable_both-edges]')
})

// CF-352: the page body gives back the gutter from its side padding, so its margin is equal on all sides.
test('the_page_body_gives_back_the_gutter_from_its_sides', () => {
  const styles = read(join(SRC, 'styles/app.css'))

  expect(styles).toContain('padding-block: var(--page-margin)')
  expect(styles).toContain(
    'padding-inline: max(0px, calc(var(--page-margin) - var(--gutter, 0px)))',
  )
})

// A native scrollbar takes its colours from `color-scheme`, not from the theme tokens: without it
// the dark theme draws the browser's light scrollbars. The thumb is the ScrollArea's own colour.
test('native_scrollbars_follow_the_theme', () => {
  const styles = read(join(SRC, 'styles/app.css'))

  expect(styles).toMatch(/:root\s*\{[^}]*color-scheme:\s*light;/)
  expect(styles).toMatch(/\.dark\s*\{[^}]*color-scheme:\s*dark;/)
  expect(styles).toMatch(/scrollbar-color:\s*var\(--border\)\s+transparent;/)
})

// The Content-Security-Policy loads styles and fonts from 'self' only: a stylesheet that imports
// from another origin is refused in the browser and reported as a violation on every page.
test('the_stylesheets_load_nothing_from_another_origin', () => {
  const sheets = files(join(SRC, 'styles'), /\.css$/)
  const found = sheets.filter((path) => /url\(\s*['"]?https?:/i.test(read(path))).map(name)

  expect(sheets.length).toBeGreaterThan(0)
  expect(found).toEqual([])
})

// A mono id or code takes the size of the text around it: a table cell never shrinks its id.
test('a_mono_cell_takes_the_size_of_its_row', () => {
  const shrunk = (text: string): string[] =>
    [...text.matchAll(/cell: '([^']*)'/g)]
      .map(([, cls = '']) => cls)
      .filter(
        (cls) =>
          /(?<![\w-])font-mono(?![\w-])/.test(cls) && /(?<![\w:-])text-xs(?![\w-])/.test(cls),
      )
  expect(breaches(TEXTS, shrunk)).toEqual([])
})

// docs/design.md's type scale: a size a screen or a class map sets is one of the roles, so text is
// the same size wherever it plays the same part. components/ui sizes itself; /design shows samples.
describe('the type standard', () => {
  test.each([
    ['text-xs font-medium tracking-wider text-muted-foreground uppercase', []],
    ['font-mono text-xs', []],
    ['cn-font-heading text-base font-medium', []],
    ['text-lg font-semibold', []],
    ['text-lg font-normal text-muted-foreground', []],
    ['text-2xl font-semibold tabular-nums @[250px]/card:text-3xl', []],
    ['text-sm text-muted-foreground', []],
    ['text-xs text-muted-foreground', ['text-xs']],
    ['flex text-xs/relaxed', ['text-xs/relaxed']],
    ['md:text-xs', ['md:text-xs']],
    ['text-2xl font-semibold', ['text-2xl']],
    ['text-2xl font-semibold tabular-nums', []],
    ['text-lg font-semibold md:text-lg', []],
    ['text-sm md:text-lg', ['md:text-lg']],
    ['text-[0.625rem]', ['text-[0.625rem]']],
    ['text-lg', ['text-lg']],
  ])('%s_breaks_%j', (classes, breaches) => {
    expect(typeBreaches(classes)).toEqual(breaches)
  })

  /** Files that set a size outside the roles, each with its reason; the list only shrinks. */
  const TYPE_EXCEPTIONS: Record<string, string> = {
    'components/TicketCard.vue': "the assignee's initial inside its 20 px circle",
  }

  test('every_text_size_a_screen_sets_is_a_role', () => {
    const screens = TEXTS.filter(
      ([where]) =>
        !where.startsWith('components/ai/') &&
        !where.startsWith('pages/design/') &&
        !where.startsWith('test/'),
    )
    const found = new Map<string, string[]>()
    for (const [where, text] of screens) {
      const sized = sizedStrings(text).flatMap(typeBreaches)
      if (sized.length) found.set(where, [`${where}: ${sized.join(', ')}`])
    }

    expect(screens.length).toBeGreaterThan(100)
    expect(verdict(found, TYPE_EXCEPTIONS)).toEqual([])
  })
})

// A row is laid out by Item's parts (docs/design.md, Page anatomy): ItemHeader, ItemContent with
// ItemTitle and ItemDescription, ItemActions, ItemFooter. An Item given its own grid or flex is how
// each row type came to order and space its parts its own way.
const ITEM_TAG = /<Item\b((?:"[^"]*"|'[^']*'|[^>"'])*)>/g
const ownLayout = (text: string): string[] =>
  [...text.matchAll(ITEM_TAG)]
    .map(([, attributes = '']) => /\bclass="([^"]*)"/.exec(attributes)?.[1] ?? '')
    // A layout set at a breakpoint (`@4xl:grid`, `md:flex`) is the row's own layout too.
    .filter((classes) =>
      /(?<![\w-])(?:[\w@[\]/-]+:)?(grid|flex|block|inline-flex)(?![\w-])/.test(classes),
    )

// Retain the layout regression's identifier as the shared measure changes to full width.
test('reading_pages_keep_a_measure_and_wide_pages_do_not', () => {
  const pages = [
    'Inbox',
    'Memory',
    'Sessions',
    'Session',
    'Agents',
    'Ticket',
    'Tickets',
    'Archive',
    'Team',
    'Design',
  ]
  for (const page of pages) {
    const source = read(join(SRC, `pages/${page}Page.vue`))
    expect(source, page).toMatch(/\bpage-wide\b/)
    expect(source, page).not.toContain('page-measure')
  }
})

test('a_row_is_laid_out_by_its_Item_parts', () => {
  expect(
    ownLayout(
      '<Item size="sm" class="grid gap-1"><Item\n  class="flex items-baseline"><Item class="scroll-mt-4"><ItemContent class="flex"><Item class="relative @4xl:grid">',
    ),
  ).toEqual(['grid gap-1', 'flex items-baseline', 'relative @4xl:grid'])
  const found = new Map<string, string[]>()
  for (const [where, text] of VUE.filter(([file]) => !file.startsWith('pages/design/'))) {
    const own = ownLayout(text)
    if (own.length) found.set(where, [`${where}: ${own.join(' | ')}`])
  }
  expect(verdict(found, {})).toEqual([])
})
