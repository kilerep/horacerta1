(function () {
  if (!("serviceWorker" in navigator)) return;

  var TOAST_ID = "hcPwaToast";
  var userRequestedUpdate = false;

  function ensureToast() {
    var existing = document.getElementById(TOAST_ID);
    if (existing) return existing;

    var toast = document.createElement("div");
    toast.id = TOAST_ID;
    toast.setAttribute("role", "status");
    toast.setAttribute("aria-live", "polite");
    toast.style.cssText =
      "position:fixed;left:12px;right:12px;bottom:14px;z-index:2200;padding:10px 12px;" +
      "border-radius:12px;border:1px solid var(--border-brand);background:rgba(16,24,46,.94);" +
      "color:rgba(255,255,255,.94);font-size:13px;line-height:1.35;" +
      "box-shadow:0 12px 28px rgba(3,7,20,.4);display:none";
    document.body.appendChild(toast);
    return toast;
  }

  function showToast(message, action) {
    var toast = ensureToast();
    toast.textContent = message;

    if (action) {
      var button = document.createElement("button");
      button.type = "button";
      button.textContent = action.label;
      button.style.cssText =
        "margin-left:10px;padding:5px 10px;border-radius:8px;border:0;font-weight:700;cursor:pointer";
      button.addEventListener("click", action.run);
      toast.appendChild(button);
    }

    toast.style.display = "block";
    clearTimeout(window.__hcPwaToastTimeout__);
    if (!action) {
      window.__hcPwaToastTimeout__ = setTimeout(function () {
        toast.style.display = "none";
      }, 3200);
    }
  }

  // A atualização NÃO recarrega a página sozinha: recarregar no meio de um
  // formulário perderia o que a pessoa digitou. Só depois do clique em "Atualizar".
  function offerUpdate(worker) {
    showToast("Nova versão do HoraCerta disponível.", {
      label: "Atualizar",
      run: function () {
        userRequestedUpdate = true;
        worker.postMessage({ type: "SKIP_WAITING" });
      },
    });
  }

  function watchInstalling(registration) {
    var worker = registration.installing;
    if (!worker) return;
    worker.addEventListener("statechange", function () {
      // Com controller ativo, um worker "installed" é uma atualização em espera
      // (o v4 de migração de segurança ativa sozinho e nem chega a este estado).
      if (worker.state === "installed" && navigator.serviceWorker.controller) {
        offerUpdate(worker);
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

        if (registration.waiting && navigator.serviceWorker.controller) {
          offerUpdate(registration.waiting);
        }
        watchInstalling(registration);
        registration.addEventListener("updatefound", function () {
          watchInstalling(registration);
        });
      })
      .catch(function () {
        // Falha silenciosa para nao impactar fluxo principal.
      });
  });

  window.addEventListener("appinstalled", function () {
    showToast("HoraCerta instalado neste dispositivo.");
  });

  navigator.serviceWorker.addEventListener("controllerchange", function () {
    // Só recarrega quando a pessoa pediu a atualização. A troca automática do
    // SW v4 (migração de segurança) vale a partir da próxima navegação.
    if (!userRequestedUpdate) return;
    userRequestedUpdate = false;
    sessionStorage.setItem("hc_pwa_updated", "1");
    window.location.reload();
  });
})();
