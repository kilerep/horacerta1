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

  function current() {
    return navigator.serviceWorker.ready.then(function (reg) { return reg.pushManager.getSubscription(); });
  }

  current().then(function (sub) {
    show(!!sub);
    if (sub) say("Avisos ativos neste aparelho.");
    else if (Notification.permission === "denied") say("Os avisos estão bloqueados neste aparelho. Libere nas configurações do navegador para o HoraCerta.");
  });

  btnOn.addEventListener("click", function () {
    btnOn.disabled = true;
    say("Toque em Permitir na pergunta do celular.");
    Notification.requestPermission().then(function (perm) {
      if (perm !== "granted") throw new Error("Permissão não concedida. Libere as notificações do HoraCerta nas configurações do navegador.");
      return navigator.serviceWorker.ready;
    }).then(function (reg) {
      return reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(key) });
    }).then(function (sub) {
      return post(panel.getAttribute("data-push-subscribe"), sub.toJSON());
    }).then(function () {
      show(true);
      say("Avisos ativos neste aparelho.");
    }).catch(function (err) {
      say(err.message || "Não foi possível ativar os avisos.");
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
      say(j.sent ? "Aviso de teste enviado. Ele deve aparecer em alguns segundos." : "Nenhum aparelho recebeu. Desligue e ative os avisos de novo.");
    }).catch(function () {
      say("Não foi possível enviar o aviso de teste.");
    }).then(function () { btnTry.disabled = false; });
  });
})();
