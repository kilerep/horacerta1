/*
 * HoraCerta Offline 2.0 - etapa 2: as telas do sistema funcionando sem internet.
 *
 * Roda dentro de /offline/ (pagina generica guardada pelo service worker). Quando a
 * internet cai e a pessoa abre qualquer tela do sistema, o service worker entrega esta
 * pagina no mesmo endereco; aqui escolhemos a aba certa pelo endereco e montamos a tela
 * a partir da copia CRIPTOGRAFADA do aparelho (HoraCertaMirror) + fila de registros
 * ainda nao enviados (HoraCertaOffline).
 *
 * Contas de horas iguais as do servidor (timeclock/services.py compute_day_total):
 * horarios do dia em ordem, minuto cheio, soma dos pares entrada/saida; numero impar
 * de horarios = dia em andamento/incompleto.
 */
(function () {
  "use strict";
  var api = window.HoraCertaOffline;
  var mirror = window.HoraCertaMirror;
  var $ = function (id) { return document.getElementById(id); };
  var PING_URL = "/ping/";

  var VIEWS = ["registrar", "resumo", "historico", "clientes", "agenda", "producao", "romaneios"];
  // enderecos reais das telas vem do servidor (pagina /offline/, via {% url %})
  var PATHS = Object.assign({
    registrar: "/me/", resumo: "/me/painel/", historico: "/me/historico/", clientes: "/me/clientes/",
    agenda: "/me/servicos/agenda/", producao: "/me/relatorios-producao/", romaneios: "/me/relatorios-producao/notas/",
  }, window.HC_OFFLINE_PATHS || {});

  var state = { profile: null, data: null, pending: [], online: false, view: "registrar", sheet: null };
  var F = window.HoraCertaOfflineForms || null;  // etapa 3: formularios para salvar sem internet

  // ---------- utilidades ----------
  function esc(text) {
    return String(text == null ? "" : text).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function pad(n) { return String(n).padStart(2, "0"); }
  function ymd(d) { return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }
  function hhmm(d) { return pad(d.getHours()) + ":" + pad(d.getMinutes()); }
  function fmtSeconds(total) {
    var m = Math.round(total / 60);
    return pad(Math.floor(m / 60)) + ":" + pad(m % 60);
  }
  var money = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
  var WEEKDAYS = ["domingo", "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado"];
  var WEEKDAYS_SHORT = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];
  var MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
  function parseDay(iso) { var p = iso.split("-"); return new Date(+p[0], +p[1] - 1, +p[2]); }
  function dayTitle(iso) { var d = parseDay(iso); return WEEKDAYS_SHORT[d.getDay()] + ", " + pad(d.getDate()) + "/" + pad(d.getMonth() + 1); }
  function weekStart(d) { var x = new Date(d.getFullYear(), d.getMonth(), d.getDate()); var wd = (x.getDay() + 6) % 7; x.setDate(x.getDate() - wd); return x; }

  function viewFromPath(path) {
    if (/^\/me\/relatorios-producao\/notas\//.test(path)) return "romaneios";
    if (/^\/me\/relatorios-producao\//.test(path)) return "producao";
    if (/^\/me\/servicos\//.test(path)) return "agenda";
    if (path.indexOf(PATHS.clientes) === 0 || /^\/me\/clientes\//.test(path)) return "clientes";
    if (/^\/me\/historico\//.test(path)) return "historico";
    if (/^\/me\/painel\//.test(path)) return "resumo";
    return "registrar";
  }
  function sheetFromPath(path) {
    var m = path.match(/^\/me\/relatorios-producao\/([0-9a-f-]{36})\//);
    return m ? m[1] : null;
  }

  // ---------- horas (igual ao servidor) ----------
  function allPunches() {
    var list = [];
    ((state.data && state.data.punches) || []).forEach(function (p) {
      list.push({ client_id: p.client_id, at: new Date(p.at), pending: false });
    });
    state.pending.forEach(function (i) {
      if (i.kind === "punch") list.push({ client_id: i.contract_id, at: new Date(i.occurred_at), pending: true, error: i.last_error });
    });
    return list.sort(function (a, b) { return a.at - b.at; });
  }

  function dayRows(clientId) {
    var byDay = {};
    allPunches().forEach(function (p) {
      if (clientId && p.client_id !== clientId) return;
      var key = ymd(p.at) + "|" + p.client_id;
      (byDay[key] = byDay[key] || { date: ymd(p.at), client_id: p.client_id, points: [] }).points.push(p);
    });
    return Object.keys(byDay).map(function (k) {
      var row = byDay[k];
      var mins = row.points.map(function (p) { var d = new Date(p.at); d.setSeconds(0, 0); return d; });
      var total = 0;
      for (var i = 0; i + 1 < mins.length; i += 2) {
        var delta = (mins[i + 1] - mins[i]) / 1000;
        if (delta > 0) total += delta;
      }
      row.total = total;
      row.incomplete = mins.length % 2 === 1;
      row.hasPending = row.points.some(function (p) { return p.pending; });
      return row;
    }).sort(function (a, b) { return a.date < b.date ? 1 : a.date > b.date ? -1 : 0; });
  }

  function clientById(id) {
    return ((state.data && state.data.clients) || []).filter(function (c) { return c.id === id; })[0] ||
      ((state.profile && state.profile.contracts) || []).filter(function (c) { return c.id === id; })[0] || { name: "cliente" };
  }
  function dayOff(iso) {
    return ((state.data && state.data.days_off) || []).filter(function (d) { return d.date === iso; })[0];
  }

  function totals() {
    var now = new Date();
    var today = ymd(now), wk = ymd(weekStart(now)), month = today.slice(0, 7);
    var out = { today: 0, week: 0, month: 0, value: 0, perClient: {} };
    dayRows().forEach(function (r) {
      var c = out.perClient[r.client_id] = out.perClient[r.client_id] || { month: 0, incomplete: 0 };
      if (r.date.slice(0, 7) === month) { out.month += r.total; c.month += r.total; if (r.incomplete && r.date !== today) c.incomplete += 1; }
      if (r.date >= wk) out.week += r.total;
      if (r.date === today) out.today += r.total;
    });
    Object.keys(out.perClient).forEach(function (id) {
      var rate = parseFloat(clientById(id).hourly_rate || "0") || 0;
      out.perClient[id].value = Math.round((out.perClient[id].month / 3600) * rate * 100) / 100;
      out.value += out.perClient[id].value;
    });
    return out;
  }

  // ---------- telas ----------
  function needCopy() {
    return '<div class="empty"><b>Esta tela ainda não foi guardada neste aparelho.</b>' +
      "<p>Abra o HoraCerta uma vez com internet. Depois ela funciona sem internet também.</p></div>";
  }
  function pendingBadge(on) { return on ? '<span class="tag warn">guardado no celular</span>' : ""; }

  function renderResumo() {
    if (!state.data) return needCopy();
    var t = totals(), now = new Date();
    var cards = [
      ["Horas hoje", fmtSeconds(t.today), ""], ["Na semana", fmtSeconds(t.week), ""],
      ["No mês", fmtSeconds(t.month), ""], ["Valor estimado no mês", money.format(t.value), "money"],
    ].map(function (c) { return '<div class="num ' + c[2] + '"><span>' + c[0] + "</span><strong>" + c[1] + "</strong></div>"; }).join("");
    var today = ymd(now);
    var jobs = (state.data.jobs || []).filter(function (j) { return j.date === today; });
    var rows = (state.data.clients || []).filter(function (c) { return c.active; }).map(function (c) {
      var pc = t.perClient[c.id] || { month: 0, value: 0, incomplete: 0 };
      return '<li><div><b>' + esc(c.name) + "</b><small>" + money.format(parseFloat(c.hourly_rate || 0)) + "/h" +
        (pc.incomplete ? " · " + pc.incomplete + (pc.incomplete === 1 ? " dia incompleto" : " dias incompletos") : "") +
        "</small></div><div class=\"right\"><b>" + fmtSeconds(pc.month) + "</b><small>" + money.format(pc.value || 0) + "</small></div></li>";
    }).join("");
    return '<h1 class="title">Meu resumo</h1><p class="sub">' + MONTHS[now.getMonth()] + " de " + now.getFullYear() +
      " · horas e valores (inclui o que está guardado no celular)</p>" +
      '<section class="nums">' + cards + "</section>" +
      (jobs.length ? '<section class="card"><h2>Hoje você tem ' + jobs.length + (jobs.length === 1 ? " serviço" : " serviços") +
        '</h2><ul class="rows">' + jobs.map(jobRow).join("") + "</ul></section>" : "") +
      '<section class="card"><h2>Por cliente</h2><ul class="rows">' + (rows || '<li><div>Nenhum cliente ativo.</div></li>') + "</ul></section>";
  }

  function renderHistorico() {
    if (!state.data) return needCopy();
    var rows = dayRows();
    var since = state.data.since;
    var html = rows.map(function (r) {
      var off = dayOff(r.date);
      var times = r.points.map(function (p) {
        return '<span class="time' + (p.pending ? " pending" : "") + '">' + hhmm(p.at) + "</span>";
      }).join("");
      return '<li><div><b>' + dayTitle(r.date) + "</b> · " + esc(clientById(r.client_id).name) +
        (off ? ' <span class="tag">' + (off.kind === "FERIADO" ? "Feriado" : "Folga") + "</span>" : "") +
        '<div class="times">' + times + "</div></div><div class=\"right\"><b>" + fmtSeconds(r.total) + "</b>" +
        (r.incomplete ? '<small class="warn-text">' + (r.date === ymd(new Date()) ? "em andamento" : "incompleto") + "</small>" : "") +
        pendingBadge(r.hasPending) + "</div></li>";
    }).join("");
    var offOnly = (state.data.days_off || []).filter(function (d) {
      return !rows.some(function (r) { return r.date === d.date; });
    }).map(function (d) {
      return '<li><div><b>' + dayTitle(d.date) + '</b> <span class="tag">' + (d.kind === "FERIADO" ? "Feriado" : "Folga") + "</span>" +
        (d.note ? "<small>" + esc(d.note) + "</small>" : "") + "</div></li>";
    }).join("");
    return '<h1 class="title">Histórico</h1><p class="sub">Desde ' + since.split("-").reverse().slice(0, 2).join("/") + ". Horários em amarelo estão guardados no celular e serão enviados.</p>" +
      '<section class="card"><ul class="rows">' + (html + offOnly || "<li><div>Nenhum horário no período.</div></li>") + "</ul></section>";
  }

  function renderClientes() {
    if (!state.data) return needCopy();
    var t = totals();
    var items = (state.data.clients || []).map(function (c) {
      var pc = t.perClient[c.id] || { month: 0, value: 0 };
      return '<li><div><b>' + esc(c.name) + '</b> <span class="tag ' + (c.active ? "ok" : "") + '">' + (c.active ? "Ativo" : "Inativo") + "</span>" +
        "<small>" + money.format(parseFloat(c.hourly_rate || 0)) + "/h · desde " + (c.start_date ? dayTitle(c.start_date) : "-") + "</small></div>" +
        '<div class="right"><b>' + fmtSeconds(pc.month) + "</b><small>" + money.format(pc.value || 0) + " no mês</small></div></li>";
    }).join("");
    var fresh = F ? F.pendingClientsRows(state) : "";
    return '<h1 class="title">Meus clientes</h1><p class="sub">Horas e valores de cada cliente no mês atual.</p>' +
      (F ? F.clientForm() : "") +
      '<section class="card"><ul class="rows">' + (fresh + items || "<li><div>Nenhum cliente.</div></li>") + "</ul></section>";
  }

  function jobRow(j) {
    var right = F ? F.jobActions(state, j) : '<span class="tag">' + esc(j.status_label) + "</span>";
    return '<li><div><b>' + (j.start ? j.start + " · " : "") + esc(j.title) + "</b><small>" + esc(j.client) +
      (j.location ? " · " + esc(j.location) : "") + '</small></div><div class="right">' + right + "</div></li>";
  }

  function renderAgenda() {
    if (!state.data) return needCopy();
    var start = weekStart(new Date());
    var days = [];
    for (var i = 0; i < 14; i++) { var d = new Date(start); d.setDate(start.getDate() + i); days.push(ymd(d)); }
    var today = ymd(new Date());
    var html = days.map(function (iso) {
      var jobs = (state.data.jobs || []).filter(function (j) { return j.date === iso; });
      var fresh = F ? F.pendingJobsFor(state, iso) : "";
      if (!jobs.length && !fresh && iso < today) return "";
      return '<section class="card day' + (iso === today ? " is-today" : "") + '"><h2>' + (iso === today ? "Hoje · " : "") + dayTitle(iso) +
        "</h2>" + (jobs.length || fresh ? '<ul class="rows">' + fresh + jobs.map(jobRow).join("") + "</ul>" : '<p class="sub">Nenhum serviço.</p>') + "</section>";
    }).join("");
    return '<h1 class="title">Agenda</h1><p class="sub">Esta semana e a próxima.</p>' +
      (F ? F.serviceForm(state) + F.reportForm() : "") + html;
  }

  function renderProducao() {
    if (!state.data) return needCopy();
    var sheets = state.data.sheets || [];
    var current = state.sheet && sheets.filter(function (s) { return s.id === state.sheet; })[0];
    if (current) {
      var entries = (state.data.entries || []).filter(function (e) { return e.sheet_id === current.id; });
      var queued = state.pending.filter(function (i) { return i.kind === "production_entry" && i.sheet_id === current.id; });
      var rows = queued.map(function (i) {
        return '<li><div><b>' + esc(i.fields.item_code || "sem código") + "</b><small>" + esc(i.fields.work_date) + "</small></div>" +
          '<div class="right"><b>' + esc(i.fields.quantity || "-") + "</b>" + pendingBadge(true) + "</div></li>";
      }).concat(entries.map(function (e) {
        var when = e.start && e.end ? e.start + "–" + e.end : (e.minutes ? e.minutes + " min" : "");
        return '<li><div><b>' + esc(e.item_code || "sem código") + "</b><small>" + dayTitle(e.date) +
          (e.production_order ? " · OP " + esc(e.production_order) : "") + (when ? " · " + when : "") +
          (e.destination ? " · " + esc(e.destination === "GUINCHO" ? "Guincho" : "Implemento") : "") + "</small></div>" +
          '<div class="right"><b>' + (e.quantity == null ? "-" : e.quantity) + "</b><small>peças</small></div></li>";
      })).join("");
      return '<p><button class="link" type="button" data-sheet="">← Todos os relatórios</button></p>' +
        '<h1 class="title">' + esc(current.equipment) + "</h1><p class=\"sub\">" + esc(current.company || "") + "</p>" +
        (current.status === "OPEN" ? '<p><button type="button" class="btn" data-go="registrar">Anotar item sem internet</button></p>' : "") +
        '<section class="card"><ul class="rows">' + (rows || "<li><div>Nenhum item.</div></li>") + "</ul></section>";
    }
    var list = sheets.map(function (s) {
      var n = (state.data.entries || []).filter(function (e) { return e.sheet_id === s.id; }).length;
      return '<li><button class="rowbtn" type="button" data-sheet="' + esc(s.id) + '"><div><b>' + esc(s.equipment) + "</b><small>" +
        esc(s.company || "") + " · " + n + (n === 1 ? " item" : " itens") + '</small></div><span class="tag ' + (s.status === "OPEN" ? "ok" : "") + '">' +
        (s.status === "OPEN" ? "Aberto" : "Fechado") + "</span></button></li>";
    }).join("");
    return '<h1 class="title">Relatórios de produção</h1><p class="sub">Máquinas e itens anotados.</p>' +
      '<section class="card"><ul class="rows">' + (list || "<li><div>Nenhum relatório.</div></li>") + "</ul></section>";
  }

  function renderRomaneios() {
    if (!state.data) return needCopy();
    var list = (state.data.shipments || []).map(function (n) {
      var situation = n.status === "DRAFT" ? "Rascunho" : n.authorized ? "Autorizado " + n.authorized + " de " + n.recipients
        : n.seen ? "Visto " + n.seen + " de " + n.recipients : "Enviado";
      var items = n.items.map(function (i) {
        return "<small>" + esc(i.quantity) + "× " + esc(i.drawing) + (i.production_order ? " (OP " + esc(i.production_order) + ")" : "") + "</small>";
      }).join("");
      return '<li><div><b>Nº ' + esc(n.number || "-") + " · " + esc(n.destination) + "</b>" + items + '</div><div class="right"><span class="tag">' +
        situation + "</span></div></li>";
    }).join("");
    var fresh = F ? F.pendingShipments(state) : "";
    return '<h1 class="title">Romaneios</h1><p class="sub">Últimos 60 dias.</p>' + (F ? F.shipmentForm() : "") +
      '<section class="card"><ul class="rows">' + (fresh + list || "<li><div>Nenhum romaneio.</div></li>") + "</ul></section>";
  }

  var RENDER = { resumo: renderResumo, historico: renderHistorico, clientes: renderClientes, agenda: renderAgenda,
    producao: renderProducao, romaneios: renderRomaneios };

  function copyInfo() {
    var el = $("copyInfo");
    if (!state.data) { el.hidden = true; return; }
    var d = new Date(state.data._saved_at || Date.now());
    el.textContent = "Mostrando a cópia guardada neste aparelho em " + pad(d.getDate()) + "/" + pad(d.getMonth() + 1) + " às " + hhmm(d) +
      ". Atualiza sozinha quando a internet voltar.";
    el.hidden = state.view === "registrar";
  }

  function show(view, push) {
    if (VIEWS.indexOf(view) < 0) view = "registrar";
    state.view = view;
    document.querySelectorAll("[data-tab]").forEach(function (b) {
      var on = b.getAttribute("data-tab") === view;
      b.classList.toggle("on", on);
      if (on) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
    });
    $("viewRegistrar").hidden = view !== "registrar";
    if (view === "registrar" && F && $("registrarExtras")) $("registrarExtras").innerHTML = F.registrarExtras(state);
    var other = $("viewOther");
    other.hidden = view === "registrar";
    if (view !== "registrar") other.innerHTML = RENDER[view]();
    copyInfo();
    if (push) {
      var path = view === "producao" && state.sheet ? "/me/relatorios-producao/" + state.sheet + "/" : PATHS[view];
      try { history.replaceState(null, "", path); } catch (e) {}
    }
    window.scrollTo(0, 0);
  }

  document.addEventListener("click", function (e) {
    var tab = e.target.closest("[data-tab]");
    if (tab) { state.sheet = null; show(tab.getAttribute("data-tab"), true); return; }
    var sheetBtn = e.target.closest("[data-sheet]");
    if (sheetBtn) { state.sheet = sheetBtn.getAttribute("data-sheet") || null; show("producao", true); return; }
    var go = e.target.closest("[data-go]");
    if (go) {
      if (state.sheet && $("sheet")) $("sheet").value = state.sheet;
      show(go.getAttribute("data-go"), true);
    }
  });

  function editing() {
    var el = document.activeElement;
    return !!(el && el.closest && el.closest("[data-offline-form]") && el.form && Array.prototype.some.call(el.form.elements,
      function (x) { return x.value && x.type !== "submit" && x.type !== "button" && x.tagName !== "SELECT" && x.type !== "date"; }));
  }

  function notify(text, kind) {
    var m = $("appMsg");
    if (!m) return;
    m.textContent = text || "";
    m.className = "msg" + (kind ? " " + kind : "");
    m.hidden = !text;
    if (text) setTimeout(function () { if (m.textContent === text) m.hidden = true; }, 6000);
  }

  function reload() {
    var uid = state.profile && state.profile.user_id;
    return Promise.all([
      uid && mirror ? mirror.load(uid) : Promise.resolve(null),
      uid ? api.pending(uid) : Promise.resolve([]),
    ]).then(function (res) {
      state.data = res[0];
      state.pending = res[1] || [];
      if (editing()) return;  // nao apaga o que a pessoa esta digitando
      show(state.view, false);
    });
  }

  window.HoraCertaOfflineApp = {
    start: function (profile) {
      state.profile = profile;
      state.view = viewFromPath(location.pathname);
      state.sheet = sheetFromPath(location.pathname);
      $("tabs").hidden = !profile;
      api.onChange(reload);
      if (F) F.attach(function () { return state; }, notify);
      return reload();
    },
    reload: reload,
    setOnline: function (on) { state.online = on; },
    describe: function (item) { return F ? F.describe(item, state) : item.kind; },
  };
})();
