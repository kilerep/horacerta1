/*
 * Aviso de conexão do HoraCerta.
 *
 * Não existe fila offline: um horário/registro só vale depois que o servidor
 * confirma. Então, quando sabemos que estamos sem conexão, avisamos e seguramos
 * o envio de formulários (POST) em vez de deixar a pessoa achar que salvou.
 *
 * "Sem conexão" aqui = navigator.onLine === false OU a última sonda a /ping/
 * falhou. navigator.onLine sozinho não basta (Wi-Fi sem internet marca "online"),
 * por isso a sonda real. Se a queda acontecer no meio de um envio, o service
 * worker mostra a página "Não foi possível salvar".
 */
(function () {
  var PING_URL = "/ping/";
  var POLL_MS = 8000;
  var BANNER_ID = "hcConnectionBanner";
  var probeFailed = false;
  var probing = false;

  function isOffline() {
    return navigator.onLine === false || probeFailed;
  }

  function ensureBanner() {
    var banner = document.getElementById(BANNER_ID);
    if (banner) return banner;

    banner = document.createElement("div");
    banner.id = BANNER_ID;
    banner.setAttribute("role", "status");
    banner.setAttribute("aria-live", "polite");
    banner.hidden = true;
    banner.style.cssText =
      "position:fixed;left:12px;right:12px;bottom:14px;z-index:2300;padding:10px 12px;" +
      "border-radius:12px;border:1px solid #f59e0b;background:#451a03;color:#fef3c7;" +
      "font-size:13px;line-height:1.35;box-shadow:0 12px 28px rgba(3,7,20,.4)";
    banner.textContent =
      "Sem conexão com o HoraCerta. Nada será salvo até a conexão voltar — seus dados na tela continuam aqui.";
    document.body.appendChild(banner);
    return banner;
  }

  function render() {
    ensureBanner().hidden = !isOffline();
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
      .then(function (response) {
        probeFailed = !(response.ok || response.status === 204);
      })
      .catch(function () {
        probeFailed = true;
      })
      .then(function () {
        probing = false;
        if (timer) clearTimeout(timer);
        render();
      });
  }

  // Captura no document: roda antes de qualquer handler do formulário
  // (inclusive form_feedback.js), então o botão não fica travado em "Salvando...".
  document.addEventListener(
    "submit",
    function (event) {
      var form = event.target;
      if (!form || !form.method || form.method.toLowerCase() !== "post") return;
      if (!isOffline()) return;

      event.preventDefault();
      event.stopImmediatePropagation();
      render();
      probe();
    },
    true
  );

  window.addEventListener("offline", function () {
    probeFailed = true;
    render();
  });
  window.addEventListener("online", probe);
  window.addEventListener("pageshow", function () {
    if (!document.hidden) probe();
  });

  setInterval(function () {
    // Só sonda enquanto está sem conexão (para detectar a volta) ou quando o
    // navegador já diz que caiu; online normal não gasta requisição à toa.
    if (!document.hidden && isOffline()) probe();
  }, POLL_MS);

  render();
})();
