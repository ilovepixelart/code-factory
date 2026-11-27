// Exercise the served board, PostgreSQL and real Git. Only the GitHub CLI is substituted.
import { chmodSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { delimiter, join } from 'node:path'
import {
  codeFactory,
  dropSample,
  expect,
  git,
  prepareSample,
  present,
  Served,
  start,
  test,
} from './fixtures'

const JOURNEY_TIMEOUT = 90_000

test('a ticket reaches Merged on the exact commit shipped from Build', async ({ browser }) => {
  test.setTimeout(JOURNEY_TIMEOUT)
  const schema = prepareSample('empty')
  const directory = mkdtempSync(join(tmpdir(), 'factory-journey-'))
  const repo = join(directory, 'journey')
  const origin = join(directory, 'origin.git')
  const env = {
    ...process.env,
    CODE_FACTORY_DB_SCHEMA: schema,
    CODE_FACTORY_STATE_DIR: join(directory, 'state'),
    PATH: [directory, process.env.PATH].join(delimiter),
  }
  let stop: (() => void) | undefined
  try {
    mkdirSync(repo)
    git(directory, 'init', '--bare', '--initial-branch=main', origin)
    git(repo, 'init', '--initial-branch=main')
    mkdirSync(join(repo, '.code-factory'))
    writeFileSync(join(repo, '.code-factory/config.toml'), '[agents]\nship = false\n')
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', 'Initial repository')
    git(repo, 'remote', 'add', 'origin', origin)
    git(repo, 'push', '-u', 'origin', 'main')
    git(repo, 'remote', 'set-head', 'origin', 'main')

    const gh = join(directory, 'gh')
    writeFileSync(
      gh,
      `#!/bin/sh
set -eu
url=https://github.com/example/journey/pull/1
case "$1 $2" in
  'pr list') echo '[]' ;;
  'pr create') echo "$url" ;;
  'pr view')
    head=$(git rev-parse refs/remotes/origin/ticket/cf-1)
    printf '{"url":"%s","number":1,"headRefOid":"%s","baseRefName":"main","state":"OPEN","mergeStateStatus":"CLEAN","isDraft":false,"statusCheckRollup":[]}\\n' "$url" "$head" ;;
  'pr merge')
    test "$3" = "$url" && test "$4" = --merge && test "$5" = --match-head-commit
    test "$6" = "$(git rev-parse refs/remotes/origin/ticket/cf-1)"
    git push origin "$6:refs/heads/main" ;;
  *) exit 1 ;;
esac
`,
    )
    chmodSync(gh, 0o700)
    codeFactory(['track', repo], env)
    codeFactory(['halt'], env)
    const server = await start(schema, { env })
    stop = server.stop
    const served = new Served(server.url, schema)
    const page = await browser.newPage()
    await page.goto(server.url + '/tickets')
    const repos = Promise.withResolvers<boolean>()
    await page.route(
      '**/api/repositories',
      async (route) => {
        await repos.promise
        await route.continue()
      },
      { times: 1 },
    )
    await page.keyboard.press('n')
    const dialog = page.getByRole('dialog', { name: 'New ticket' })
    const created = page.waitForResponse(
      (r) => r.url().endsWith('/api/tickets') && r.request().method() === 'POST',
    )
    await dialog.getByRole('textbox', { name: 'Title', exact: true }).fill('Deliver a release note')
    const create = dialog.getByRole('button', { name: 'Create ticket' })
    try {
      await expect(create).toBeDisabled()
    } finally {
      repos.resolve(true)
    }
    await create.click()
    expect((await created).status()).toBe(201)
    const card = (column: string) =>
      page
        .getByRole('region', { name: column, exact: true })
        .getByRole('link', { name: 'Deliver a release note' })
    await expect(card('Spec')).toBeVisible()
    const tree = present(
      codeFactory(['start', 'CF-1', '--repository', repo], env).trim().split(' on ')[0],
      'Factory worktree path',
    )
    writeFileSync(join(tree, 'release.txt'), 'Ready to ship\n')
    git(tree, 'add', 'release.txt')
    git(tree, 'commit', '-m', 'Write release note')
    const head = git(tree, 'rev-parse', 'HEAD')
    await page.reload()
    await expect(card('Build')).toBeVisible()
    const path = '/api/tickets/journey/CF-1'
    const ship = await served.api('POST', path + '/ship')
    expect(ship, JSON.stringify(ship.json)).toMatchObject({ status: 200 })
    await page.reload()
    await expect(card('Review')).toBeVisible()
    const merge = await served.api('POST', path + '/merge')
    expect(merge, JSON.stringify(merge.json)).toMatchObject({ status: 200 })
    await page.reload()
    await expect(card('Merged')).toBeVisible()
    expect(git(origin, 'rev-parse', 'main')).toBe(head)
    await page.close()
  } finally {
    stop?.()
    dropSample(schema)
    rmSync(directory, { recursive: true, force: true })
  }
})
