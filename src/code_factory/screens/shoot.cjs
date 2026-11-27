// The browser half of `code-factory shoot`: capture board pages in light and dark at 1600x900
// with scrollbars drawn. Arguments: the board address, the folder, then `<page path> <image stem>
// <section id>` triples, the id empty for the top of the page. Read from standard input, so no
// file another account could plant is run; NODE_PATH finds Playwright in the web app's packages.
let chromium
try {
  ;({ chromium } = require('@playwright/test'))
} catch {
  process.exit(3)
}
const [url, folder, ...triples] = process.argv.slice(2)
const SECTION_MS = 10_000
const VIEW = { width: 1600, height: 900 }

// The board scrolls inside `main` and draws a section after its data arrives: the section is
// waited for and brought to the top; one still out of view fails the capture.
async function showSection(page, path, id) {
  const target = page.locator(`[id="${id}"]`)
  try {
    await target.waitFor({ timeout: SECTION_MS })
  } catch {
    throw new Error(`${path} shows no section with the id ${id}`)
  }
  await target.evaluate((element) => element.scrollIntoView({ block: 'start' }))
  const top = await target.evaluate((element) => element.getBoundingClientRect().top)
  if (top < 0 || top >= VIEW.height) throw new Error(`${path} cannot scroll the section ${id} into view`)
}

// One page after the other: a capture waits for the network and the scroll of its own page.
async function capture(browser, [path, stem, id], theme) {
  const context = await browser.newContext({ viewport: VIEW, colorScheme: theme })
  await context.addCookies([
    { name: 'code_factory_owner', value: process.env.CODE_FACTORY_SHOOT_SESSION ?? '', url },
  ])
  const page = await context.newPage()
  await page.goto(url + path)
  await page.waitForLoadState('networkidle')
  if (id) await showSection(page, path, id)
  await page.screenshot({ path: `${folder}/${stem}-${theme}.png` })
  await context.close()
}

;(async () => {
  const browser = await chromium.launch({ ignoreDefaultArgs: ['--hide-scrollbars'] })
  try {
    const jobs = []
    for (let i = 0; i < triples.length; i += 3) {
      for (const theme of ['light', 'dark']) jobs.push([triples.slice(i, i + 3), theme])
    }
    await jobs.reduce(
      (done, [triple, theme]) => done.then(() => capture(browser, triple, theme)),
      Promise.resolve(),
    )
  } finally {
    await browser.close()
  }
})().catch((error) => {
  process.stderr.write(String(error))
  process.exit(1)
})
