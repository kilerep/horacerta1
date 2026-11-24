/*
 * HoraCerta offline: fila de registros feitos sem internet + envio automatico.
 *
 * Guarda no aparelho (IndexedDB "hc-offline"):
 *   - queue:   cada toque feito offline (entrada/saida ou item de producao) com o
 *              horario real do toque e um client_ref unico. Fica ate o servidor aceitar.
 *   - profile: lista minima para a tela offline funcionar (clientes e folhas de
 *              producao abertas da pessoa logada). Apagada ao sair da conta.
 *
 * Nao guarda paginas, valores, relatorios nem nada alem disso.
 * Envio: POST /me/offline/sincronizar/ quando ha conexao (ao abrir o app, ao voltar
 * a internet e a cada 60s com fila pendente). Reenviar e seguro (client_ref).
 */
(function (root) {
  "use strict";

  var DB_NAME = "hc-offline";
  var DB_VERSION = 1;
  var SYNC_URL = "/me/offline/sincronizar/";
  var PROFILE_URL = "/me/offline/perfil/";

  function openDb() {
    return new Promise(function (resolve, reject) {
      if (!root.indexedDB) return reject(new Error("sem indexedDB"));
      var req = root.indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = function () {
        var db = req.result;
        if (!db.objectStoreNames.contains("queue")) db.createObjectStore("queue", { keyPath: "client_ref" });
        if (!db.objectStoreNames.contains("profile")) db.createObjectStore("profile", { keyPath: "key" });
      };
      req.onsuccess = function () { resolve(req.result); };
      req.onerror = function () { reject(req.error); };
    });
  }

  function tx(store, mode, fn) {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var t = db.transaction(store, mode);
        var result = fn(t.objectStore(store));
        t.oncomplete = function () { resolve(result && result.result !== undefined ? result.result : result); };
        t.onerror = function () { reject(t.error); };
      });
    });
  }

  function uuid() {
    if (root.crypto && root.crypto.randomUUID) return root.crypto.randomUUID();
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
      var r = (Math.random() * 16) | 0;
      return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
    });
  }

  function getAll(store) {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var req = db.transaction(store, "readonly").objectStore(store).getAll();
        req.onsuccess = function () { resolve(req.result || []); };
        req.onerror = function () { reject(req.error); };
      });
    });
  }

  function getProfile() {
    return openDb().then(function (db) {
      return new Promise(function (resolve) {
        var req = db.transaction("profile", "readonly").objectStore("profile").get("me");
        req.onsuccess = function () { resolve(req.result ? req.result.data : null); };
        req.onerror = function () { resolve(null); };
      });
    }).catch(function () { return null; });
  }

  function saveProfile(data) {
    return tx("profile", "readwrite", function (s) { return s.put({ key: "me", data: data, saved_at: new Date().toISOString() }); });
  }

  function clearProfile() {
    return tx("profile", "readwrite", function (s) { return s.clear(); }).catch(function () {});
  }

  function enqueue(item) {
    var record = Object.assign({ client_ref: uuid(), created_at: new Date().toISOString() }, item);
    return tx("queue", "readwrite", function (s) { return s.put(record); }).then(function () {
      notify();
      return record;
    });
  }

  function pending(userId) {
    return getAll("queue").then(function (items) {
      return items.filter(function (i) { return !userId || i.user_id === userId; })
        .sort(function (a, b) { return a.created_at < b.created_at ? -1 : 1; });
    }).catch(function () { return []; });
  }

  function remove(ref) {
    return tx("queue", "readwrite", function (s) { return s.delete(ref); });
  }

  function markError(record, reason) {
    record.last_error = reason;
    return tx("queue", "readwrite", function (s) { return s.put(record); });
  }

  function csrfToken() {
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    if (match) return decodeURIComponent(match[1]);
    var input = document.querySelector("input[name=csrfmiddlewaretoken]");
    return input ? input.value : "";
  }

  var syncing = false;
  function sync(userId) {
    if (syncing || !navigator.onLine) return Promise.resolve({ sent: 0 });
    syncing = true;
    return pending(userId).then(function (items) {
      var toSend = items.filter(function (i) { return !i.last_error; });
      if (!toSend.length) return { sent: 0 };
      return fetch(SYNC_URL, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
        body: JSON.stringify({ items: toSend }),
      }).then(function (resp) {
        if (resp.status === 403 || resp.redirected) throw new Error("login");
        if (!resp.ok) throw new Error("http " + resp.status);
        return resp.json();
      }).then(function (data) {
        var byRef = {};
        toSend.forEach(function (i) { byRef[i.client_ref] = i; });
        var sent = 0, failed = 0;
        var jobs = (data.resultados || []).map(function (r) {
          var record = byRef[r.client_ref];
          if (!record) return null;
          if (r.status === "ok") { sent += 1; return remove(record.client_ref); }
          failed += 1;
          return markError(record, r.motivo || "Não aceito pelo servidor.");
        });
        if (data.perfil) saveProfile(data.perfil);
        return Promise.all(jobs).then(function () { notify(); return { sent: sent, failed: failed }; });
      });
    }).catch(function (err) {
      return { sent: 0, error: String(err && err.message || err) };
    }).then(function (res) { syncing = false; return res; });
  }

  function refreshProfile() {
    if (!navigator.onLine) return Promise.resolve(null);
    return fetch(PROFILE_URL, { credentials: "same-origin", cache: "no-store" })
      .then(function (r) { return r.ok && !r.redirected ? r.json() : null; })
      .then(function (data) { if (data && data.user_id) return saveProfile(data).then(function () { return data; }); return null; })
      .catch(function () { return null; });
  }

  var listeners = [];
  function notify() { listeners.forEach(function (fn) { try { fn(); } catch (e) {} }); }
  function onChange(fn) { listeners.push(fn); }

  root.HoraCertaOffline = {
    enqueue: enqueue, pending: pending, remove: remove, sync: sync, getProfile: getProfile,
    saveProfile: saveProfile, refreshProfile: refreshProfile, clearProfile: clearProfile, onChange: onChange, uuid: uuid,
  };
})(window);
