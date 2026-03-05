(function () {
  var body = document.body;
  var sidebar = document.getElementById("appSidebar");
  var toggle = document.getElementById("menuToggle");
  var overlay = document.getElementById("sidebarOverlay");
  var mobileQuery = window.matchMedia("(max-width: 900px)");

  if (!body || !sidebar || !toggle || !overlay) {
    return;
  }

  function isMobile() {
    return mobileQuery.matches;
  }

  function closeMenu() {
    body.classList.remove("menu-open");
    toggle.setAttribute("aria-expanded", "false");
  }

  function openMenu() {
    if (!isMobile()) {
      return;
    }
    body.classList.add("menu-open");
    toggle.setAttribute("aria-expanded", "true");
  }

  function toggleMenu() {
    if (!isMobile()) {
      return;
    }
    if (body.classList.contains("menu-open")) {
      closeMenu();
    } else {
      openMenu();
    }
  }

  function syncViewport() {
    if (!isMobile()) {
      closeMenu();
    }
  }

  toggle.addEventListener("click", toggleMenu);
  overlay.addEventListener("click", closeMenu);

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      closeMenu();
    }
  });

  sidebar.addEventListener("click", function (event) {
    var target = event.target;
    if (isMobile() && target && target.closest("a")) {
      closeMenu();
    }
  });

  if (mobileQuery.addEventListener) {
    mobileQuery.addEventListener("change", syncViewport);
  } else if (mobileQuery.addListener) {
    mobileQuery.addListener(syncViewport);
  }

  syncViewport();
})();
