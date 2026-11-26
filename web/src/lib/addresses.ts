// The addresses an activity sentence may link (CF-1292): only a pull request of GitHub,
// https://github.com/<owner>/<repo>/pull/<number>, drawn as `#<number>`; never markup.

const PULL = /https:\/\/github\.com\/[\w.-]+\/[\w.-]+\/pull\/(\d+)(?![\w/#?-])/g

/** A piece of a sentence: plain text, or an address to link. */
export interface TextPart {
  text: string
  href: string | null
}

/** `text` cut into its plain pieces and its pull request addresses. */
export function textParts(text: string): TextPart[] {
  const parts: TextPart[] = []
  let from = 0
  for (const found of text.matchAll(PULL)) {
    const at = found.index
    const address = found[0]
    if (at > from) parts.push({ text: text.slice(from, at), href: null })
    parts.push({ text: `#${found[1] ?? ''}`, href: address })
    from = at + address.length
  }
  if (from < text.length) parts.push({ text: text.slice(from), href: null })
  return parts
}
