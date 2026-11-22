/*
 * HoraCerta Offline 2.0 - copia dos dados no aparelho, CRIPTOGRAFADA.
 *
 * Banco "hc-mirror" (IndexedDB), separado da fila de envio ("hc-offline"):
 *   - keys: uma chave AES-GCM 256 por conta, gerada no proprio aparelho e marcada
 *           como NAO exportavel (o JavaScript usa, mas nao consegue ler os bytes).
 *   - data: a copia (JSON de /me/offline/copia/) cifrada com essa chave + IV novo
 *           a cada gravacao. Nada fica em texto puro no disco.
 *
 * Quando a copia e apagada (wipeAll):
 *   - ao abrir qualquer tela deslogada (depois de "Sair" ou com a sessao expirada);
 *   - quando o servidor recusa a sessao ao atualizar a copia;
 *   - quando outra conta entra neste aparelho;
 *   - quando a copia passa de 30 dias sem ser atualizada.
 * A fila de registros feitos sem internet NAO fica aqui e nao e apagada por isto:
 * ela so e enviada quando a mesma conta entrar de novo (offline_store.js).
 */
(function (root) {
  "use strict";

  var DB_NAME = "hc-mirror";
  var DB_VERSION = 1;
  var MIRROR_URL = "/me/offline/copia/";
  var DEFAULT_TTL_DAYS = 30;
  var REFRESH_EVERY_MS = 5 * 60 * 1000;
  var subtle = root.crypto && root.crypto.subtle;

  function supported() {
    return !!(root.indexedDB && subtle && root.TextEncoder);
  }

  function openDb() {
    return new Promise(function (resolve, reject) {
      var req = root.indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = function () {
        var db = req.result;
        if (!db.objectStoreNames.contains("keys")) db.createObjectStore("keys", { keyPath: "user_id" });
        if (!db.objectStoreNames.contains("data")) db.createObjectStore("data", { keyPath: "user_id" });
      };
      req.onsuccess = function () { resolve(req.result); };
      req.onerror = function () { reject(req.error); };
      req.onblocked = function () { reject(new Error("blocked")); };
    });
  }

  function request(store, mode, fn) {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var t = db.transaction(store, mode);
        var req = fn(t.objectStore(store));
        t.oncomplete = function () { db.close(); resolve(req && req.result); };
        t.onerror = function () { db.close(); reject(t.error); };
        t.onabort = function () { db.close(); reject(t.error); };
      });
    });
  }

  function getKey(userId, create) {
    return request("keys", "readonly", function (s) { return s.get(userId); }).then(function (row) {
      if (row && row.key) return row.key;
      if (!create) return null;
      return subtle.generateKey({ name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]).then(function (key) {
        return request("keys", "readwrite", function (s) { return s.put({ user_id: userId, key: key }); }).then(function () {
          return key;
        });
      });
    });
  }

  function save(userId, data) {
    var iv = root.crypto.getRandomValues(new Uint8Array(12));
    var plain = new TextEncoder().encode(JSON.stringify(data));
    return getKey(userId, true).then(function (key) {
      return subtle.encrypt({ name: "AES-GCM", iv: iv }, key, plain);
    }).then(function (cipher) {
      return request("data", "readwrite", function (s) {
        return s.put({
          user_id: userId,
          iv: iv,
          cipher: cipher,
          saved_at: Date.now(),
          ttl_days: Number(data && data.ttl_days) || DEFAULT_TTL_DAYS,
        });
      });
    }).then(function () { emit("saved"); });
  }

  function meta(userId) {
    return request("data", "readonly", function (s) { return s.get(userId); }).then(function (row) {
      return row ? { saved_at: row.saved_at, ttl_days: row.ttl_days } : null;
    }).catch(function () { return null; });
  }

  function expired(row) {
    var ttl = (row.ttl_days || DEFAULT_TTL_DAYS) * 24 * 3600 * 1000;
    return !row.saved_at || Date.now() - row.saved_at > ttl;
  }

  /** Le a copia da conta. Devolve null se nao houver, se venceu ou se nao der para abrir. */
  function load(userId) {
    if (!supported() || !userId) return Promise.resolve(null);
    return request("data", "readonly", function (s) { return s.get(userId); }).then(function (row) {
      if (!row) return null;
      if (expired(row)) return wipeAll().then(function () { return null; });
      return getKey(userId, false).then(function (key) {
        if (!key) return null;
        return subtle.decrypt({ name: "AES-GCM", iv: row.iv }, key, row.cipher).then(function (plain) {
          var data = JSON.parse(new TextDecoder().decode(plain));
          if (!data || data.user_id !== userId) return null;
          data._saved_at = row.saved_at;
          return data;
        });
      });
    }).catch(function () { return null; });
  }

  /** Apaga TODA copia guardada neste aparelho (todas as contas). */
  function wipeAll() {
    if (!root.indexedDB) return Promise.resolve();
    return new Promise(function (resolve) {
      var req = root.indexedDB.deleteDatabase(DB_NAME);
      req.onsuccess = req.onerror = req.onblocked = function () { resolve(); };
    }).then(function () { emit("wiped"); });
  }

  var refreshing = null;
  /** Baixa a copia nova do servidor (precisa de internet e sessao valida). */
  function refresh(userId, force) {
    if (!supported() || !userId) return Promise.resolve(null);
    if (refreshing) return refreshing;
    refreshing = meta(userId).then(function (m) {
      if (!force && m && Date.now() - m.saved_at < REFRESH_EVERY_MS) return null;
      if (root.navigator && root.navigator.onLine === false) return null;
      return fetch(MIRROR_URL, { credentials: "same-origin", cache: "no-store", headers: { Accept: "application/json" } })
        .then(function (resp) {
          // sessao acabou (redirecionou para o login) ou acesso negado: apaga a copia
          if (resp.redirected || resp.status === 401 || resp.status === 403) {
            return wipeAll().then(function () { return null; });
          }
          if (!resp.ok) return null;
          return resp.json().then(function (data) {
            if (!data || data.user_id !== userId) return wipeAll().then(function () { return null; });
            return save(userId, data).then(function () { return data; });
          });
        });
    }).catch(function () { return null; }).then(function (res) { refreshing = null; return res; });
    return refreshing;
  }

  var listeners = [];
  function emit(kind) { listeners.forEach(function (fn) { try { fn(kind); } catch (e) {} }); }
  function onChange(fn) { listeners.push(fn); }

  root.HoraCertaMirror = {
    supported: supported, load: load, save: save, meta: meta, refresh: refresh, wipeAll: wipeAll, onChange: onChange,
  };

  // Liga sozinho nas telas do sistema.
  function boot() {
    var body = root.document && root.document.body;
    if (!body || !supported()) return;
    var auth = body.getAttribute("data-authenticated");
    var userId = body.getAttribute("data-user-id") || "";
    if (auth === "false") {
      // tela deslogada (depois de Sair ou com a sessao expirada): nada de dados no aparelho
      wipeAll();
      return;
    }
    if (auth !== "true" || !userId) return;
    // outra conta entrou neste aparelho: a copia anterior nao pode ficar
    request("data", "readonly", function (s) { return s.getAllKeys(); }).then(function (owners) {
      var others = (owners || []).filter(function (id) { return id !== userId; });
      return others.length ? wipeAll() : null;
    }).catch(function () {}).then(function () {
      refresh(userId, false);
      root.addEventListener("online", function () { refresh(userId, true); });
    });
  }
  if (root.document) {
    if (root.document.readyState === "loading") root.document.addEventListener("DOMContentLoaded", boot);
    else boot();
  }
})(window);
