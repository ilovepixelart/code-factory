import type { Icon } from '@/lib/icon'

/** Whether an svg draws this icon of the icon library: its shapes are the icon's own, in order. */
export function draws(svg: Element | null | undefined, icon: Icon): boolean {
  const shapes = [...(svg?.children ?? [])]
  return (
    shapes.length === icon.length &&
    icon.every(([tag, attributes], index) => {
      const shape = shapes[index]
      const d = attributes.d
      return (
        shape?.tagName.toLowerCase() === tag &&
        shape.getAttribute('d') === (d === undefined ? null : String(d))
      )
    })
  )
}
