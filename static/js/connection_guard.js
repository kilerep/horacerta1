/*
 * Aviso de conexao do HoraCerta (Offline 2.0).
 *
 * Faixa no topo da tela:
 *   - sem internet: fica fixa enquanto durar, dizendo o que continua funcionando;
 *   - internet voltou: mensagem verde por alguns segundos.
 *
 * "Sem conexao" = navigator.onLine === false OU a ultima sonda a /ping/ falhou
 * (Wi-Fi sem internet marca "online", por isso a sonda real).
 *
 * Formularios que ja sabem trabalhar sem internet (registrar entrada/saida e item de
 * producao, marcados com data-offline-ok ou pelos ids abaixo) seguem para a fila do
 * aparelho (offline_bridge.js). Os demais sao segurados com aviso, em vez de deixar
 * a pessoa achar que salvou.
 */
(function () {
  var PING_URL = "/ping/";
  var POLL_MS = 8000;
  var BACK_ONLINE_MS = 5000;
  var BAR_ID = "hcConnectionBanner";
  var OFFLINE_FORMS = "#hcPunchForm, #new-entry, [data-offline-ok]";
  var probeFailed = false;
  var probing = false;
  var wasOffline = false;
  var hideTimer = null;

  var body = document.body;
  var logged = body && body.getAttribute("data-authenticated") === "true";
  var MSG_OFFLINE = logged
    ? "Sem internet. Registrar horário e produção continuam funcionando: ficam guardados no celular e são enviados sozinhos quando a conexão voltar."
    : "Sem internet. Esta página precisa de conexão para enviar informações.";
  var MSG_BLOCKED = "Esta ação precisa de internet. Seus dados na tela continuam aqui; tente de novo quando a conexão voltar.";
  var MSG_BACK = "Conectado de novo. Tudo funcionando normalmente.";

  function isOffline() {
    return navigator.onLine === false || probeFailed;
  }

  function bar() {
    var el = document.getElementById(BAR_ID);
    if (el) return el;
    el = document.createElement("div");
    el.id = BAR_ID;
    el.setAttribute("role", "status");
    el.setAttribute("aria-live", "polite");
    el.hidden = true;
    el.style.cssText =
      "position:fixed;left:50%;transform:translateX(-50%);top:calc(10px + env(safe-area-inset-top, 0px));z-index:2400;" +
      "width:min(560px, calc(100% - 24px));box-sizing:border-box;padding:10px 14px 10px 38px;border-radius:14px;" +
      "font-size:13px;line-height:1.4;font-weight:600;box-shadow:0 12px 28px rgba(3,7,20,.35);";
    var dot = document.createElement("span");
    dot.setAttribute("aria-hidden", "true");
    dot.style.cssText = "position:absolute;left:14px;top:50%;width:12px;height:12px;margin-top:-6px;border-radius:999px;";
    var text = document.createElement("span");
    text.setAttribute("data-text", "");
    el.appendChild(dot);
    el.appendChild(text);
    document.body.appendChild(el);
    return el;
  }

  function show(kind, message) {
    var el = bar();
    var offline = kind === "offline" || kind === "blocked";
    el.style.border = "1px solid " + (offline ? "#f59e0b" : "#22c55e");
    el.style.background = offline ? "#451a03" : "#052e16";
    el.style.color = offline ? "#fef3c7" : "#dcfce7";
    el.firstChild.style.background = offline ? "#f59e0b" : "#22c55e";
    el.lastChild.textContent = message;
    el.setAttribute("data-state", kind);
    el.hidden = false;
    document.documentElement.classList.toggle("hc-is-offline", offline);
  }

  function hide() {
    var el = document.getElementById(BAR_ID);
    if (el) el.hidden = true;
    document.documentElement.classList.remove("hc-is-offline");
  }

  function render() {
    if (hideTimer) { clearTimeout(hideTimer); hideTimer = null; }
    if (isOffline()) {
      wasOffline = true;
      show("offline", MSG_OFFLINE);
      return;
    }
    if (wasOffline) {
      wasOffline = false;
      show("online", MSG_BACK);
      hideTimer = setTimeout(hide, BACK_ONLINE_MS);
      try { window.dispatchEvent(new CustomEvent("hc:back-online")); } catch (e) {}
      return;
    }
    var el = document.getElementById(BAR_ID);
    if (el && el.getAttribute("data-state") !== "online") hide();
  }

  function probe() {
    if (probing) return Promise.resolve();
    probing = true;
    var controller = "AbortController" in window ? new AbortController() : null;
    var timer = controller ? setTimeout(function () { controller.abort(); }, 5000) : null;
    return fetch(PING_URL + "?t=" + Date.now(), {
      cache: "no-store",
      credentials: "omit",
      signal: controller ? controller.signal : undefined,
    })
      .then(function (response) { probeFailed = !(response.ok || response.status === 204); })
      .catch(function () { probeFailed = true; })
      .then(function () {
        probing = false;
        if (timer) clearTimeout(timer);
        render();
      });
  }

  // Captura no document: roda antes dos outros handlers do formulario.
  document.addEventListener(
    "submit",
    function (event) {
      var form = event.target;
      if (!form || !form.method || form.method.toLowerCase() !== "post") return;
      if (!isOffline()) return;
      if (form.matches && form.matches(OFFLINE_FORMS)) return; // vai para a fila do aparelho
      event.preventDefault();
      event.stopImmediatePropagation();
      show("blocked", MSG_BLOCKED);
      probe();
    },
    true
  );

  window.addEventListener("offline", function () { probeFailed = true; render(); });
  window.addEventListener("online", probe);
  window.addEventListener("pageshow", function () { if (!document.hidden) probe(); });
  setInterval(function () {
    // so sonda enquanto esta sem conexao (para notar a volta)
    if (!document.hidden && isOffline()) probe();
  }, POLL_MS);

  window.HoraCertaNet = { isOffline: isOffline, probe: probe };
  render();
})();
