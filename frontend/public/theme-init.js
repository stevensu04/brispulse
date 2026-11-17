// Applies the visitor's saved theme before the first paint, so a reload does not flash
// the other theme first. A separate file because the content security policy allows no
// inline scripts. Must stay tiny and must never throw.
(function () {
  try {
    var theme = window.localStorage.getItem("brispulse-theme");
    if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
  } catch (e) {
    // Storage blocked (private browsing): the system theme applies.
  }
})();
