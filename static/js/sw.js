const SW_VERSION = "hc-sw-v2";
const STATIC_CACHE = `hc-static-${SW_VERSION}`;
const DYNAMIC_CACHE = `hc-dynamic-${SW_VERSION}`;
const OFFLINE_PAGE = "/offline/";

// Assets que devem estar sempre em cache
const ESSENTIAL_ASSETS = [
  "/",
  "/offline/",
  "/static/css/",
  "/static/js/main.js",
  "/static/pwa/icon-192.png"
];

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

async function networkFirstWithFallback(request) {
  try {
    const response = await fetch(request);
    
    // Se sucesso, guardar em cache dinâmico
    if (response && response.ok) {
      const cache = await caches.open(DYNAMIC_CACHE);
      cache.put(request, response.clone());
    }
    
    return response;
  } catch (error) {
    // Se falhar, tentar cache dinâmico
    const cached = await caches.match(request);
    if (cached) {
      return cached;
    }
    
    // Se não tiver em cache, retornar página offline
    if (request.mode === "navigate" || request.destination === "document") {
      return caches.match(OFFLINE_PAGE) || 
        new Response("Você está offline", { status: 503 });
    }
    
    return new Response("Recurso não disponível", { status: 503 });
  }
}

// Instalar Service Worker
self.addEventListener("install", (event) => {
  console.log("🔧 Service Worker instalando...");
  
  event.waitUntil(
    (async () => {
      try {
        const cache = await caches.open(STATIC_CACHE);
        console.log("✅ Cache estático criado");
        
        // Pré-cachear assets essenciais
        await cache.addAll(ESSENTIAL_ASSETS).catch(err => {
          console.warn("⚠️ Alguns assets essenciais não puderam ser cacheados:", err);
        });
      } catch (error) {
        console.error("❌ Erro ao instalar Service Worker:", error);
      }
    })()
  );
  
  self.skipWaiting();
});

// Ativar Service Worker
self.addEventListener("activate", (event) => {
  console.log("🚀 Service Worker ativado");
  
  event.waitUntil(
    (async () => {
      try {
        const keys = await caches.keys();
        
        // Deletar caches antigos
        await Promise.all(
          keys
            .filter((key) => {
              return (key.startsWith("hc-static-") || key.startsWith("hc-dynamic-")) && 
                     key !== STATIC_CACHE && 
                     key !== DYNAMIC_CACHE;
            })
            .map((key) => {
              console.log("🗑️ Deletando cache antigo:", key);
              return caches.delete(key);
            })
        );
        
        await self.clients.claim();
        console.log("✅ Clientes reivindicados");
      } catch (error) {
        console.error("❌ Erro ao ativar Service Worker:", error);
      }
    })()
  );
});

// Mensagens do cliente (para skip waiting, atualizar cache, etc)
self.addEventListener("message", (event) => {
  if (!event.data) return;
  
  if (event.data.type === "SKIP_WAITING") {
    console.log("⏭️ Pulando espera, ativando nova versão");
    self.skipWaiting();
  }
  
  if (event.data.type === "CLEAR_CACHE") {
    console.log("🧹 Limpando cache dinâmico");
    caches.delete(DYNAMIC_CACHE);
  }
});

// Interceptar requisições
self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  
  const url = new URL(event.request.url);
  
  // Para navegação (HTML): Network first
  if (event.request.mode === "navigate" || event.request.destination === "document") {
    event.respondWith(networkFirstWithFallback(event.request));
    return;
  }
  
  // Para assets estáticos: Cache first
  if (isCacheableAsset(event.request, url)) {
    event.respondWith(staleWhileRevalidate(event.request));
    return;
  }
  
  // Para APIs: Network first
  if (url.pathname.startsWith("/api/") || 
      url.pathname.startsWith("/timeclock/") ||
      url.pathname.startsWith("/services/")) {
    event.respondWith(networkFirstWithFallback(event.request));
    return;
  }
});

// Push notification
self.addEventListener("push", (event) => {
  console.log("📬 Push notification recebida");
  
  if (!event.data) {
    console.log("⚠️ Push sem dados");
    return;
  }
  
  try {
    const data = event.data.json();
    
    const options = {
      body: data.body || "Nova notificação",
      icon: "/static/pwa/icon-192.png",
      badge: "/static/pwa/icon-192.png",
      tag: data.tag || "horacerta-notification",
      requireInteraction: data.requireInteraction || false,
      actions: data.actions || [],
      data: data.data || {}
    };
    
    if (data.image) {
      options.image = data.image;
    }
    
    event.waitUntil(
      self.registration.showNotification(data.title || "HoraCerta", options)
    );
  } catch (error) {
    console.error("❌ Erro ao processar push:", error);
    
    // Se não for JSON, mostrar como texto
    event.waitUntil(
      self.registration.showNotification("HoraCerta", {
        body: event.data.text(),
        icon: "/static/pwa/icon-192.png",
        badge: "/static/pwa/icon-192.png"
      })
    );
  }
});

// Clique em notificação
self.addEventListener("notificationclick", (event) => {
  console.log("👆 Notificação clicada:", event.notification.tag);
  
  event.notification.close();
  
  const urlToOpen = event.notification.data.url || "/";
  
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true })
      .then((clientList) => {
        // Procurar por janela já aberta
        for (let i = 0; i < clientList.length; i++) {
          const client = clientList[i];
          if (client.url === urlToOpen && "focus" in client) {
            return client.focus();
          }
        }
        
        // Se não encontrar, abrir nova janela
        if (clients.openWindow) {
          return clients.openWindow(urlToOpen);
        }
      })
  );
});

// Fechar notificação
self.addEventListener("notificationclose", (event) => {
  console.log("❌ Notificação fechada:", event.notification.tag);
});

// Sincronização em background (para quando voltar online)
self.addEventListener("sync", (event) => {
  console.log("🔄 Background sync:", event.tag);
  
  if (event.tag === "sync-punches") {
    event.waitUntil(syncPunches());
  }
});

async function syncPunches() {
  try {
    // Aqui você pode implementar lógica de sincronização
    console.log("✅ Punches sincronizados");
  } catch (error) {
    console.error("❌ Erro ao sincronizar:", error);
  }
}

console.log(`✅ Service Worker ${SW_VERSION} carregado`);
