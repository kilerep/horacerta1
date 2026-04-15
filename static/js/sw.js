const SW_VERSION = "hc-sw-v1";
const STATIC_CACHE = `hc-static-${SW_VERSION}`;

function isCacheableAsset(request, url) {
  if (url.origin !== self.location.origin) return false;
  if (request.mode === "navigate" || request.destination === "document") return false;
  if (url.pathname.startsWith("/admin/")) return false;

  const dest = request.destination;
  if (["style", "script", "image", "font"].includes(dest)) return true;
  if (url.pathname.startsWith("/static/")) return true;
  return false;
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(STATIC_CACHE);
  const cached = await cache.match(request);

  const networkPromise = fetch(request)
    .then((response) => {
      if (response && response.ok) {
        cache.put(request, response.clone());
      }
      return response;
    })
    .catch(() => null);

  if (cached) {
    return cached;
  }

  const network = await networkPromise;
  if (network) return network;
  return new Response("", { status: 504, statusText: "Gateway Timeout" });
}

self.addEventListener("install", (event) => {
  self.skipWaiting();
  event.waitUntil(caches.open(STATIC_CACHE));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(keys.filter((key) => key.startsWith("hc-static-") && key !== STATIC_CACHE).map((key) => caches.delete(key)));
      await self.clients.claim();
    })()
  );
});

self.addEventListener("message", (event) => {
  if (!event.data || event.data.type !== "SKIP_WAITING") return;
  self.skipWaiting();
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  if (!isCacheableAsset(event.request, url)) return;

  event.respondWith(staleWhileRevalidate(event.request));
});
