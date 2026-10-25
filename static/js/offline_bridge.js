/*
 * Ponte entre as telas normais (com internet) e o modo offline.
 *
 * Em toda tela logada:
 *   - guarda a lista minima (clientes, folhas de producao abertas) para a tela offline;
 *   - envia a fila de registros feitos sem internet assim que houver conexao;
 *   - mostra quantos registros estao esperando envio;
 *   - se a internet cair na hora de "Registrar entrada/saida" ou "Salvar item" da producao,
 *     guarda o registro no aparelho em vez de mostrar erro;
 *   - ao sair da conta, apaga a lista guardada (a fila pendente continua ate ser enviada).
 */
(function () {
  "use strict";
  var api = window.HoraCertaOffline;
  var userId = document.body.getAttribute("data-user-id") || "";
  if (!api || !userId) return;

  var banner = document.createElement("div");
  banner.className = "hc-offline-banner";
  banner.setAttribute("role", "status");
  banner.hidden = true;
  document.body.appendChild(banner);

  function showBanner(text, kind) {
    banner.textContent = text;
    banner.className = "hc-offline-banner" + (kind ? " is-" + kind : "");
    banner.hidden = !text;
  }

  function refreshBanner(extra) {
    return api.pending(userId).then(function (items) {
      var waiting = items.filter(function (i) { return !i.last_error; }).length;
      var failed = items.length - waiting;
      if (extra) return showBanner(extra, "ok");
      if (failed) return showBanner(failed + " registro(s) feito(s) sem internet não foram aceitos. Abra o modo offline para ver o motivo.", "warn");
      if (waiting) return showBanner(waiting + " registro(s) feito(s) sem internet aguardando envio" + (navigator.onLine ? "..." : ". Enviaremos quando a internet voltar."), navigator.onLine ? "" : "warn");
      showBanner("");
    });
  }

  function trySync() {
    return api.sync(userId).then(function (res) {
      if (res && res.sent) {
        refreshBanner(res.sent + " registro(s) feito(s) sem internet enviado(s).");
        setTimeout(function () { refreshBanner(); }, 6000);
      } else {
        refreshBanner();
      }
    });
  }

  api.onChange(function () { refreshBanner(); });
  api.refreshProfile().then(function (data) {
    if (data && data.user_id !== userId) api.clearProfile();
  });
  trySync();
  window.addEventListener("online", trySync);
  window.addEventListener("offline", function () { refreshBanner(); });
  setInterval(function () { api.pending(userId).then(function (items) { if (items.length && navigator.onLine) trySync(); }); }, 60000);

  // Registrar entrada/saida sem internet: guarda no aparelho com o horario do toque.
  var punchForm = document.getElementById("hcPunchForm");
  if (punchForm) {
    punchForm.addEventListener("submit", function (event) {
      if (navigator.onLine) return;
      event.preventDefault();
      var contract = (punchForm.querySelector("[name=contract]") || {}).value;
      api.enqueue({ kind: "punch", user_id: userId, contract_id: contract, occurred_at: new Date().toISOString() })
        .then(function () { showBanner("Sem internet: horário guardado no aparelho. Enviaremos quando a conexão voltar.", "warn"); });
    }, true);
  }

  // Item da producao sem internet.
  var entryForm = document.getElementById("new-entry");
  var sheetId = entryForm && entryForm.getAttribute("data-sheet-id");
  if (entryForm && sheetId) {
    entryForm.addEventListener("submit", function (event) {
      if (navigator.onLine) return;
      event.preventDefault();
      var fields = {};
      ["work_date", "item_code", "quantity", "destination", "start_time", "end_time", "duration", "note"].forEach(function (name) {
        var el = entryForm.querySelector("[name=" + name + "]" + (name === "destination" ? ":checked" : ""));
        fields[name] = el ? el.value : "";
      });
      api.enqueue({ kind: "production_entry", user_id: userId, sheet_id: sheetId, fields: fields, occurred_at: new Date().toISOString() })
        .then(function () {
          entryForm.reset();
          showBanner("Sem internet: item guardado no aparelho. Enviaremos quando a conexão voltar.", "warn");
        });
    }, true);
  }

  // Sair da conta: apaga a lista guardada para a proxima pessoa nao ver.
  document.querySelectorAll('a[href$="/logout/"]').forEach(function (link) {
    link.addEventListener("click", function () { api.clearProfile(); });
  });
})();
