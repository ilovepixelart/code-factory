import { execFileSync } from 'node:child_process'
import { ROOT } from './fixtures'

/**
 * Build the app once, before any test serves it. `CODE_FACTORY_E2E_BUILT=1` skips it when it is
 * already built, so runs side by side do not rebuild over each other.
 */
export default function globalSetup(): void {
  if (process.env.CODE_FACTORY_E2E_BUILT === '1') return
  execFileSync('pnpm', ['--dir', `${ROOT}/web`, 'build'], { stdio: 'ignore' })
}
