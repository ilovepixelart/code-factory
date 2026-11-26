// What the shell offers the parts it holds: the sidebar's quick actions and the command menu's
// actions reach the overlays and the theme the shell owns through this one key.
import type { InjectionKey } from 'vue'

export interface Shell {
  /** Opens the command menu. */
  search: () => void
  /** Opens New ticket. */
  newTicket: () => void
  /** Opens the shortcut sheet. */
  shortcuts: () => void
  /** Switches between the light and the dark theme. */
  toggleTheme: () => void
}

export const SHELL: InjectionKey<Shell> = Symbol('shell')
