// The type scale of docs/design.md: every text size a screen sets belongs to a role, and a
// role is its size with the classes that come with it. A size alone, a size with a line height
// (`text-xs/relaxed`) or an arbitrary size is a breach; `text-sm` is the text of every screen.

const SIZE =
  /(?:^|\s)((?:[\w@[\]/-]+:)*)text-(xs|base|lg|xl|2xl|3xl|4xl|5xl|\[[^\]]+\])(\/[\w.-]+)?(?=\s|$)/g

const ROLES: Record<string, string[][]> = {
  // a group label; code shown as a block
  xs: [['font-medium', 'tracking-wider', 'text-muted-foreground', 'uppercase'], ['font-mono']],
  // the page title in the site header
  base: [['font-medium']],
  // a document's title; a figure that is missing
  lg: [['font-semibold'], ['font-normal', 'text-muted-foreground']],
  // a figure; in a card it steps up once the card is wide (dashboard-01's section cards)
  '2xl': [['font-semibold', 'tabular-nums']],
}

/** The sizes in one class string that no role accounts for. */
export function typeBreaches(classes: string): string[] {
  const words = new Set(classes.split(/\s+/))
  const breaches: string[] = []
  for (const match of classes.matchAll(SIZE)) {
    const [whole, prefix = '', size = '', leading] = match
    if (prefix === '@[250px]/card:' && size === '3xl') continue
    // A breakpoint may restate the string's own size, as over a component's `md:text-sm`.
    const restated = prefix !== '' && /^(sm|md|lg|xl):$/.test(prefix) && words.has(`text-${size}`)
    if (restated && !leading) continue
    const roles = prefix || leading ? undefined : ROLES[size]
    if (!roles?.some((needs) => needs.every((word) => words.has(word)))) breaches.push(whole.trim())
  }
  return breaches
}

/** The quoted strings of a source that carry a text size: the class strings a template or a script sets. */
export function sizedStrings(source: string): string[] {
  return [...source.matchAll(/(["'`])((?:(?!\1)[^\n])*?\btext-[^"'`\n]*)\1/g)].map(
    (m) => m[2] ?? '',
  )
}
