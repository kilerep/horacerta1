// Avisos no celular (notificacao push): liga/desliga neste aparelho a partir de Meu perfil.
(function () {
  var panel = document.querySelector("[data-push-panel]");
  if (!panel) return;
  var statusEl = panel.querySelector("[data-push-status]");
  var btnOn = panel.querySelector("[data-push-on]");
  var btnOff = panel.querySelector("[data-push-off]");
  var btnTry = panel.querySelector("[data-push-try]");
  var key = panel.getAttribute("data-push-key");

  function say(text) { if (statusEl) statusEl.textContent = text; }
  function show(on) {
    btnOn.hidden = on;
    btnOff.hidden = !on;
    btnTry.hidden = !on;
  }
  function csrf() {
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }
  function post(url, body) {
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: JSON.stringify(body || {}),
    }).then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || "Falha"); return j; }); });
  }
  // erro ao ativar vai para o registro do servidor (para o suporte enxergar a causa)
  function report(stage, err) {
    try {
      post("/api/push/erro/", {
        stage: stage,
        error: String((err && (err.name + ": " + err.message)) || err).slice(0, 300),
        permission: window.Notification ? Notification.permission : "",
        standalone: !!(window.matchMedia && window.matchMedia("(display-mode: standalone)").matches),
      }).catch(function () {});
    } catch (e) {}
  }
  function keyBytes(base64) {
    var pad = "=".repeat((4 - (base64.length % 4)) % 4);
    var raw = atob((base64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
    var out = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
    return out;
  }

  if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
    btnOn.disabled = true;
    say("Este navegador não aceita avisos. No iPhone, instale o HoraCerta na tela de início e abra por lá.");
    return;
  }

  function sameKey(sub) {
    var k = sub && sub.options && sub.options.applicationServerKey;
    if (!k) return false;
    var a = new Uint8Array(k), b = keyBytes(key);
    if (a.length !== b.length) return false;
    for (var i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
    return true;
  }

  // Inscricao valida = feita com a chave atual do servidor. Uma antiga (de versao
  // anterior do app ou de outra chave) e descartada: o servidor nao consegue usa-la.
  function current() {
    return navigator.serviceWorker.ready.then(function (reg) { return reg.pushManager.getSubscription(); })
      .then(function (sub) {
        if (sub && !sameKey(sub)) return sub.unsubscribe().then(function () { return null; }, function () { return null; });
        return sub;
      });
  }

  current().then(function (sub) {
    if (!sub) {
      show(false);
      if (Notification.permission === "denied") say("Os avisos estão bloqueados neste aparelho. Libere nas configurações do navegador para o HoraCerta.");
      else say("Avisos desligados neste aparelho.");
      return;
    }
    // o aparelho ja aceitou: garante que o servidor conhece este aparelho (reenviar e seguro)
    return post(panel.getAttribute("data-push-subscribe"), sub.toJSON()).then(function () {
      show(true);
      say("Avisos ativos neste aparelho.");
    }, function () {
      show(false);
      say("Não foi possível confirmar os avisos com o servidor. Toque em Ativar de novo.");
    });
  });

  btnOn.addEventListener("click", function () {
    btnOn.disabled = true;
    say("Toque em Permitir na pergunta do celular.");
    Notification.requestPermission().then(function (perm) {
      if (perm !== "granted") throw new Error("Permissão não concedida. Libere as notificações do HoraCerta nas configurações do navegador.");
      return navigator.serviceWorker.ready;
    }).then(function () {
      return current().then(function (old) {
        if (old) return old;
        return navigator.serviceWorker.ready.then(function (reg) {
          return reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(key) });
        });
      });
    }).then(function (sub) {
      return post(panel.getAttribute("data-push-subscribe"), sub.toJSON());
    }).then(function () {
      show(true);
      say("Avisos ativos neste aparelho.");
    }).catch(function (err) {
      report("ativar", err);
      say("Não foi possível ativar: " + (err.message || "erro desconhecido") + ". Já avisamos o suporte.");
    }).then(function () { btnOn.disabled = false; });
  });

  btnOff.addEventListener("click", function () {
    btnOff.disabled = true;
    current().then(function (sub) {
      if (!sub) return null;
      var endpoint = sub.endpoint;
      return sub.unsubscribe().then(function () { return post(panel.getAttribute("data-push-unsubscribe"), { endpoint: endpoint }); });
    }).then(function () {
      show(false);
      say("Avisos desligados neste aparelho.");
    }).catch(function () {
      say("Não foi possível desligar agora. Tente de novo.");
    }).then(function () { btnOff.disabled = false; });
  });

  btnTry.addEventListener("click", function () {
    btnTry.disabled = true;
    post(panel.getAttribute("data-push-test")).then(function (j) {
      if (j.sent) { say("Aviso de teste enviado. Ele deve aparecer em alguns segundos."); return; }
      show(false);
      say("Este aparelho não está ligado no servidor. Toque em Ativar avisos neste aparelho.");
    }).catch(function () {
      say("Não foi possível enviar o aviso de teste.");
    }).then(function () { btnTry.disabled = false; });
  });
})();
