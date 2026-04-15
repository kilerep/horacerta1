(function () {
  if (!("serviceWorker" in navigator)) return;

  var isRefreshing = false;

  function handleWaitingWorker(registration) {
    if (!registration || !registration.waiting) return;
    registration.waiting.postMessage({ type: "SKIP_WAITING" });
  }

  function trackInstallingWorker(registration) {
    if (!registration || !registration.installing) return;
    registration.installing.addEventListener("statechange", function () {
      if (registration.installing && registration.installing.state === "installed" && navigator.serviceWorker.controller) {
        handleWaitingWorker(registration);
      }
    });
  }

  window.addEventListener("load", function () {
    navigator.serviceWorker
      .register("/sw.js", { scope: "/" })
      .then(function (registration) {
        registration.update();
        setInterval(function () {
          registration.update();
        }, 60 * 60 * 1000);

        handleWaitingWorker(registration);
        trackInstallingWorker(registration);
        registration.addEventListener("updatefound", function () {
          trackInstallingWorker(registration);
        });
      })
      .catch(function () {
        // Falha silenciosa para nao impactar fluxo principal.
      });
  });

  navigator.serviceWorker.addEventListener("controllerchange", function () {
    if (isRefreshing) return;
    isRefreshing = true;
    window.location.reload();
  });
})();
