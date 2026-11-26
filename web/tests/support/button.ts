// shadcn-vue's Button writes `data-variant` only when a variant is passed: a Button with none is
// its `default`, the board's primary action (docs/design.md, Buttons).
export const PRIMARY =
  '[data-slot="button"]:not([data-variant]), [data-slot="button"][data-variant="default"]'

/** The variant a rendered Button draws. */
export function variantOf(
  element: Element | { attributes: (name: string) => string | undefined },
): string {
  const value =
    element instanceof Element
      ? element.getAttribute('data-variant')
      : element.attributes('data-variant')
  return value ?? 'default'
}
