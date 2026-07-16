const SW_VERSION = "hc-sw-v4";
const STATIC_CACHE = `hc-static-${SW_VERSION}`;
const DYNAMIC_CACHE = `hc-dynamic-${SW_VERSION}`;
const OFFLINE_PAGE = "/offline/";

const ESSENTIAL_ASSETS = ["/", OFFLINE_PAGE, "/static/pwa/icon-192.png"];
const SENSITIVE_PATH_PREFIXES = [
  "/me/",
  "/contratante/",
  "/admin/",
  "/api/",
  "/accounts/",
  "/servicos/",
  "/media/",
  "/login/",
  "/logout/",
  "/password-",
];

function isSensitiveRequest(url) {
  if (url.origin !== self.location.origin) return true;
  return SENSITIVE_PATH_PREFIXES.some((prefix) => url.pathname.startsWith(prefix));
}

function responseAllowsStorage(response) {
  if (!response || !response.ok) return false;
  const cacheControl = (response.headers.get("Cache-Control") || "").toLowerCase();
  return !cacheControl.includes("no-store") && !cacheControl.includes("private");
}

function isCacheableAsset(request, url) {
  if (url.origin !== self.location.origin) return false;
  if (!url.pathname.startsWith("/static/")) return false;
  return ["style", "script", "image", "font"].includes(request.destination);
}

async function cacheEssentialAssets() {
  const cache = await caches.open(STATIC_CACHE);
  await Promise.all(
    ESSENTIAL_ASSETS.map(async (asset) => {
      try {
        const response = await fetch(asset, { cache: "no-cache" });
        if (responseAllowsStorage(response)) await cache.put(asset, response.clone());
      } catch (error) {
        console.warn("Não foi possível pré-cachear", asset, error);
      }
    })
  );
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(STATIC_CACHE);
  const cached = await cache.match(request);
  const networkPromise = fetch(request)
    .then((response) => {
      if (responseAllowsStorage(response)) cache.put(request, response.clone());
      return response;
    })
    .catch(() => null);

  if (cached) return cached;
  return (await networkPromise) || new Response("", { status: 504, statusText: "Gateway Timeout" });
}

async function offlineResponse(request) {
  if (request.mode === "navigate" || request.destination === "document") {
    return (await caches.match(OFFLINE_PAGE)) || new Response("Você está offline", { status: 503 });
  }
  return new Response("Recurso não disponível", { status: 503 });
}

async function networkOnly(request) {
  try {
    return await fetch(request);
  } catch (error) {
    return offlineResponse(request);
  }
}

async function networkFirstWithFallback(request) {
  try {
    const response = await fetch(request);
    if (responseAllowsStorage(response)) {
      const cache = await caches.open(DYNAMIC_CACHE);
      await cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    const cached = await caches.match(request);
    if (cached) return cached;
    return offlineResponse(request);
  }
}

self.addEventListener("install", (event) => {
  event.waitUntil(cacheEssentialAssets());
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key.startsWith("hc-") && key !== STATIC_CACHE && key !== DYNAMIC_CACHE)
            .map((key) => caches.delete(key))
        )
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("message", (event) => {
  if (event.data?.type === "SKIP_WAITING") self.skipWaiting();
  if (event.data?.type === "CLEAR_CACHE") caches.delete(DYNAMIC_CACHE);
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;

  const url = new URL(event.request.url);

  if (isSensitiveRequest(url)) {
    event.respondWith(networkOnly(event.request));
    return;
  }

  if (event.request.mode === "navigate" || event.request.destination === "document") {
    event.respondWith(networkFirstWithFallback(event.request));
    return;
  }

  if (isCacheableAsset(event.request, url)) {
    event.respondWith(staleWhileRevalidate(event.request));
  }
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
  const urlToOpen = event.notification.data?.url || "/";

  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
      const existing = clientList.find((client) => client.url === urlToOpen && "focus" in client);
      return existing ? existing.focus() : clients.openWindow?.(urlToOpen);
    })
  );
});
