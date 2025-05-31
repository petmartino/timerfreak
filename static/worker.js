self.addEventListener('install', e => {
    e.waitUntil(
        caches.open('timerfreak-cache').then(cache => {
            return cache.addAll([
                '/timerfreak/',
                '/timerfreak/static/app.js',
                '/timerfreak/static/alarm.mp3',
                '/timerfreak/static/style.css',
                '/timerfreak/static/manifest.json'
            ]);
        })
    );
});

self.addEventListener('fetch', e => {
    e.respondWith(
        caches.match(e.request).then(response => response || fetch(e.request))
    );
});
