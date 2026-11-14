/* PWA glue: service-worker registration, install button, offline banner, mobile logout. */
(() => {
  const secure = location.protocol === 'https:' || ['localhost', '127.0.0.1'].includes(location.hostname);
  if ('serviceWorker' in navigator && secure) window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => {}));

  let deferred = null;
  const buttons = () => document.querySelectorAll('.installBtn');
  window.addEventListener('beforeinstallprompt', e => { e.preventDefault(); deferred = e; buttons().forEach(b => b.classList.remove('hidden')); });
  window.addEventListener('appinstalled', () => { deferred = null; buttons().forEach(b => b.classList.add('hidden')); });
  document.addEventListener('click', async e => {
    if (!e.target.closest('.installBtn') || !deferred) return;
    deferred.prompt(); await deferred.userChoice; deferred = null; buttons().forEach(b => b.classList.add('hidden'));
  });

  const bar = document.getElementById('offlineBar');
  const sync = () => bar && bar.classList.toggle('hidden', navigator.onLine);
  window.addEventListener('online', sync); window.addEventListener('offline', sync); sync();

  const out = document.getElementById('logout2'), real = document.getElementById('logout');
  if (out && real) out.addEventListener('click', () => real.click());
})();
