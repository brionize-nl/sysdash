// SysDash service worker — netwerk-eerst, zelf-verversend.
// BELANGRIJK: hoog CACHE_VERSION op bij elke web-wijziging → oude cache wordt gewist.
const CACHE_VERSION = "sysdash-v5";
const SHELL = ["./", "./index.html", "./style.css", "./app.js", "./config.js", "./assets/bg.jpg", "./assets/icon-192.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE_VERSION).then(c => c.addAll(SHELL)).catch(()=>{}));
  self.skipWaiting();  // nieuwe versie neemt meteen over
});

self.addEventListener("activate", e => {
  // wis ALLE oude caches (andere versienamen)
  e.waitUntil(
    caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE_VERSION).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  const u = e.request.url;
  if (u.includes("supabase.co") || new URL(u).pathname.startsWith("/api/") || !["GET"].includes(e.request.method) || new URL(u).origin !== self.location.origin || new URL(u).pathname.endsWith("config.js")) return;  // data altijd rechtstreeks (nooit cachen)
  // NETWERK-EERST: haal verse versie, val alleen terug op cache bij offline.
  // cache:"no-store" is nodig omdat de webserver geen Cache-Control-header stuurt — zonder dit
  // mag de browser zelf óók nog heuristisch cachen (RFC 7234), bovenop de service-worker-cache
  // hieronder. Zonder deze regel bleef "netwerk-eerst" soms toch een oude versie tonen (22 aug).
  e.respondWith(
    fetch(e.request, { cache: "no-store" }).then(resp => {
      // verse kopie in de cache leggen voor offline-gebruik
      const copy = resp.clone();
      caches.open(CACHE_VERSION).then(c => c.put(e.request, copy)).catch(()=>{});
      return resp;
    }).catch(() => caches.match(e.request).then(r => r || caches.match("./index.html")))
  );
});
