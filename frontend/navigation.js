/* Responsive navigation drawer. The same role-specific menu is used at every size. */
(() => {
  const sidebar = document.getElementById('appSidebar');
  const main = document.getElementById('appMain');
  const toggle = document.getElementById('navToggle');
  const closeButton = document.getElementById('navClose');
  const backdrop = document.getElementById('navBackdrop');
  const mobile = window.matchMedia('(max-width: 860px)');
  let open = false;

  function sync() {
    const modal = mobile.matches && open;
    sidebar.classList.toggle('is-open', modal);
    sidebar.inert = mobile.matches && !modal;
    main.inert = modal;
    backdrop.classList.toggle('hidden', !modal);
    document.body.classList.toggle('nav-open', modal);
    toggle.setAttribute('aria-expanded', String(modal));
    toggle.setAttribute('aria-label', modal ? 'Close menu' : 'Open menu');
    if (mobile.matches) {
      sidebar.setAttribute('aria-hidden', String(!modal));
      if (modal) {
        sidebar.setAttribute('role', 'dialog');
        sidebar.setAttribute('aria-modal', 'true');
      } else {
        sidebar.removeAttribute('role');
        sidebar.removeAttribute('aria-modal');
      }
    } else {
      sidebar.removeAttribute('aria-hidden');
      sidebar.removeAttribute('role');
      sidebar.removeAttribute('aria-modal');
    }
  }

  function close(restoreFocus = true) {
    const wasOpen = open;
    open = false;
    sync();
    if (wasOpen && restoreFocus && mobile.matches && !document.getElementById('app').classList.contains('hidden')) toggle.focus();
  }

  toggle.addEventListener('click', () => {
    if (open) return close();
    if (!mobile.matches) return;
    open = true;
    sync();
    // Let the browser finish applying inert/visibility before moving keyboard focus.
    setTimeout(() => { if (open && mobile.matches && !sidebar.contains(document.activeElement)) closeButton.focus(); }, 250);
  });
  closeButton.addEventListener('click', () => close());
  backdrop.addEventListener('click', () => close());
  document.getElementById('nav').addEventListener('click', e => {
    if (e.target.closest('button[data-page]')) close();
  });
  window.addEventListener('rn:logout', () => close(false));
  document.addEventListener('keydown', e => {
    if (!open || !mobile.matches) return;
    if (e.key === 'Escape') {
      e.preventDefault();
      close();
    } else if (e.key === 'Tab') {
      const items = [...sidebar.querySelectorAll('button:not([disabled])')].filter(el => el.getClientRects().length);
      if (!items.length) return;
      const first = items[0], last = items[items.length - 1];
      if (e.shiftKey && (document.activeElement === first || !sidebar.contains(document.activeElement))) {
        e.preventDefault(); last.focus();
      } else if (!e.shiftKey && (document.activeElement === last || !sidebar.contains(document.activeElement))) {
        e.preventDefault(); first.focus();
      }
    }
  });
  const onViewportChange = () => {
    const focusedSidebar = sidebar.contains(document.activeElement);
    const wasOpen = open;
    open = false;
    sync();
    if (mobile.matches && focusedSidebar) toggle.focus();
    else if (!mobile.matches && wasOpen) sidebar.querySelector('button[aria-current="page"]')?.focus();
  };
  if (mobile.addEventListener) mobile.addEventListener('change', onViewportChange);
  else mobile.addListener(onViewportChange);
  sync();
})();
