/*
 * HoraCerta Offline 2.0 - etapa 3: salvar sem internet.
 *
 * Formularios das telas offline. Cada um guarda a acao na fila do aparelho
 * (HoraCertaOffline.enqueue) com um client_ref unico; quando a internet volta a fila
 * e enviada para /me/offline/sincronizar/ e o servidor aplica com as mesmas regras da
 * tela online (timeclock/offline_actions.py). Reenviar nunca duplica.
 *
 * Um cliente criado offline recebe o id "ref:<client_ref>" nas listas; acoes para ele
 * vao com client_from_ref e o servidor liga as duas coisas na ordem certa.
 */
(function () {
  "use strict";
  var api = window.HoraCertaOffline;

  function esc(text) {
    return String(text == null ? "" : text).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function pad(n) { return String(n).padStart(2, "0"); }
  function today() { var d = new Date(); return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }
  function br(iso) { return iso ? iso.split("-").reverse().join("/") : ""; }

  var STATUS_LABEL = { PLANNED: "Planejado", SENT: "Orçamento enviado", SCHEDULED: "Planejado", IN_PROGRESS: "Em execução",
    FINISHED: "Finalizado", DRAFT: "Rascunho", REPORT_SENT: "Relatório enviado" };

  function pendingOf(state, kind) { return state.pending.filter(function (i) { return i.kind === kind; }); }

  /** Clientes para escolher: os da copia (ativos) + os criados sem internet ainda nao enviados. */
  function clientOptions(state, withCasual) {
    var list = ((state.data && state.data.clients) || []).filter(function (c) { return c.active; })
      .map(function (c) { return { value: c.id, label: c.name }; });
    if (!list.length && state.profile) {
      list = (state.profile.contracts || []).map(function (c) { return { value: c.id, label: c.name }; });
    }
    pendingOf(state, "client_new").forEach(function (i) {
      list.push({ value: "ref:" + i.client_ref, label: i.name + " (novo, guardado no celular)" });
    });
    var html = list.map(function (o) { return '<option value="' + esc(o.value) + '">' + esc(o.label) + "</option>"; }).join("");
    return (withCasual ? '<option value="">Cliente avulso (digitar nome)</option>' : "") + html;
  }

  function clientRef(value) {
    if (!value) return {};
    return value.indexOf("ref:") === 0 ? { client_from_ref: value.slice(4) } : { contract_id: value };
  }

  function clientName(state, item) {
    if (item.client_from_ref) {
      var n = pendingOf(state, "client_new").filter(function (i) { return i.client_ref === item.client_from_ref; })[0];
      return n ? n.name : "cliente novo";
    }
    var id = item.contract_id;
    var c = ((state.data && state.data.clients) || []).concat((state.profile && state.profile.contracts) || [])
      .filter(function (x) { return x.id === id; })[0];
    return c ? c.name : (item.manual_client_name || "cliente");
  }

  // ---------- formularios ----------
  function field(label, html) { return "<div><label>" + label + "</label>" + html + "</div>"; }

  function registrarExtras(state) {
    var times = [0, 1, 2, 3].map(function (n) {
      return '<input type="time" name="t' + n + '" aria-label="Horário ' + (n + 1) + '">';
    }).join("");
    return '<section class="card"><div class="head"><div><h2>Horário manual de hoje</h2><p>Para quando esqueceu de registrar na hora. Só vale para hoje.</p></div></div>' +
      '<form data-offline-form="manual_punch" class="stack">' +
      field("Cliente", '<select name="client" required>' + clientOptions(state) + "</select>") +
      '<div><label>Horários (entrada, saída, entrada, saída)</label><div class="row4">' + times + "</div></div>" +
      field("Observação", '<input name="note" maxlength="200" placeholder="Ex.: esqueci de registrar a saída">') +
      '<button type="submit">Guardar horários de hoje</button></form></section>' +
      '<section class="card"><div class="head"><div><h2>Folga ou feriado</h2><p>Marca o dia para não aparecer como dia incompleto.</p></div></div>' +
      '<form data-offline-form="day_off" class="stack"><div class="row">' +
      field("Dia", '<input type="date" name="date" required value="' + today() + '">') +
      field("Tipo", '<select name="off_kind"><option value="FOLGA">Folga</option><option value="FERIADO">Feriado</option></select>') +
      "</div>" + field("Observação", '<input name="note" maxlength="80" placeholder="Ex.: feriado municipal">') +
      '<button type="submit">Guardar folga/feriado</button></form></section>';
  }

  function clientForm() {
    return '<details class="card"><summary><b>+ Novo cliente</b></summary><form data-offline-form="client_new" class="stack">' +
      field("Nome do cliente", '<input name="name" required maxlength="120" placeholder="Ex.: Condomínio Aurora">') +
      '<div class="row">' + field("Valor por hora (R$)", '<input name="hourly_rate" inputmode="decimal" placeholder="Ex.: 85,00">') +
      field("WhatsApp", '<input name="whatsapp" inputmode="tel" placeholder="Opcional">') + "</div>" +
      '<button type="submit">Guardar cliente</button></form></details>';
  }

  function pendingClientsRows(state) {
    return pendingOf(state, "client_new").map(function (i) {
      return '<li><div><b>' + esc(i.name) + '</b> <span class="tag warn">guardado no celular</span><small>' +
        (i.hourly_rate ? "R$ " + esc(i.hourly_rate) + "/h" : "sem valor/hora") + "</small></div></li>";
    }).join("");
  }

  function serviceForm(state) {
    var cats = ((state.data && state.data.categories) || []).map(function (c) {
      return '<option value="' + esc(c.id) + '">' + esc(c.name) + "</option>";
    }).join("");
    return '<details class="card"><summary><b>+ Novo serviço</b></summary><form data-offline-form="service_new" class="stack">' +
      field("O que vai ser feito", '<input name="title" required maxlength="140" placeholder="Ex.: Troca de chuveiro">') +
      field("Cliente", '<select name="client">' + clientOptions(state, true) + "</select>") +
      field("Nome do cliente avulso", '<input name="manual_client_name" maxlength="120" placeholder="Só se for cliente avulso">') +
      field("Categoria", '<select name="category" required>' + cats + "</select>") +
      '<div class="row">' + field("Dia", '<input type="date" name="date" required value="' + today() + '">') +
      field("Horário", '<input type="time" name="start">') + "</div>" +
      field("Endereço", '<input name="location" maxlength="140" placeholder="Rua, número, bairro">') +
      field("Descrição", '<textarea name="description" rows="2" placeholder="Detalhes do que vai ser feito"></textarea>') +
      '<p class="sub">Com endereço e descrição o serviço já entra como Planejado; sem eles, como Rascunho.</p>' +
      '<button type="submit">Guardar serviço</button></form></details>';
  }

  function reportForm() {
    return '<details class="card"><summary><b>+ Rascunho de relatório de serviço</b></summary><form data-offline-form="report_draft" class="stack">' +
      field("Título", '<input name="title" required maxlength="140" placeholder="Ex.: Manutenção do quadro elétrico">') +
      '<div class="row">' + field("Cliente / empresa", '<input name="client_name" required maxlength="140">') +
      field("Serviço realizado", '<input name="service_name" required maxlength="160">') + "</div>" +
      '<div class="row">' + field("De", '<input type="date" name="date_from" value="' + today() + '">') +
      field("Até", '<input type="date" name="date_to" value="' + today() + '">') + "</div>" +
      field("Atividades realizadas", '<textarea name="activities" rows="4"></textarea>') +
      field("Observações e pendências", '<textarea name="observations" rows="3"></textarea>') +
      field("Conclusão", '<textarea name="conclusion" rows="2"></textarea>') +
      '<p class="sub">Fica como rascunho. Com internet, confira e emita.</p>' +
      '<button type="submit">Guardar rascunho</button></form></details>';
  }

  function shipmentForm() {
    var row = '<div class="row4 item-row"><input name="order" placeholder="OP" aria-label="Ordem de produção">' +
      '<input name="drawing" placeholder="Nº desenho" aria-label="Número do desenho"><input name="quantity" inputmode="numeric" placeholder="Qtd" aria-label="Quantidade">' +
      '<input name="description" placeholder="Descrição" aria-label="Descrição"></div>';
    return '<details class="card"><summary><b>+ Novo romaneio (rascunho)</b></summary><form data-offline-form="shipment_draft" class="stack">' +
      field("Empresa de destino", '<input name="destination" required maxlength="120">') +
      '<div class="row">' + field("Motorista", '<input name="driver" maxlength="80">') +
      field("Placa", '<input name="plate" maxlength="10">') + "</div>" +
      '<div><label>Itens</label><div class="items">' + row + row + row + '</div><button type="button" class="link" data-add-row>+ mais uma linha</button></div>' +
      '<p class="sub">Fica como rascunho. Com internet, confira e envie para o encarregado.</p>' +
      '<button type="submit">Guardar rascunho</button></form></details>';
  }

  function pendingShipments(state) {
    return pendingOf(state, "shipment_draft").map(function (i) {
      return '<li><div><b>Rascunho · ' + esc(i.destination) + '</b> <span class="tag warn">guardado no celular</span>' +
        i.items.map(function (r) { return "<small>" + esc(r.quantity) + "× " + esc(r.drawing) + "</small>"; }).join("") + "</div></li>";
    }).join("");
  }

  /** Mudanca de etapa do servico ainda nao enviada (a mais recente). */
  function pendingStatus(state, jobId) {
    var list = pendingOf(state, "service_status").filter(function (i) { return i.job_id === jobId; });
    return list.length ? list[list.length - 1] : null;
  }

  function jobActions(state, job) {
    var p = pendingStatus(state, job.id);
    var status = p ? (p.action === "start" ? "IN_PROGRESS" : "FINISHED") : job.status;
    var btn = "";
    if (status === "PLANNED" || status === "SENT" || status === "SCHEDULED") btn = "start";
    else if (status === "IN_PROGRESS") btn = "finish";
    var label = STATUS_LABEL[status] || job.status_label;
    return '<span class="tag' + (p ? " warn" : "") + '">' + esc(label) + (p ? " · no celular" : "") + "</span>" +
      (btn ? '<button type="button" class="mini" data-job-action="' + btn + '" data-job="' + esc(job.id) + '" data-base="' + esc(status) + '">' +
        (btn === "start" ? "Iniciar" : "Finalizar") + "</button>" : "");
  }

  function pendingJobsFor(state, iso) {
    return pendingOf(state, "service_new").filter(function (i) { return i.date === iso; }).map(function (i) {
      return '<li><div><b>' + (i.start ? i.start + " · " : "") + esc(i.title) + "</b><small>" + esc(clientName(state, i)) +
        '</small></div><div class="right"><span class="tag warn">novo · no celular</span></div></li>';
    }).join("");
  }

  /** Texto de cada item na lista "Aguardando envio". */
  function describe(item, state) {
    var when = new Date(item.occurred_at);
    var hm = pad(when.getHours()) + ":" + pad(when.getMinutes());
    switch (item.kind) {
      case "punch": return "Horário " + hm + " · " + clientName(state, item);
      case "production_entry": return "Item " + ((item.fields && item.fields.item_code) || "sem código");
      case "manual_punch": return "Horário manual " + (item.times || []).join(", ") + " · " + clientName(state, item);
      case "day_off": return (item.kind_label || "Folga") + " em " + br(item.date);
      case "client_new": return "Cliente novo · " + item.name;
      case "service_new": return "Serviço novo · " + item.title + " (" + br(item.date) + ")";
      case "service_status": return (item.action === "start" ? "Iniciar" : "Finalizar") + " serviço · " + (item.job_title || "");
      case "shipment_draft": return "Romaneio (rascunho) · " + item.destination;
      case "report_draft": return "Relatório (rascunho) · " + item.title;
      default: return "Registro";
    }
  }

  // ---------- envio dos formularios ----------
  function read(form) {
    var out = {};
    Array.prototype.forEach.call(form.elements, function (el) { if (el.name) out[el.name] = (el.value || "").trim(); });
    return out;
  }

  function build(kind, form, state) {
    var f = read(form);
    var base = { kind: kind, user_id: state.profile.user_id, occurred_at: new Date().toISOString() };
    switch (kind) {
      case "manual_punch": {
        var times = ["t0", "t1", "t2", "t3"].map(function (k) { return f[k]; }).filter(Boolean);
        if (!f.client) return "Escolha o cliente.";
        if (!times.length) return "Informe pelo menos 1 horário.";
        return Object.assign(base, clientRef(f.client), { date: today(), times: times, note: f.note });
      }
      case "day_off":
        if (!f.date) return "Escolha o dia.";
        return Object.assign(base, { date: f.date, off_kind: f.off_kind, kind_label: f.off_kind === "FERIADO" ? "Feriado" : "Folga", note: f.note });
      case "client_new":
        if (!f.name) return "Informe o nome do cliente.";
        return Object.assign(base, { name: f.name, hourly_rate: f.hourly_rate.replace(",", "."), whatsapp: f.whatsapp });
      case "service_new":
        if (!f.title) return "Diga o que vai ser feito.";
        if (!f.client && !f.manual_client_name) return "Escolha o cliente ou digite o nome do cliente avulso.";
        return Object.assign(base, f.client ? clientRef(f.client) : { manual_client_name: f.manual_client_name },
          { title: f.title, category_id: f.category, date: f.date, start: f.start, location: f.location, description: f.description });
      case "report_draft":
        if (!f.title || !f.client_name || !f.service_name) return "Preencha título, cliente e serviço realizado.";
        return Object.assign(base, f);
      case "shipment_draft": {
        if (!f.destination) return "Informe a empresa de destino.";
        var rows = Array.prototype.map.call(form.querySelectorAll(".item-row"), function (r) {
          var v = function (n) { return (r.querySelector('[name="' + n + '"]').value || "").trim(); };
          return { order: v("order"), drawing: v("drawing"), quantity: v("quantity"), description: v("description") };
        }).filter(function (r) { return r.order || r.drawing || r.description; });
        if (rows.some(function (r) { return !r.drawing || !(parseInt(r.quantity, 10) >= 1); })) return "Cada item precisa do nº do desenho e da quantidade.";
        return Object.assign(base, { destination: f.destination, driver: f.driver, plate: f.plate, items: rows });
      }
    }
    return "Formulário desconhecido.";
  }

  var DONE = {
    manual_punch: "Horários de hoje guardados no celular.", day_off: "Folga/feriado guardado no celular.",
    client_new: "Cliente guardado no celular. Já dá para registrar horas e serviços para ele.",
    service_new: "Serviço guardado no celular.", report_draft: "Rascunho de relatório guardado no celular.",
    shipment_draft: "Rascunho de romaneio guardado no celular.", service_status: "Mudança guardada no celular.",
  };

  function attach(getState, notify) {
    document.addEventListener("submit", function (event) {
      var form = event.target.closest && event.target.closest("[data-offline-form]");
      if (!form) return;
      event.preventDefault();
      var state = getState();
      if (!state.profile) return notify("Abra o app uma vez com internet antes de usar sem internet.", "warn");
      var item = build(form.getAttribute("data-offline-form"), form, state);
      if (typeof item === "string") return notify(item, "warn");
      api.enqueue(item).then(function () { form.reset(); notify(DONE[item.kind], "ok"); });
    });
    document.addEventListener("click", function (event) {
      var add = event.target.closest("[data-add-row]");
      if (add) {
        var items = add.parentNode.querySelector(".items");
        items.appendChild(items.firstElementChild.cloneNode(true));
        items.lastElementChild.querySelectorAll("input").forEach(function (i) { i.value = ""; });
        return;
      }
      var act = event.target.closest("[data-job-action]");
      if (!act) return;
      var state = getState();
      var job = ((state.data && state.data.jobs) || []).filter(function (j) { return j.id === act.getAttribute("data-job"); })[0];
      var action = act.getAttribute("data-job-action");
      if (!job || !window.confirm((action === "start" ? "Iniciar" : "Finalizar") + " o serviço \"" + job.title + "\"?")) return;
      api.enqueue({ kind: "service_status", user_id: state.profile.user_id, occurred_at: new Date().toISOString(),
        job_id: job.id, job_title: job.title, action: action, base_status: act.getAttribute("data-base") })
        .then(function () { notify(DONE.service_status, "ok"); });
    });
  }

  window.HoraCertaOfflineForms = {
    registrarExtras: registrarExtras, clientForm: clientForm, pendingClientsRows: pendingClientsRows,
    serviceForm: serviceForm, reportForm: reportForm, shipmentForm: shipmentForm, pendingShipments: pendingShipments,
    jobActions: jobActions, pendingJobsFor: pendingJobsFor, describe: describe, attach: attach,
  };
})();
