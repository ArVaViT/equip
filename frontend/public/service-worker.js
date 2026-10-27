const SHELL_CACHE = "equip-offline-shell-v1"
const COURSE_IMAGE_CACHE = "equip-course-images-v1"
const CACHE_PREFIX = "equip-"

self.addEventListener("install", (event) => {
  event.waitUntil(
    Promise.all([caches.open(SHELL_CACHE).then((cache) => cache.add("/")), self.skipWaiting()]),
  )
})

self.addEventListener("activate", (event) => {
  event.waitUntil(
    Promise.all([
      caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key.startsWith(CACHE_PREFIX) && key !== SHELL_CACHE && key !== COURSE_IMAGE_CACHE)
          .map((key) => caches.delete(key)),
      ),
      ),
      self.clients.claim(),
    ]),
  )
})

self.addEventListener("fetch", (event) => {
  const request = event.request
  if (request.method !== "GET") return

  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok && response.headers.get("content-type")?.includes("text/html")) {
            const copy = response.clone()
            void caches.open(SHELL_CACHE).then((cache) => cache.put("/", copy))
          }
          return response
        })
        .catch(async () => {
          const cached = await caches.match("/", { cacheName: SHELL_CACHE })
          if (cached) return cached
          return new Response("Offline page unavailable", {
            status: 503,
            headers: { "Content-Type": "text/plain; charset=utf-8" },
          })
        }),
    )
    return
  }

  if (
    url.search === "" &&
    (url.pathname.startsWith("/assets/") || url.pathname === "/locale-boot.js")
  ) {
    event.respondWith(
      caches.open(SHELL_CACHE).then(async (cache) => {
        const cached = await cache.match(request)
        if (cached) return cached
        const response = await fetch(request)
        if (response.ok && response.type === "basic") await cache.put(request, response.clone())
        return response
      }),
    )
    return
  }

  const imagePath = url.pathname.slice("/img/course-assets/".length)
  const safeImagePath =
    url.pathname.startsWith("/img/course-assets/") &&
    imagePath.length > 0 &&
    imagePath.split("/").every((segment) => segment !== "." && segment !== ".." && /^[A-Za-z0-9._-]+$/.test(segment))
  if (safeImagePath && url.search === "") {
    event.respondWith(
      fetch(request)
        .then(async (response) => {
          const contentType = response.headers.get("content-type")?.split(";", 1)[0]?.trim().toLowerCase()
          const cacheableImage =
            contentType === "image/jpeg" ||
            contentType === "image/png" ||
            contentType === "image/webp" ||
            contentType === "image/gif" ||
            contentType === "image/avif"
          if (response.ok && response.type === "basic" && cacheableImage) {
            const cache = await caches.open(COURSE_IMAGE_CACHE)
            await cache.put(request, response.clone())
            const requests = await cache.keys()
            if (requests.length > 200) await cache.delete(requests[0])
          }
          return response
        })
        .catch(async () => {
          const cached = await caches.match(request, { cacheName: COURSE_IMAGE_CACHE })
          if (cached) return cached
          throw new Error("Course image is unavailable offline")
        }),
    )
  }
})
