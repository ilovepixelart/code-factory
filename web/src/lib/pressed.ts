// Which of several buttons sharing one busy state was pressed, so that only it shows a Spinner
// while the busy state holds.

import { ref } from 'vue'

export interface Pressed {
  /** Note `name` as the pressed button, then run its action; a promise clears it as it ends. */
  press: <T>(name: string, action: () => T) => T
  /** Whether the button `name` shows its Spinner: it was pressed and its change is sent. */
  spins: (name: string, busy: boolean) => boolean
}

export function usePressed(): Pressed {
  const pressed = ref('')
  function press<T>(name: string, action: () => T): T {
    pressed.value = name
    const result = action()
    if (result instanceof Promise) {
      const clear = () => {
        if (pressed.value === name) pressed.value = ''
      }
      void result.then(clear, clear)
    }
    return result
  }
  const spins = (name: string, busy: boolean): boolean => busy && pressed.value === name
  return { press, spins }
}
