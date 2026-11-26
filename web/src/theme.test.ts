import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { expect, test } from 'vitest'
import { STAGE_DOT, STAGES } from './lib/board'
import { LABEL_COLORS } from './lib/format'
import { badgeVariants } from '@/components/ui/badge'

const styles = readFileSync(join(import.meta.dirname, 'styles/app.css'), 'utf8')
const block = (selector: string): string =>
  new RegExp(`(?:^|\\n)${selector.replace('.', '\\.')} \\{([^}]*)\\}`).exec(styles)?.[1] ?? ''

// The status colours are theme tokens, set for both themes and mapped to utilities, as shadcn-vue
// adds a colour: a variable per theme and a `--color-*` entry in `@theme inline`.
test.each(['success', 'warning', 'info'])('the_%s_colour_is_a_token_in_both_themes', (name) => {
  expect(block(':root')).toMatch(new RegExp(`--${name}: `))
  expect(block('.dark')).toMatch(new RegExp(`--${name}: `))
  expect(block('@theme inline')).toContain(`--color-${name}: var(--${name});`)
})

const SLOTS = ['1', '2', '3', '4', '5', '6', '7', '8']

// The categorical colours are eight distinct hues in each theme, not the neutral greys.
test('the_eight_chart_colours_are_distinct_hues_in_each_theme', () => {
  for (const theme of [':root', '.dark']) {
    const values = SLOTS.map((n) => new RegExp(`--chart-${n}: ([^;]+);`).exec(block(theme))?.[1])
    expect(values.every((v) => v !== undefined && !/oklch\([\d.]+ 0 0\)/.test(v))).toBe(true)
    expect(new Set(values).size).toBe(8)
  }
  for (const n of SLOTS) {
    expect(block('@theme inline')).toContain(`--color-chart-${n}: var(--chart-${n});`)
  }
})

// Each column's dot is its own hue; a released ticket, no longer on the board, is muted.
test('each_column_has_its_own_dot_colour', () => {
  const columns = STAGES.map((s) => STAGE_DOT[s])

  expect(new Set(columns).size).toBe(columns.length)
  expect(STAGE_DOT.released).toBe('bg-muted-foreground')
})

// A label's dot takes one of the eight categorical hues.
test('labels_take_the_eight_categorical_colours', () => {
  expect([...LABEL_COLORS]).toEqual(SLOTS.map((n) => `bg-chart-${n}`))
})

// WCAG 2.2 contrast between theme tokens. A colour is read from the theme as the browser draws
// it: OKLCH (or hex) to sRGB, an alpha colour composited over its surface in sRGB, then relative
// luminance. The conversion follows the OKLab definition and WCAG's luminance formula.
type Rgb = [number, number, number]

const toLinear = (c: number): number => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
const toGamma = (c: number): number => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055)
const clamp = (c: number): number => Math.min(1, Math.max(0, c))

function oklchToRgb(l: number, c: number, h: number): Rgb {
  const a = c * Math.cos((h * Math.PI) / 180)
  const b = c * Math.sin((h * Math.PI) / 180)
  const l3 = (l + 0.3963377774 * a + 0.2158037573 * b) ** 3
  const m3 = (l - 0.1055613458 * a - 0.0638541728 * b) ** 3
  const s3 = (l - 0.0894841775 * a - 1.291485548 * b) ** 3
  const linear = [
    4.0767416621 * l3 - 3.3077115913 * m3 + 0.2309699292 * s3,
    -1.2684380046 * l3 + 2.6097574011 * m3 - 0.3413193965 * s3,
    -0.0041960863 * l3 - 0.7034186147 * m3 + 1.707614701 * s3,
  ]
  const [r = 0, g = 0, bl = 0] = linear.map((v) => toGamma(clamp(v)))
  return [r, g, bl]
}

/** A colour value as sRGB (0 to 1) and its alpha. */
function parse(value: string): { rgb: Rgb; alpha: number } {
  const hex = /^#([0-9a-f]{6})$/i.exec(value.trim())
  if (hex) {
    const n = Number.parseInt(hex[1] ?? '', 16)
    return { rgb: [(n >> 16) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255], alpha: 1 }
  }
  const ok = /oklch\(([\d.]+) ([\d.]+) ([\d.]+)(?: \/ ([\d.]+)%)?\)/.exec(value)
  if (!ok) throw new Error(`not a colour: ${value}`)
  const alpha = ok[4] === undefined ? 1 : Number(ok[4]) / 100
  return { rgb: oklchToRgb(Number(ok[1]), Number(ok[2]), Number(ok[3])), alpha }
}

const over = (top: Rgb, alpha: number, under: Rgb): Rgb => [
  top[0] * alpha + under[0] * (1 - alpha),
  top[1] * alpha + under[1] * (1 - alpha),
  top[2] * alpha + under[2] * (1 - alpha),
]
const luminance = (rgb: Rgb): number =>
  0.2126 * toLinear(rgb[0]) + 0.7152 * toLinear(rgb[1]) + 0.0722 * toLinear(rgb[2])
const ratio = (a: Rgb, b: Rgb): number => {
  const [x, y] = [luminance(a), luminance(b)]
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05)
}
const token = (theme: string, name: string): string =>
  new RegExp(`--${name}: ([^;]+);`).exec(block(theme))?.[1] ?? ''
/** A token as drawn on a surface token: its alpha, and an extra one (as `bg-x/10`), composited. */
function drawn(theme: string, name: string, surface: string, extra = 1): Rgb {
  const top = parse(token(theme, name))
  return over(top.rgb, top.alpha * extra, parse(token(theme, surface)).rgb)
}

