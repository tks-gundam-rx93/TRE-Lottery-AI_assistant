'use strict';
/** PWA shell status is separate from API availability and prediction success. */
(() => {
  const $ = id => document.getElementById(id);
  let registration = null;
  let installPrompt = null;
  let reloading = false;
  const standalone = () => window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
  function showState() {
    const status = $('pwa-status');
    const installed = standalone();
    if (status) status.textContent = !navigator.onLine
      ? 'オフライン：画面と対応端末の音声試聴を利用できます。予測・CSV取込には通信が必要です。'
      : installed ? 'ホーム画面から起動中。予測・CSV取込はオンラインで利用します。'
      : 'Safariの共有メニューから「ホーム画面に追加」すると、アプリとして起動できます。';
    if ($('pwa-install-guide')) $('pwa-install-guide').hidden = installed;
  }
  window.trePwa = {
    async fetch(input, options = {}) {
      if (!navigator.onLine) throw new Error('オフラインです。通信を再開してから実行してください。');
      const controller = new AbortController();
      const warning = setTimeout(() => {
        if ($('pwa-status')) $('pwa-status').textContent = 'サーバーの応答を待っています。初回起動には約1分かかる場合があります。';
      }, 10000);
      const deadline = setTimeout(() => controller.abort(), 90000);
      try {
        return await window.fetch(input, {...options, cache: 'no-store', signal: controller.signal});
      } catch (error) {
        if (error.name === 'AbortError') throw new Error('サーバーの応答が時間内に届きませんでした。少し待って再実行してください。');
        if (error instanceof TypeError) throw new Error('サーバーに接続できません。通信を確認し、少し待って再実行してください。');
        throw error;
      } finally { clearTimeout(warning); clearTimeout(deadline); showState(); }
    },
    async json(response) {
      if (!(response.headers.get('content-type') || '').includes('application/json')) {
        throw new Error('サーバーが起動中、または利用できません。少し待って再実行してください。');
      }
      return response.json();
    }
  };
  function updateAvailable() {
    if ($('pwa-update')) $('pwa-update').hidden = false;
  }
  window.addEventListener('online', showState);
  window.addEventListener('offline', showState);
  window.addEventListener('appinstalled', () => { installPrompt = null; showState(); });
  window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault(); installPrompt = event;
    if ($('pwa-install')) $('pwa-install').hidden = false;
  });
  document.addEventListener('DOMContentLoaded', async () => {
    showState();
    $('pwa-install')?.addEventListener('click', async () => {
      if (!installPrompt) return;
      await installPrompt.prompt(); await installPrompt.userChoice;
      installPrompt = null; $('pwa-install').hidden = true;
    });
    $('pwa-update')?.addEventListener('click', () => {
      if (registration?.waiting) registration.waiting.postMessage({type: 'ACTIVATE_UPDATE'});
    });
    if (!window.isSecureContext) {
      $('pwa-status').textContent = 'ホーム画面追加とマイク入力にはHTTPSのURLをSafariで開いてください。';
      return;
    }
    if (!('serviceWorker' in navigator)) {
      $('pwa-status').textContent += ' このブラウザはオフライン起動に未対応です。';
      return;
    }
    try {
      registration = await navigator.serviceWorker.register('/sw.js', {scope: '/', updateViaCache: 'none'});
      if (registration.waiting) updateAvailable();
      registration.addEventListener('updatefound', () => {
        const installing = registration.installing;
        installing?.addEventListener('statechange', () => {
          if (installing.state === 'installed' && navigator.serviceWorker.controller) updateAvailable();
        });
      });
      navigator.serviceWorker.addEventListener('controllerchange', () => {
        // Only a user-requested update reloads the current page; first install preserves the boot gesture.
        if ($('pwa-update')?.hidden === false && !reloading) { reloading = true; location.reload(); }
      });
    } catch {
      $('pwa-status').textContent += ' オフライン用の保存に失敗しました。通信中はそのまま利用できます。';
    }
  });
})();
