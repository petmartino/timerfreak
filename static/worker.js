// TimerFreak Service Worker
// Uses relative paths to work with any deployment base URL

const CACHE_NAME = 'timerfreak-cache-v1';
const ASSETS_TO_CACHE = [
    './',
    './static/style.css',
    './static/worker.js',
    './static/manifest.json',
    './static/logotimerfreak.svg'
];

self.addEventListener('install', e => {
    e.waitUntil(
        caches.open(CACHE_NAME).then(cache => {
            return cache.addAll(ASSETS_TO_CACHE).catch(err => {
                console.warn('Some assets failed to cache:', err);
                // Continue even if some assets fail
                return Promise.resolve();
            });
        })
    );
    // Activate immediately
    self.skipWaiting();
});

self.addEventListener('activate', e => {
    // Clean up old caches
    e.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames
                    .filter(name => name !== CACHE_NAME)
                    .map(name => caches.delete(name))
            );
        })
    );
    // Claim all clients
    self.clients.claim();
});

self.addEventListener('fetch', e => {
    // Only handle GET requests
    if (e.request.method !== 'GET') return;
    
    // Skip cross-origin requests
    if (!e.request.url.startsWith(self.location.origin)) return;
    
    e.respondWith(
        caches.match(e.request).then(response => {
            // Return cached response if found
            if (response) {
                return response;
            }
            // Clone the request
            const fetchRequest = e.request.clone();
            // Fetch from network
            return fetch(fetchRequest).then(response => {
                // Don't cache non-successful responses
                if (!response || response.status !== 200 || response.type !== 'basic') {
                    return response;
                }
                // Clone the response
                const responseToCache = response.clone();
                // Add to cache
                caches.open(CACHE_NAME).then(cache => {
                    cache.put(e.request, responseToCache);
                });
                return response;
            }).catch(err => {
                console.warn('Fetch failed:', err);
                // Return offline fallback if available
                return null;
            });
        })
    );
});
