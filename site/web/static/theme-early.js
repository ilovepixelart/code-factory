// Dark unless the visitor chose light, applied before paint so the page never flashes light
// first. A file, not an inline script, so a policy of script-src 'self' serves it.
;(function () {
  var saved = null
  try {
    saved = localStorage.codeFactoryTheme
  } catch {
    saved = null
  }
  if (saved !== 'light') document.documentElement.classList.add('dark')
})()
