// The shape of a source guard (CF-1274): list the `.vue` files, read their opening tags (across
// lines), and compare the offenders with an allowlist that gives a reason per file. A guard fails
// for an offender not on the list and for a listed file that no longer offends, so the list only
// shrinks. A guard test passes its own rule to `offenders` and its list to `verdict`.

import { readFileSync, readdirSync } from 'node:fs'
import { join, relative } from 'node:path'

const SRC = join(import.meta.dirname, '..')

export interface Tag {
  name: string
  text: string
  line: number
}

/** Every `.vue` file under web/src, as a path relative to it, sorted. */
export function vueFiles(folder = SRC): string[] {
  return readdirSync(folder, { withFileTypes: true })
    .flatMap((entry) => {
      const path = join(folder, entry.name)
      if (entry.isDirectory()) return vueFiles(path)
      return entry.name.endsWith('.vue') ? [relative(SRC, path)] : []
    })
    .sort()
}

export const readVue = (file: string): string => readFileSync(join(SRC, file), 'utf8')

/** The opening tags of a template, one per element, even when its attributes span lines. */
export function openingTags(source: string): Tag[] {
  const template = source.replace(/<script\b[\s\S]*?<\/script>/g, (script) =>
    script.replace(/[^\n]/g, ' '),
  )
  const tag = /<([A-Za-z][\w.-]*)((?:[^>"']|"[^"]*"|'[^']*')*)>/g
  return [...template.matchAll(tag)].map((match) => ({
    name: match[1] ?? '',
    text: match[0],
    line: template.slice(0, match.index).split('\n').length,
  }))
}

/** Offending files with what offends in each (`file:line tag`), from a per-tag rule. */
export function offenders(
  files: string[],
  rule: (tag: Tag) => boolean,
  exempt: string[] = [],
): Map<string, string[]> {
  const found = new Map<string, string[]>()
  for (const file of files.filter((f) => !exempt.includes(f))) {
    const hits = openingTags(readVue(file))
      .filter(rule)
      .map((tag) => `${file}:${String(tag.line)} <${tag.name}>`)
    if (hits.length) found.set(file, hits)
  }
  return found
}

/** Offending files from a per-source rule, for what the tags alone do not show (a class in a map). */
export function sourceOffenders(
  files: string[],
  rule: (source: string) => boolean,
  exempt: string[] = [],
): Map<string, string[]> {
  return new Map(
    files
      .filter((file) => !exempt.includes(file) && rule(readVue(file)))
      .map((file) => [file, [file]]),
  )
}

/** What is wrong with the allowlist: a new offender, or a listed file that no longer offends. */
export function verdict(found: Map<string, string[]>, allowed: Record<string, string>): string[] {
  const fresh = [...found.entries()]
    .filter(([file]) => !(file in allowed))
    .map(([, hits]) => `not allowed: ${hits.join(', ')}`)
  const stale = Object.entries(allowed)
    .filter(([file]) => !found.has(file))
    .map(([file, reason]) => `no longer offends, remove it from the list: ${file} (${reason})`)
  return [...fresh, ...stale]
}

const VOID = new Set(['area', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source'])

/** Every opening tag of a template with the name of the element it sits in ('' at the top). */
export function withParents(source: string): (Tag & { parent: string })[] {
  const template = source.replace(/<script\b[\s\S]*?<\/script>/g, (script) =>
    script.replace(/[^\n]/g, ' '),
  )
  const tag = /<(\/?)([A-Za-z][\w.-]*)((?:[^>"']|"[^"]*"|'[^']*')*)>/g
  const open: string[] = []
  const found: (Tag & { parent: string })[] = []
  for (const match of template.matchAll(tag)) {
    const [text, closing = '', name = '', rest = ''] = match
    if (closing) {
      const at = open.lastIndexOf(name)
      if (at >= 0) open.length = at
      continue
    }
    const line = template.slice(0, match.index).split('\n').length
    found.push({ name, text, line, parent: open.at(-1) ?? '' })
    if (!rest.endsWith('/') && !VOID.has(name)) open.push(name)
  }
  return found
}
