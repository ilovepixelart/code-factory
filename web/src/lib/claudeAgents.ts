// Which Claude Code agent files apply when two define one name.

import type { ClaudeAgent } from '../generated/ClaudeAgent'

/** For each file a same-named file shadows, by path, the place of the file that applies: the
 *  closest project folder's (the list is global first, then closest first), else the global one. */
export function overriddenBy(agents: ClaudeAgent[]): Record<string, string> {
  const winner = new Map<string, ClaudeAgent>()
  for (const agent of agents) {
    const held = winner.get(agent.name)
    if (!held || (held.place === 'global' && agent.place !== 'global'))
      winner.set(agent.name, agent)
  }
  const shadowed: Record<string, string> = {}
  for (const agent of agents) {
    const wins = winner.get(agent.name)
    if (wins && wins !== agent) shadowed[agent.path] = wins.place
  }
  return shadowed
}
