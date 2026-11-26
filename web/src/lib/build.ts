// The build this tab runs (CF-1298). The server names the web build it serves on every answer
// (`X-Code-Factory-Build`); the first one seen is the tab's own, and a later one that differs means
// the board was rebuilt and restarted. The tab then offers a reload and loads its next navigation
// afresh; it never reloads by itself, since a form may hold unsaved text.

import { reactive } from 'vue'

export const BUILD_HEADER = 'X-Code-Factory-Build'

/** What the notice says when the tab runs an older build than the board. */
export const UPDATED = 'The board was updated; reload the page to see it.'

export const build = reactive({ stale: false })
let loaded: string | null = null

/** Take the build an answer named: the first is the tab's own, a different later one makes the tab
 *  stale. An answer naming none (the server did not answer) changes nothing. */
export function noteBuild(named: string | null): void {
  if (!named) return
  if (loaded === null) loaded = named
  else if (named !== loaded) build.stale = true
}

/** Forget what was seen, as a test starts. */
export function resetBuild(): void {
  loaded = null
  build.stale = false
}

/** The address a navigation to `fullPath` loads afresh, or null while the tab runs the current build. */
export function freshLoad(fullPath: string): string | null {
  return build.stale ? fullPath : null
}
