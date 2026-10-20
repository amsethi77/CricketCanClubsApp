// Dark / light mode + navbar search (site_tools.js). Apply the saved theme right away to avoid a flash.
(function loadSiteTools() {
  try {
    if (localStorage.getItem("cricketClubAppTheme") === "dark") document.documentElement.setAttribute("data-theme", "dark");
  } catch (e) { /* ignore */ }
  // Public AI Assistant (read-only chat for signed-out visitors). See README.md -> "Public AI Assistant".
  if (!document.querySelector('script[src^="/assets/muse_public.js"]')) {
    const muse = document.createElement("script");
    muse.src = "/assets/muse_public.js?v=20261018a";
    muse.defer = true;
    document.head.appendChild(muse);
  }
  if (document.querySelector('script[src^="/assets/site_tools.js"]')) return;
  const script = document.createElement("script");
  script.src = "/assets/site_tools.js";
  document.head.appendChild(script);
})();

(async function loadPublicHeader() {
  const mount = document.querySelector('[data-public-header]');
  if (!mount) return;

  try {
    const response = await fetch('/assets/public_header.html?v=20261016b', {
      cache: 'no-store',
    });
    if (!response.ok) return;
    mount.innerHTML = await response.text();
    showSignedInLinks(mount);

    const path = (window.location.pathname || '/').replace(/\/+$/, '') || '/';
    const activeKey =
      path === '/' || path === '/live' || path.startsWith('/live/')
        ? 'live'
        : path === '/fixtures'
          ? 'fixtures'
          : path === '/rankings'
            ? 'rankings'
            : path === '/scorecards' || path.startsWith('/scorecards/')
            ? 'scorecards'
            : path === '/clubs'
              ? 'clubs'
              : path === '/signin'
                ? 'signin'
                : path === '/register'
                  ? 'register'
                  : path === '/pricing'
                    ? 'pricing'
                    : path === '/score'
                      ? 'score'
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

    setupMoreMenu(mount);
  } catch (error) {
    console.warn('Failed to load public header', error);
  }
})();

/*
 * "More" menu (phone only - live.css hides the button on laptop).
 * Tapping More opens a dropdown with every link marked
 * class="nav-overflow-item" in public_header.html (Clubs, Sign In, Register).
 */
function setupMoreMenu(mount) {
  const moreButton = mount.querySelector('.nav-more-toggle');
  const nav = mount.querySelector('.top-nav');
  if (!moreButton || !nav) return;

  moreButton.setAttribute('aria-haspopup', 'menu');
  moreButton.setAttribute('aria-expanded', 'false');

  // If the open page is one of the links inside More (Clubs, Sign In, Register),
  // highlight the More button (it keeps its "More" label).
  const activeHidden = nav.querySelector('a.nav-overflow-item[aria-current="page"]');
  if (activeHidden) {
    const text = activeHidden.querySelector('.nav-text');
    moreButton.classList.add('is-active');
    moreButton.setAttribute('aria-label', `More menu, current page: ${text ? text.textContent : ''}`);
  }

  let menu = null;

  function closeMenu() {
    if (menu) menu.remove();
    menu = null;
    moreButton.setAttribute('aria-expanded', 'false');
  }

  function positionMenu() {
    if (!menu) return;
    const rect = moreButton.getBoundingClientRect();
    menu.style.top = `${rect.bottom + 8}px`;
    menu.style.right = `${Math.max(8, window.innerWidth - rect.right)}px`;
  }

  function openMenu() {
    menu = document.createElement('div');
    menu.className = 'nav-more-menu';
    menu.setAttribute('role', 'menu');

    nav.querySelectorAll('a.nav-overflow-item').forEach((link) => {
      const item = document.createElement('a');
      item.className = 'nav-more-menu-item';
      item.href = link.getAttribute('href');
      item.setAttribute('role', 'menuitem');
      if (link.getAttribute('aria-current') === 'page') {
        item.setAttribute('aria-current', 'page');
      }
      const icon = link.querySelector('.nav-icon');
      const text = link.querySelector('.nav-text');
      item.innerHTML =
        `<span class="nav-more-menu-icon" aria-hidden="true">${icon ? icon.textContent : ''}</span>` +
        `<span>${text ? text.textContent : link.textContent.trim()}</span>`;
      menu.appendChild(item);
    });

    // Dark mode is the moon button next to search, so it isn't repeated here.
    document.body.appendChild(menu); // on <body> so nothing can clip it
    moreButton.setAttribute('aria-expanded', 'true');
    positionMenu();
  }

  moreButton.addEventListener('click', (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (menu) closeMenu();
    else openMenu();
  });

  // Close when tapping outside, pressing Esc, or rotating/resizing the screen.
  document.addEventListener('click', (event) => {
    if (menu && !menu.contains(event.target)) closeMenu();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && menu) {
      closeMenu();
      moreButton.focus();
    }
  });
  window.addEventListener('resize', closeMenu);
  window.addEventListener('scroll', positionMenu, { passive: true });
}

