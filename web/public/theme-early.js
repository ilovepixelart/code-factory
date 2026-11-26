// Apply the theme and the sidebar fold before paint: a saved theme wins, otherwise the OS
// preference. A file, since the security policy runs no inline script.
;(function () {
  var saved = null,
    folded = false
  try {
    saved = localStorage.codeFactoryTheme
    folded = localStorage.codeFactorySidebar === 'folded'
  } catch {
    saved = null
  }
  var dark = saved ? saved === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches
  document.documentElement.classList.add(dark ? 'dark' : 'light')
  if (folded) document.documentElement.dataset.sidebar = 'folded'
})()
