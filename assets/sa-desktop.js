/* SYNOR — desktop mega-menu behaviour.
   Only ever runs at the desktop breakpoint; the mobile drawer is left alone. */
(function () {
  var DESKTOP = '(min-width: 900px)';
  var OPEN_DELAY = 90;
  var CLOSE_DELAY = 180;

  function setup(root) {
    if (root.dataset.shdReady) return;
    root.dataset.shdReady = '1';

    var items = Array.prototype.slice.call(root.querySelectorAll('[data-mega]'));
    var panes = Array.prototype.slice.call(root.querySelectorAll('[data-megapane]'));
    if (!items.length) return;

    var openTimer = null;
    var closeTimer = null;
    var current = null;

    function clearTimers() {
      clearTimeout(openTimer);
      clearTimeout(closeTimer);
    }

    function show(key) {
      current = key;
      items.forEach(function (it) {
        var on = it.dataset.mega === key;
        it.classList.toggle('on', on);
        var link = it.querySelector('.shd-link');
        if (link) link.setAttribute('aria-expanded', on ? 'true' : 'false');
      });
      panes.forEach(function (p) {
        p.hidden = p.dataset.megapane !== key;
      });
    }

    function hide() {
      current = null;
      items.forEach(function (it) {
        it.classList.remove('on');
        var link = it.querySelector('.shd-link');
        if (link) link.setAttribute('aria-expanded', 'false');
      });
      panes.forEach(function (p) {
        p.hidden = true;
      });
    }

    function queueShow(key) {
      clearTimers();
      if (current === key) return;
      openTimer = setTimeout(function () {
        show(key);
      }, current ? 0 : OPEN_DELAY);
    }

    function queueHide() {
      clearTimers();
      closeTimer = setTimeout(hide, CLOSE_DELAY);
    }

    items.forEach(function (it) {
      var key = it.dataset.mega;
      it.addEventListener('mouseenter', function () {
        queueShow(key);
      });
      it.addEventListener('mouseleave', queueHide);
      it.addEventListener('focusin', function () {
        clearTimers();
        show(key);
      });
    });

    panes.forEach(function (p) {
      p.addEventListener('mouseenter', clearTimers);
      p.addEventListener('mouseleave', queueHide);
      p.addEventListener('focusin', clearTimers);
    });

    root.addEventListener('focusout', function (e) {
      if (!root.contains(e.relatedTarget)) queueHide();
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && current) {
        hide();
        var link = root.querySelector('.shd-item.on .shd-link');
        if (link) link.blur();
      }
    });
  }

  function init() {
    if (!window.matchMedia(DESKTOP).matches) return;
    Array.prototype.slice.call(document.querySelectorAll('[data-shd]')).forEach(setup);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }

  window.matchMedia(DESKTOP).addEventListener('change', init);

  // Theme editor re-renders the header section on every setting change.
  document.addEventListener('shopify:section:load', init);

  /* Keep the desktop bag count in step with the cart. The storefront updates
     the cart through several different code paths, so read the authoritative
     count from cart.js rather than trying to hook each of them. */
  function refreshCount() {
    var badges = document.querySelectorAll('[data-shd-count]');
    if (!badges.length) return;
    fetch(window.Shopify && window.Shopify.routes ? window.Shopify.routes.root + 'cart.js' : '/cart.js', {
      headers: { Accept: 'application/json' },
    })
      .then(function (r) {
        return r.ok ? r.json() : null;
      })
      .then(function (cart) {
        if (!cart) return;
        badges.forEach(function (b) {
          b.textContent = cart.item_count;
          b.hidden = cart.item_count === 0;
        });
      })
      .catch(function () {
        /* leave the server-rendered count in place */
      });
  }

  document.addEventListener('cart:refresh', refreshCount);
  if (window.PUB_SUB_EVENTS && window.subscribe) {
    window.subscribe(window.PUB_SUB_EVENTS.cartUpdate, refreshCount);
  }
})();
