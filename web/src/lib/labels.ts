import { inject } from 'vue'
import { LABEL_COLORS, labelColor } from './format'
import { BOARD } from './live'

/**
 * A label's dot colour on this board (CF-1079): the board's labels in name order take the colours
 * in turn, so up to eight never share one; a label the board does not list keeps `labelColor`.
 */
export function useLabelColor(): (name: string) => string {
  const live = inject(BOARD, undefined)
  return (name: string) => {
    const all = [
      ...new Set((live?.board.value?.options.label ?? []).map((l) => l.trim().toLowerCase())),
    ].sort()
    const index = all.indexOf(name.trim().toLowerCase())
    return index < 0
      ? labelColor(name)
      : (LABEL_COLORS[index % LABEL_COLORS.length] ?? labelColor(name))
  }
}
