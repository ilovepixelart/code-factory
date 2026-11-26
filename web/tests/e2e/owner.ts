// The owner's session every board of the browser tests keeps (`code-factory sample-load` mints it
// from 32 bytes of 0x2a): sent by every browser context as the sign-in cookie
// (playwright.config.ts), so the pages change the board as the owner's signed-in browser does.
export const OWNER_TOKEN = `cfs_${'Kioq'.repeat(10)}Kio`

/** The cookie header a test's own request to a board sends, as the signed-in owner's browser does. */
export const OWNER_COOKIE = `code_factory_owner=${OWNER_TOKEN}`
