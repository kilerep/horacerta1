(function () {
  if (!("serviceWorker" in navigator)) return;

  var isRefreshing = false;
  var TOAST_ID = "hcPwaToast";

  function ensureToast() {
    var existing = document.getElementById(TOAST_ID);
    if (existing) return existing;

    var toast = document.createElement("div");
    toast.id = TOAST_ID;
    toast.setAttribute("role", "status");
    toast.setAttribute("aria-live", "polite");
    toast.style.position = "fixed";
    toast.style.left = "12px";
    toast.style.right = "12px";
    toast.style.bottom = "14px";
    toast.style.zIndex = "2200";
    toast.style.padding = "10px 12px";
    toast.style.borderRadius = "12px";
    toast.style.border = "1px solid var(--border-brand)";
    toast.style.background = "rgba(16,24,46,.94)";
    toast.style.color = "rgba(255,255,255,.94)";
    toast.style.fontSize = "13px";
    toast.style.lineHeight = "1.35";
    toast.style.boxShadow = "0 12px 28px rgba(3,7,20,.4)";
    toast.style.display = "none";
    document.body.appendChild(toast);
    return toast;
  }

  function showToast(message) {
    var toast = ensureToast();
    toast.textContent = message;
    toast.style.display = "block";
    clearTimeout(window.__hcPwaToastTimeout__);
    window.__hcPwaToastTimeout__ = setTimeout(function () {
      toast.style.display = "none";
    }, 3200);
  }

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
    if (sessionStorage.getItem("hc_pwa_updated") === "1") {
      sessionStorage.removeItem("hc_pwa_updated");
      showToast("Aplicativo atualizado com sucesso.");
    }

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

        if (!navigator.serviceWorker.controller) {
          showToast("Modo offline ativado para uso mais estavel.");
        }
      })
      .catch(function () {
        // Falha silenciosa para nao impactar fluxo principal.
      });
  });

  window.addEventListener("appinstalled", function () {
    showToast("HoraCerta instalado neste dispositivo.");
  });

  navigator.serviceWorker.addEventListener("controllerchange", function () {
    if (isRefreshing) return;
    isRefreshing = true;
    sessionStorage.setItem("hc_pwa_updated", "1");
    window.location.reload();
  });
})();