// The contrast helper itself, against WCAG's own reference values.
test('the_contrast_helper_matches_wcag_reference_values', () => {
  const white = parse('#ffffff').rgb
  expect(ratio(white, parse('#000000').rgb)).toBeCloseTo(21, 5)
  expect(ratio(white, parse('#767676').rgb)).toBeCloseTo(4.54, 2)
  expect(ratio(white, parse('oklch(1 0 0)').rgb)).toBeCloseTo(1, 3)
})

// WCAG 1.4.11: a control's border and the focus ring are at least 3:1 against the surface they
// sit on, in both themes.
test.each([':root', '.dark'])('controls_and_the_focus_ring_reach_3_to_1_in_%s', (theme) => {
  for (const surface of ['background', 'card']) {
    const ground = parse(token(theme, surface)).rgb
    expect(
      ratio(drawn(theme, 'input', surface), ground),
      `input on ${surface}`,
    ).toBeGreaterThanOrEqual(3)
    expect(
      ratio(drawn(theme, 'ring', surface), ground),
      `ring on ${surface}`,
    ).toBeGreaterThanOrEqual(3)
  }
})

// WCAG 1.4.3: muted text is at least 4.5:1 on the page, a card and a muted surface.
test.each([':root', '.dark'])('muted_text_reaches_4_5_to_1_in_%s', (theme) => {
  for (const surface of ['background', 'card', 'muted']) {
    const text = drawn(theme, 'muted-foreground', surface)
    expect(ratio(text, parse(token(theme, surface)).rgb), surface).toBeGreaterThanOrEqual(4.5)
  }
})

test.each([':root', '.dark'])('sidebar_labels_and_focus_are_readable_in_%s', (theme) => {
  for (const surface of ['sidebar', 'sidebar-accent']) {
    const ground = parse(token(theme, surface)).rgb
    expect(ratio(drawn(theme, 'sidebar-foreground', surface, 0.7), ground)).toBeGreaterThanOrEqual(
      4.5,
    )
    expect(ratio(drawn(theme, 'sidebar-ring', surface), ground)).toBeGreaterThanOrEqual(3)
  }
  expect(
    ratio(
      parse(token(theme, 'sidebar-accent-foreground')).rgb,
      parse(token(theme, 'sidebar-accent')).rgb,
    ),
  ).toBeGreaterThanOrEqual(4.5)
})

// A red badge is red text on a red wash (`bg-destructive/10`, `/20` in dark) over a card; the text
// is at least 4.5:1 on that wash, as the other status colours are.
test.each([
  [':root', 0.1],
  ['.dark', 0.2],
])('red_badge_text_reaches_4_5_to_1_on_its_wash_in_%s', (theme, wash) => {
  const ground = drawn(theme, 'destructive', 'card', wash)
  expect(ratio(drawn(theme, 'destructive', 'card'), ground)).toBeGreaterThanOrEqual(4.5)
})

// A status badge is a neutral outlined pill with a dot in the tone's colour and
// the word in the text colour; only destructive keeps its red tint, so a failure stands out.
test.each(['success', 'warning', 'info'] as const)(
  'the_%s_badge_is_a_neutral_outline_with_a_coloured_dot',
  (tone) => {
    const look = badgeVariants({ variant: tone }).split(/\s+/)

    expect({
      outline: look.includes('border-border'),
      text: look.includes('text-foreground'),
      dot: look.includes(`before:bg-${tone}`),
      tint: look.some((token) => token.startsWith(`bg-${tone}`)),
    }).toEqual({ outline: true, text: true, dot: true, tint: false })
  },
)

// The theme refresh (owner, 2026-11-24, docs/design.md): one indigo accent as the primary
// and the focus ring in both themes (the ring may be a lighter step of the same hue for 3:1), white on it, cool blue-grey neutrals and a 6 px radius.
const hueOf = (value: string): number =>
  Number(/oklch\([\d.]+ [\d.]+ ([\d.]+)\)/.exec(value)?.[1]) || Number.NaN

test.each([':root', '.dark'])('the_accent_is_one_indigo_with_white_on_it_in_%s', (theme) => {
  const primary = /oklch\(([\d.]+) ([\d.]+) ([\d.]+)\)/.exec(token(theme, 'primary'))
  const hue = Number(primary?.[3])
  const onPrimary = ratio(
    parse(token(theme, 'primary-foreground')).rgb,
    parse(token(theme, 'primary')).rgb,
  )

  expect({
    indigo: Number(primary?.[2]) > 0.1 && hue > 265 && hue < 290,
    ring: Math.abs(hueOf(token(theme, 'ring')) - hue) < 1,
    white: onPrimary >= 4.5,
    cool: /oklch\([\d.]+ 0\.0\d+ 2[6-9]\d/.test(token(theme, 'background')) || theme === ':root',
  }).toEqual({ indigo: true, ring: true, white: true, cool: true })
})

test('the_radius_is_6_px', () => {
  expect(/--radius: ([^;]+);/.exec(block(':root'))?.[1]).toBe('0.375rem')
})

// Headings are Inter set tighter (docs/design.md's type scale): the theme's heading hook, which
// every generated title carries, draws the heading font with a negative tracking.
test('a_heading_is_the_heading_font_set_tighter', () => {
  const rule = /\.cn-font-heading \{([^}]*)\}/.exec(styles)?.[1] ?? ''
  const app = readFileSync(join(import.meta.dirname, 'App.vue'), 'utf8')

  expect({
    font: rule.includes('font-family: var(--font-heading)'),
    tight: /letter-spacing: -0\.\d+em/.test(rule),
    page: /<h1[^>]*class="[^"]*cn-font-heading/.test(app),
  }).toEqual({ font: true, tight: true, page: true })
})
