(function () {
  var STORAGE_KEY = "hc_theme";
  var THEMES = ["executive-blue", "graphite-premium", "corporate-light-blue"];

  function isValidTheme(theme) {
    return THEMES.indexOf(theme) !== -1;
  }

  function canUseCustomThemes() {
    var body = document.body;
    if (!body) return true;
    var flag = (body.getAttribute("data-can-custom-themes") || "1").trim();
    return flag !== "0";
  }

  function getLockedTheme() {
    var body = document.body;
    if (!body) return "executive-blue";

    var defaultTheme = (body.getAttribute("data-default-theme") || "").trim();
    if (isValidTheme(defaultTheme)) return defaultTheme;

    var inlineTheme = (body.getAttribute("data-theme") || "").trim();
    if (isValidTheme(inlineTheme)) return inlineTheme;

    return "executive-blue";
  }

  function getInitialTheme() {
    var body = document.body;
    if (!body) return "executive-blue";
    if (!canUseCustomThemes()) return getLockedTheme();

    var persisted = "";
    try {
      persisted = localStorage.getItem(STORAGE_KEY) || "";
    } catch (_err) {
      persisted = "";
    }
    if (isValidTheme(persisted)) return persisted;

    // Future-ready hooks: backend can set company/user preference via data attrs.
    var userTheme = (body.getAttribute("data-theme-user") || "").trim();
    if (isValidTheme(userTheme)) return userTheme;

    var companyTheme = (body.getAttribute("data-theme-company") || "").trim();
    if (isValidTheme(companyTheme)) return companyTheme;

    var defaultTheme = (body.getAttribute("data-default-theme") || "").trim();
    if (isValidTheme(defaultTheme)) return defaultTheme;

    var inlineTheme = (body.getAttribute("data-theme") || "").trim();
    if (isValidTheme(inlineTheme)) return inlineTheme;

    return "executive-blue";
  }

  function applyTheme(theme) {
    if (!isValidTheme(theme)) return;
    if (!canUseCustomThemes()) theme = getLockedTheme();

    document.documentElement.setAttribute("data-theme", theme);
    document.body.setAttribute("data-theme", theme);

    var metaTheme = document.querySelector('meta[name="theme-color"]');
    if (metaTheme) {
      var currentPrimary = getComputedStyle(document.body).getPropertyValue("--color-primary").trim();
      if (currentPrimary) metaTheme.setAttribute("content", currentPrimary);
    }

    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch (_err) {
      // Ignore if storage is blocked
    }

    var controls = document.querySelectorAll("[data-theme-control]");
    for (var i = 0; i < controls.length; i += 1) {
      if (controls[i].value !== theme) controls[i].value = theme;
    }
  }

  function bindControls() {
    var controls = document.querySelectorAll("[data-theme-control]");
    if (!canUseCustomThemes()) {
      var lockedTheme = getLockedTheme();
      for (var i = 0; i < controls.length; i += 1) {
        controls[i].value = lockedTheme;
        controls[i].setAttribute("disabled", "disabled");
      }
      return;
    }

    for (var i = 0; i < controls.length; i += 1) {
      controls[i].addEventListener("change", function (event) {
        applyTheme((event.target.value || "").trim());
      });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var theme = getInitialTheme();
    applyTheme(theme);
    bindControls();
  });
})();
