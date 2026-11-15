// Relatorio de producao: marcar itens e manda-los para um romaneio de envio.
// "Selecionar para romaneio" liga o modo; no computador o botao direito num item faz o mesmo.
(function () {
  var list = document.querySelector("[data-pick-list]");
  var bar = document.querySelector("[data-pickbar]");
  if (!list || !bar) return;

  var toggle = list.querySelector("[data-select-toggle]");
  var hint = list.querySelector("[data-select-hint]");
  var count = bar.querySelector("[data-pick-count]");
  var submit = bar.querySelector("[data-pick-submit]");
  var cancel = bar.querySelector("[data-select-cancel]");
  var active = false;

  function boxes() {
    return Array.prototype.slice.call(list.querySelectorAll("input[name=entry]"));
  }

  function refresh() {
    var n = boxes().filter(function (box) { return box.checked; }).length;
    count.textContent = n === 1 ? "1 item" : n + " itens";
    submit.disabled = n === 0;
    list.querySelectorAll("[data-pick-row]").forEach(function (row) {
      row.classList.toggle("is-picked", row.querySelector("input").checked);
    });
  }

  function setMode(on) {
    active = on;
    list.classList.toggle("is-picking", on);
    bar.hidden = !on;
    if (hint) hint.hidden = !on;
    list.querySelectorAll(".prod-pick").forEach(function (label) { label.hidden = !on; });
    if (toggle) toggle.textContent = on ? "Selecionando..." : "Selecionar para romaneio";
    if (!on) boxes().forEach(function (box) { box.checked = false; });
    refresh();
  }

  if (toggle) toggle.addEventListener("click", function () { setMode(!active); });
  cancel.addEventListener("click", function () { setMode(false); });
  list.addEventListener("change", refresh);

  list.querySelectorAll("[data-pick-row]").forEach(function (row) {
    var box = row.querySelector("input[name=entry]");
    var link = row.querySelector("a");
    // No modo de selecao, tocar no item marca/desmarca em vez de abrir a edicao.
    link.addEventListener("click", function (event) {
      if (!active) return;
      event.preventDefault();
      box.checked = !box.checked;
      refresh();
    });
    // Botao direito (computador) ou toque longo que gere contextmenu: entra no modo com o item marcado.
    row.addEventListener("contextmenu", function (event) {
      event.preventDefault();
      if (!active) setMode(true);
      box.checked = true;
      refresh();
      submit.focus();
    });
  });
})();
