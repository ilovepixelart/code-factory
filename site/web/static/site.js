// The theme toggle and the copy buttons. Handlers are bound here rather than written inline, so
// the page runs under a policy of script-src 'self'.
;(function () {
  var root = document.documentElement
  document.querySelectorAll('[data-theme-toggle]').forEach(function (button) {
    button.addEventListener('click', function () {
      var dark = root.classList.toggle('dark')
      try {
        localStorage.codeFactoryTheme = dark ? 'dark' : 'light'
      } catch {
        // without storage the choice lasts for this page only
      }
    })
  })

  if (!navigator.clipboard) return // the text stays select-all, as it is without script
  document.querySelectorAll('[data-copy]').forEach(function (button) {
    var source = button.parentElement.querySelector('[data-install]')
    button.hidden = false
    button.addEventListener('click', function () {
      navigator.clipboard.writeText(source.textContent).then(
        function () {
          button.textContent = 'copied'
          setTimeout(function () {
            button.textContent = 'copy'
          }, 1500)
        },
        function () {
          window.getSelection().selectAllChildren(source) // a denied clipboard leaves the selection
        },
      )
    })
  })
})()
