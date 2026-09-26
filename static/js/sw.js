/*
 * HoraCerta - Service Worker (v4)
 *
 * Princípio: o que é privado NUNCA é guardado no navegador.
 *
 * As versões anteriores (v1-v3) guardavam em Cache Storage todo HTML
 * autenticado que passava por aqui (painel, clientes, relatórios, valores/hora)
 * indexado só pela URL e nunca limpavam no logout - outra pessoa usando o mesmo
 * navegador podia ver esses dados offline. Esta versão inverte a regra:
 *
 *   - navegação HTML: SEMPRE rede. Só um conjunto pequeno e explícito de
 *     páginas públicas sem personalização (PUBLIC_HTML) pode usar cache.
 *   - qualquer outra navegação que falhe por falta de rede mostra /offline/.
 *   - assets estáticos: só os versionados por hash (arquivo.<12hex>.ext), que
 *     são imutáveis por construção.
 *   - POST/PUT/DELETE nunca entram em fila nem em cache: se a rede cair no meio,
 *     a pessoa vê uma página clara de "não foi possível salvar".
 *
 * Isto é "degradação graciosa" offline, não "offline-first": registrar horários
 * sem conexão continua indisponível de propósito (ver Bloco 6 do roadmap).
 */

const SW_VERSION = "hc-sw-v4";
const OFFLINE_CACHE = `hc-offline-${SW_VERSION}`;
const PUBLIC_CACHE = `hc-public-${SW_VERSION}`;
const OFFLINE_PAGE = "/offline/";

// Somente páginas comprovadamente públicas e iguais para qualquer visitante
// (não dependem de sessão, nome, cliente ou token). Não incluir "/": ele
// redireciona quem está logado para o painel.
const PUBLIC_HTML = new Set(["/help/", "/terms/", "/privacy/"]);

// ManifestStaticFilesStorage nomeia os arquivos como nome.<md5 de 12 hex>.ext:
// o conteúdo define o nome, então é seguro servir do cache para sempre.
const HASHED_STATIC = /^\/static\/.+\.[0-9a-f]{12}\.[A-Za-z0-9]+$/;
const MAX_PUBLIC_CACHE_ENTRIES = 80;

// Versão de migração de segurança: ativa imediatamente (sem esperar todas as
// abas fecharem) para descartar logo os caches privados das versões antigas.
// Remover na próxima versão do SW, voltando ao aviso "nova versão disponível".
const ACTIVATE_IMMEDIATELY = true;

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(OFFLINE_CACHE).then((cache) => cache.add(new Request(OFFLINE_PAGE, { cache: "reload" })))
  );
  if (ACTIVATE_IMMEDIATELY) self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      // Esta origem só serve o HoraCerta: descarta TODO cache que não seja
      // desta versão (inclui hc-static-*/hc-dynamic-* das versões antigas, que
      // podem conter HTML autenticado).
      const keep = new Set([OFFLINE_CACHE, PUBLIC_CACHE]);
      const names = await caches.keys();
      await Promise.all(names.filter((name) => !keep.has(name)).map((name) => caches.delete(name)));
      await self.clients.claim();
    })()
  );
});

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") {
    self.skipWaiting();
    return;
  }
  if (event.data && event.data.type === "CLEAR_CACHE") {
    event.waitUntil(caches.delete(PUBLIC_CACHE));
  }
});

async function trimCache(cache) {
  const keys = await cache.keys();
  const excess = keys.length - MAX_PUBLIC_CACHE_ENTRIES;
  for (let i = 0; i < excess; i += 1) await cache.delete(keys[i]);
}

function isCacheableHtml(response) {
  const contentType = response.headers.get("content-type") || "";
  return response.ok && !response.redirected && response.type === "basic" && contentType.includes("text/html");
}

async function offlineFallback() {
  const cached = await caches.match(OFFLINE_PAGE);
  return (
    cached ||
    new Response("Sem conexão com o HoraCerta.", {
      status: 503,
      headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" },
    })
  );
}

async function publicPageNetworkFirst(request) {
  const cache = await caches.open(PUBLIC_CACHE);
  try {
    const response = await fetch(request);
    if (isCacheableHtml(response)) await cache.put(request, response.clone());
    return response;
  } catch (error) {
    return (await cache.match(request)) || offlineFallback();
  }
}

async function hashedStaticCacheFirst(request) {
  const cache = await caches.open(PUBLIC_CACHE);
  const cached = await cache.match(request);
  if (cached) return cached;

  const response = await fetch(request);
  if (response.ok && !response.redirected && response.type === "basic") {
    await cache.put(request, response.clone());
    await trimCache(cache);
  }
  return response;
}

function saveFailedResponse() {
  const html =
    '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">' +
    '<meta name="viewport" content="width=device-width,initial-scale=1">' +
    "<title>Não foi possível salvar - HoraCerta</title></head>" +
    '<body style="font-family:system-ui,sans-serif;max-width:32rem;margin:12vh auto;padding:0 1.25rem;line-height:1.5">' +
    "<h1>Não foi possível salvar</h1>" +
    "<p>O HoraCerta perdeu a conexão antes de concluir o envio. <strong>Nada foi salvo.</strong></p>" +
    "<p>Volte à tela anterior, confira os dados e tente novamente quando a conexão voltar.</p>" +
    '<button onclick="history.back()" style="padding:.7rem 1.2rem;font-size:1rem">Voltar</button>' +
    "</body></html>";
  return new Response(html, {
    status: 503,
    headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" },
  });
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);

  // Outras origens (fontes, CDNs) ficam com o navegador.
  if (url.origin !== self.location.origin) return;

  // Formulário HTML tradicional (POST com navegação): sempre rede; se cair no
  // meio do envio, mostra uma página clara em vez do erro genérico do Chrome.
  // Nunca enfileira nem guarda nada.
  if (request.method !== "GET") {
    if (request.mode === "navigate") {
      event.respondWith(fetch(request).catch(() => saveFailedResponse()));
    }
    return;
  }

  if (request.mode === "navigate") {
    if (PUBLIC_HTML.has(url.pathname) && url.search === "") {
      event.respondWith(publicPageNetworkFirst(request));
    } else {
      // Todo o resto (painel, clientes, relatórios, login, links públicos com
      // token...) é rede pura. Sem rede: página offline. Sem cópia local.
      event.respondWith(fetch(request).catch(() => offlineFallback()));
    }
    return;
  }

  if (HASHED_STATIC.test(url.pathname)) {
    event.respondWith(hashedStaticCacheFirst(request));
  }
  // Demais requisições (API, /ping/, mídia, manifest...) não são interceptadas:
  // vão direto à rede, respeitando os cabeçalhos de cache do servidor.
});

self.addEventListener("push", (event) => {
  if (!event.data) return;

  try {
    const data = event.data.json();
    event.waitUntil(
      self.registration.showNotification(data.title || "HoraCerta", {
        body: data.body || "Nova notificação",
        icon: "/static/pwa/icon-192.png",
        badge: "/static/pwa/icon-192.png",
        tag: data.tag || "horacerta-notification",
        data: data.data || {},
      })
    );
  } catch (error) {
    event.waitUntil(
      self.registration.showNotification("HoraCerta", {
        body: event.data.text(),
        icon: "/static/pwa/icon-192.png",
        badge: "/static/pwa/icon-192.png",
      })
    );
  }
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const urlToOpen = (event.notification.data && event.notification.data.url) || "/";

  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
      const existing = clientList.find((client) => client.url === urlToOpen && "focus" in client);
      return existing ? existing.focus() : clients.openWindow && clients.openWindow(urlToOpen);
    })
  );
});