// Adds "Dark mode" / "Light mode" to a More menu (phones have no room for the toggle in the row).
function appendThemeMenuItem(menu, itemClass, iconClass, closeMenu) {
  const tools = window.CCSiteTools;
  if (!tools) return;
  const label = tools.themeMenuLabel();
  const item = document.createElement('a');
  item.href = '#';
  item.className = itemClass + ' theme-menu-item';
  item.setAttribute('role', 'menuitem');
  item.innerHTML = `<span class="${iconClass}" aria-hidden="true">${label.icon}</span><span>${label.text}</span>`;
  item.addEventListener('click', (event) => {
    event.preventDefault();
    tools.toggleTheme();
    closeMenu();
  });
  menu.appendChild(item);
}

// Signed-in visitors on public pages (Scorecards, Fixtures, Live...) are still signed in: show
// "My dashboard" and "Sign out" instead of "Sign In" / "Register" so it doesn't look like a sign-out.
async function showSignedInLinks(mount) {
  let token = '';
  try {
    token = localStorage.getItem('cricketClubAppAuthToken') || '';
  } catch (e) {
    token = '';
  }
  if (!token) return;
  try {
    const response = await fetch('/api/auth/me', { headers: { 'X-Auth-Token': token } });
    if (!response.ok) return;
    const data = await response.json();
    const user = data.user || {};
    const signin = mount.querySelector('[data-public-nav="signin"]');
    const register = mount.querySelector('[data-public-nav="register"]');
    if (signin) {
      signin.href = '/dashboard';
      signin.dataset.publicNav = 'dashboard';
      signin.innerHTML = '<span class="nav-icon" aria-hidden="true">🏠</span><span class="nav-text">My dashboard</span>';
      signin.title = `Signed in as ${user.display_name || ''}`.trim();
    }
    if (register) {
      // Sign out is not in More: it gets its own button at the right end of the bar (laptop),
      // and stays in the phone ☰ menu (this link, hidden from the row and from More).
      register.href = '/signout';
      register.dataset.publicNav = 'signout';
      register.classList.remove('nav-overflow-item');
      register.innerHTML = '<span class="nav-icon" aria-hidden="true">🚪</span><span class="nav-text">Sign out</span>';
    }
    const header = mount.querySelector('.app-header');
    if (header && !header.querySelector('.public-signout')) {
      const out = document.createElement('a');
      out.className = 'public-signout';
      out.href = '/signout';
      out.textContent = 'Sign out';
      out.title = `Signed in as ${user.display_name || ''}`.trim();
      header.appendChild(out);
    }
    const heroActions = document.getElementById('homeHeroActions');
    if (heroActions) {
      heroActions.innerHTML = '<a class="home-btn primary" href="/dashboard">Go to my dashboard</a>';
    }
    document.body.dataset.signedIn = 'true';
    document.dispatchEvent(new CustomEvent('cc:signed-in', { detail: user }));
  } catch (e) {
    /* offline: leave the public links */
  }
}

