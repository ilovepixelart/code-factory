import { onUnmounted } from 'vue'

/**
 * For a form that opens from a button: once the form is gone, the keyboard goes back to the
 * control that held it when the form opened, if that control is still on the page and focus has
 * not been moved elsewhere in the meantime. Call it from the form's setup.
 */
export function useReturnFocus(): void {
  const opener = document.activeElement
  onUnmounted(() => {
    const free = !document.activeElement || document.activeElement === document.body
    if (free && opener instanceof HTMLElement && opener !== document.body && opener.isConnected) {
      opener.focus()
    }
  })
}
