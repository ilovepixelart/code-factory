import { execFileSync } from 'node:child_process'
import { ROOT } from '../e2e/fixtures'

/** Build the app and the release binary, the build the owner runs, before any timing. */
export default function globalSetup(): void {
  execFileSync('pnpm', ['--dir', `${ROOT}/web`, 'build'], { stdio: 'ignore' })
  execFileSync('cargo', ['build', '--quiet', '--release', '--locked', '-p', 'code-factory'], {
    cwd: ROOT,
    stdio: 'inherit',
  })
}
