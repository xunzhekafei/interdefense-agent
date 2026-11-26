/* InterDefense Studio 的 Service Worker。
 *
 * 只做三件事：
 *   1. 让页面可安装（配合 manifest.webmanifest）；
 *   2. 静态资源缓存优先，断网/弱网时仍能打开界面；
 *   3. 导航请求网络优先，保证部署新版本后不会被旧页面锁住。
 *
 * 明确不缓存 /api 与 WebSocket：面试对话、评分、登录态都是实时的，
 * 缓存它们会让用户看到过期数据，这比「离线打不开」更危险。
 *
 * 本应用只有一个入口 bundle，没有按需加载的 chunk，所以新版本激活时
 * 可以放心清掉旧缓存；以后若加了代码分割，需要改成保留上一版缓存。
 */
const VERSION = "v1";
const CACHE = `interdefense-${VERSION}`;
const SHELL = ["/", "/manifest.webmanifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)),
      );
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/")) return;   // 实时数据，交给网络

  if (request.mode === "navigate") {
    event.respondWith(
      (async () => {
        try {
          const fresh = await fetch(request);
          const cache = await caches.open(CACHE);
          cache.put("/", fresh.clone());
          return fresh;
        } catch {
          const cache = await caches.open(CACHE);
          return (await cache.match("/")) || (await cache.match("/index.html")) ||
            Response.error();
        }
      })(),
    );
    return;
  }

  event.respondWith(
    (async () => {
      const cache = await caches.open(CACHE);
      const hit = await cache.match(request);
      if (hit) return hit;
      const fresh = await fetch(request);
      if (fresh.ok) cache.put(request, fresh.clone());
      return fresh;
    })(),
  );
});
