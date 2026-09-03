(async function loadPublicHeader() {
  const mount = document.querySelector('[data-public-header]');
  if (!mount) return;

  try {
    const response = await fetch('/assets/public_header.html?v=20260511b', {
      cache: 'no-store',
    });
    if (!response.ok) return;
    mount.innerHTML = await response.text();

    const path = (window.location.pathname || '/').replace(/\/+$/, '') || '/';
    const activeKey =
      path === '/' || path === '/live' || path.startsWith('/live/')
        ? 'live'
        : path === '/fixtures'
          ? 'fixtures'
          : path === '/rankings'
            ? 'rankings'
            : path === '/clubs'
              ? 'clubs'
              : path === '/signin'
                ? 'signin'
                : path === '/register'
                  ? 'register'
                  : null;

    mount.querySelectorAll('[data-public-nav]').forEach((link) => {
      const isActive = activeKey && link.dataset.publicNav === activeKey;
      link.classList.toggle('is-active', isActive);
      if (isActive) {
        link.setAttribute('aria-current', 'page');
      } else {
        link.removeAttribute('aria-current');
      }
    });
  } catch (error) {
    console.warn('Failed to load public header', error);
  }
})();
