/* Script of the menu pages: progressive enhancement over finished HTML.

   1. The class js on <html> comes first; hidden initial states depend on it.
      No script, everything is visible.
   2. Module registry: register(name, init). Every init runs once the
      document is parsed, each in its own try/catch: one failing module
      leaves the others working.
   3. Modules hook onto data attributes only; is-* classes and the markers on
      <html> are states for the styles (assets/app.css).

   No build step, no dependencies; works under CSP script-src 'self' (no
   inline code, eval or new Function). The script has no interface text of
   its own: every word of the page lives in the markup. */
(function () {
  'use strict';

  document.documentElement.classList.add('js');

  var root = document.documentElement;


  /* ==========================================================================
     Module registry
     ========================================================================== */

  var modules = [];
  var started = false;

  /* The module name and the error type only, never page data. */
  function report(name, error) {
    console.warn('app: module "' + name + '" failed (' +
      (error && error.name ? error.name : 'Error') + ')');
  }

  /* init(document) runs once, when the DOM is parsed. */
  function register(name, init) {
    modules.push({ name: name, init: init });
  }

  function start() {
    if (started) {
      return;
    }
    started = true;
    modules.forEach(function (module) {
      try {
        module.init(document);
      } catch (error) {
        report(module.name, error);
      }
    });
  }

  /* The script is loaded with defer, so DOMContentLoaded is still ahead; the
     other branches cover other ways of loading. The listeners come before the
     modules: a failure while declaring a late module keeps the early ones. */
  document.addEventListener('DOMContentLoaded', start);
  window.addEventListener('load', start);
  if (document.readyState === 'complete') {
    setTimeout(start, 0);
  }

  function prefersReducedMotion() {
    return typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }


  /* ==========================================================================
     Module tabs - a tab switcher [data-tabs] (the sets of a menu)
     --------------------------------------------------------------------------
     Without the script every panel is shown and the tab list
     [data-tabs-tablist] stays hidden by its attribute. With it: ARIA Tabs,
     one panel visible; arrows (wrapping), Home and End, selection follows
     focus, tabindex="0" on the selected tab only. The first tab is selected.
     Roles and links of the panels are set here; ids come from the markup
     (aria-controls of each [data-tabs-tab]). The number of tabs goes to the
     styles as --tabs-count through CSSOM. Fewer than two tabs, or tabs and
     panels that do not pair one to one: nothing happens, everything stays
     visible.
     Any error restores the view without the script.

     Declared before reveal and started before it: hiding panels shortens
     the page, and reveal must measure the final layout.
     ========================================================================== */

  var TABS_STEPS = { ArrowLeft: -1, ArrowUp: -1, ArrowRight: 1, ArrowDown: 1 };

  function startTabs(widget) {
    var tablist = widget.querySelector('[data-tabs-tablist]');
    var tabs = tablist ? Array.prototype.slice.call(tablist.querySelectorAll('[data-tabs-tab]')) : [];
    var all = Array.prototype.slice.call(widget.querySelectorAll('[data-tabs-panel]'));
    var panels = tabs.map(function (tab) {
      var id = tab.getAttribute('aria-controls');
      return all.filter(function (panel) {
        return panel.id === id;
      })[0];
    });
    /* One panel, nothing to switch. Every panel must belong to exactly one
       tab: as many tabs as panels, each tab finds its panel and no panel is
       left out (so none is named twice). Otherwise the markup is wrong and
       everything stays visible. */
    if (tabs.length < 2 || panels.length !== all.length || panels.indexOf(undefined) !== -1 ||
        all.some(function (panel) { return panels.indexOf(panel) === -1; })) {
      return;
    }

    var labelledBy = panels.map(function (panel) {
      return panel.getAttribute('aria-labelledby');
    });

    function select(index, focus) {
      tabs.forEach(function (tab, i) {
        var on = i === index;
        tab.setAttribute('aria-selected', on ? 'true' : 'false');
        tab.tabIndex = on ? 0 : -1;
        panels[i].hidden = !on;
      });
      if (focus) {
        tabs[index].focus();
      }
    }

    /* The view without the script: the tab list hidden, every panel shown,
       roles removed, the original links back. */
    function restore() {
      tablist.hidden = true;
      tablist.style.removeProperty('--tabs-count');
      if (!tablist.getAttribute('style')) {
        tablist.removeAttribute('style');
      }
      panels.forEach(function (panel, i) {
        panel.hidden = false;
        panel.removeAttribute('role');
        panel.removeAttribute('tabindex');
        if (labelledBy[i]) {
          panel.setAttribute('aria-labelledby', labelledBy[i]);
        } else {
          panel.removeAttribute('aria-labelledby');
        }
      });
      tablist.removeEventListener('keydown', onKeyDown);
      tablist.removeEventListener('click', onClick);
    }

    function guarded(handler) {
      return function (event) {
        try {
          handler(event);
        } catch (error) {
          restore();
          report('tabs', error);
        }
      };
    }

    var onClick = guarded(function (event) {
      var tab = event.target && typeof event.target.closest === 'function' ?
        event.target.closest('[data-tabs-tab]') : null;
      var at = tabs.indexOf(tab);
      if (at !== -1) {
        select(at, false);
      }
    });

    var onKeyDown = guarded(function (event) {
      var at = tabs.indexOf(event.target);
      if (at === -1 || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) {
        return;
      }
      var last = tabs.length - 1;
      var step = TABS_STEPS[event.key];
      var to = event.key === 'Home' ? 0 : event.key === 'End' ? last :
        typeof step === 'number' ? (at + step + tabs.length) % tabs.length : -1;
      if (to === -1) {
        return;
      }
      event.preventDefault();
      select(to, true);
    });

    try {
      panels.forEach(function (panel, i) {
        panel.setAttribute('role', 'tabpanel');
        panel.setAttribute('tabindex', '0');
        panel.setAttribute('aria-labelledby', tabs[i].id);
      });
      tablist.style.setProperty('--tabs-count', String(tabs.length));
      select(0, false);
      tablist.addEventListener('keydown', onKeyDown);
      tablist.addEventListener('click', onClick);
      tablist.hidden = false;
    } catch (error) {
      restore();
      throw error;
    }
  }

  register('tabs', function (doc) {
    Array.prototype.forEach.call(doc.querySelectorAll('[data-tabs]'), function (widget) {
      try {
        startTabs(widget);
      } catch (error) {
        report('tabs', error);
      }
    });
  });


  /* ==========================================================================
     Module reveal - blocks [data-reveal] appearing on scroll
     --------------------------------------------------------------------------
     The hidden state applies only under the marker reveal-on on <html>; the
     marker is set as the last step and removed on any error. A shown block
     gets is-revealed and is no longer observed; once its transition is over
     it gets is-settled: the transition and the cascade delay stop applying
     and leave the element's own transitions alone.
     ========================================================================== */

  /* The share of the screen height a block must enter before it appears. 0:
     it starts with the first visible pixel, otherwise a band at the bottom
     edge would show a block that is on screen but still empty. */
  var REVEAL_INSET = 0;
  var REVEAL_MARGIN = '0px 0px -' + (REVEAL_INSET * 100) + '% 0px';
  var REVEAL_STAGGER_MAX = 4;   /* the longest cascade within one group */
  var REVEAL_SETTLE_MS = 2000;  /* a safety net when transitionend never comes */

  register('reveal', function (doc) {
    var pending = Array.prototype.slice.call(doc.querySelectorAll('[data-reveal]'));
    if (!pending.length || typeof window.IntersectionObserver !== 'function' ||
        prefersReducedMotion()) {
      return; /* no marker, everything visible */
    }

    var observer = null;
    var frame = 0;

    function viewportHeight() {
      return window.innerHeight || root.clientHeight;
    }

    /* The appearance is over: drop the transition, the delay and the style. */
    function settle(element) {
      if (element.classList.contains('is-settled')) {
        return;
      }
      element.classList.add('is-settled');
      element.style.removeProperty('--reveal-index');
      if (!element.getAttribute('style')) {
        element.removeAttribute('style');
      }
    }

    /* The end is only the real end of the block's own opacity transition.
       While scrolling, Chromium sends an extra transitionend with
       elapsedTime 0 in the first frame; taking it would drop the transition
       halfway and the block would jump into place. */
    function isRevealEnd(event, element) {
      if (event.target !== element) {
        return false; /* a transition of a nested element */
      }
      if (event.type === 'transitioncancel') {
        return true;
      }
      return event.propertyName === 'opacity' && event.elapsedTime > 0;
    }

    function settleLater(element) {
      var timer = 0;
      function done(event) {
        if (event && !isRevealEnd(event, element)) {
          return;
        }
        clearTimeout(timer);
        element.removeEventListener('transitionend', done);
        element.removeEventListener('transitioncancel', done);
        settle(element);
      }
      element.addEventListener('transitionend', done);
      element.addEventListener('transitioncancel', done);
      timer = setTimeout(done, REVEAL_SETTLE_MS);
    }

    /* order: the place in the group appearing together; instant: no transition. */
    function show(element, order, instant) {
      var at = pending.indexOf(element);
      if (at === -1) {
        return;
      }
      pending.splice(at, 1);
      if (observer) {
        observer.unobserve(element);
      }
      if (instant) {
        settle(element);
      } else {
        if (order > 0) {
          element.style.setProperty('--reveal-index', String(Math.min(order, REVEAL_STAGGER_MAX)));
        }
        settleLater(element);
      }
      element.classList.add('is-revealed');
      if (!pending.length) {
        finish();
      }
    }

    function finish() {
      if (observer) {
        observer.disconnect();
        observer = null;
      }
      if (frame && typeof window.cancelAnimationFrame === 'function') {
        window.cancelAnimationFrame(frame);
      }
      frame = 0;
      doc.removeEventListener('focusin', onFocusIn);
      window.removeEventListener('scroll', onViewportChange, true);
      window.removeEventListener('resize', onViewportChange);
      window.removeEventListener('orientationchange', onViewportChange);
      doc.removeEventListener('visibilitychange', onVisibilityChange);
      window.removeEventListener('pageshow', sweep);
    }

    function fail() {
      root.classList.remove('reveal-on');
      pending = [];
      finish();
    }

    /* Wraps the event handlers: after a failure everything stays visible. */
    function guarded(handler) {
      return function (argument) {
        try {
          handler(argument);
        } catch (error) {
          fail();
          report('reveal', error);
        }
      };
    }

    /* Shows everything already on screen or above it (a fast scroll, a jump
       to the end, a return from a background tab). inset: the share of the
       screen height from the bottom a block still has to enter. */
    function sweepWithin(inset) {
      var limit = viewportHeight() * (1 - inset);
      var order = 0;
      pending.slice().forEach(function (element) {
        var rect = element.getBoundingClientRect();
        if (rect.bottom <= 0) {
          show(element, 0, true);
        } else if (rect.top < limit) {
          show(element, order, false);
          order += 1;
        }
      });
    }

    var sweep = guarded(function () {
      sweepWithin(0);
    });

    /* Keyboard focus inside a block still hidden: show it at once. */
    var onFocusIn = guarded(function (event) {
      var node = event.target;
      while (node && node.nodeType === 1) {
        if (node.hasAttribute('data-reveal')) {
          show(node, 0, true);
        }
        node = node.parentElement;
      }
    });

    /* Scroll, resize or rotation: a check that does not depend on the
       observer, at most once a frame. Near the very end of the page a block
       may never reach the inset, so there it is dropped. The end belongs to
       body when body scrolls, otherwise to the document. */
    function atEnd() {
      var body = doc.body;
      if (window.getComputedStyle(body).overflowY !== 'visible') {
        return body.scrollTop + body.clientHeight >= body.scrollHeight - 2;
      }
      return viewportHeight() + window.pageYOffset >= root.scrollHeight - 2;
    }

    var onFrame = guarded(function () {
      frame = 0;
      sweepWithin(atEnd() ? 0 : REVEAL_INSET);
    });

    function onViewportChange() {
      if (frame) {
        return;
      }
      if (typeof window.requestAnimationFrame === 'function') {
        frame = window.requestAnimationFrame(onFrame);
      } else {
        onFrame();
      }
    }

    var onVisibilityChange = guarded(function () {
      if (!doc.hidden) {
        sweep();
      }
    });

    var onIntersect = guarded(function (entries) {
      var order = 0;
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          show(entry.target, order, false);
          order += 1;
        }
      });
      /* Blocks a scroll jumped over give no intersection. */
      var passed = pending.filter(function (element) {
        return element.getBoundingClientRect().bottom <= 0;
      });
      passed.forEach(function (element) {
        show(element, 0, true);
      });
    });

    try {
      /* Blocks visible at load are shown before the hidden state is on:
         they are never hidden, so they never flicker. */
      var limit = viewportHeight();
      pending.slice().forEach(function (element) {
        if (element.getBoundingClientRect().top < limit) {
          show(element, 0, true);
        }
      });
      if (!pending.length) {
        return;
      }

      observer = new window.IntersectionObserver(onIntersect, {
        rootMargin: REVEAL_MARGIN,
        threshold: 0
      });
      pending.forEach(function (element) {
        observer.observe(element);
      });
      doc.addEventListener('focusin', onFocusIn);
      /* Capture: the scroll of an inner scroller does not bubble to window. */
      window.addEventListener('scroll', onViewportChange, { passive: true, capture: true });
      window.addEventListener('resize', onViewportChange);
      window.addEventListener('orientationchange', onViewportChange);
      doc.addEventListener('visibilitychange', onVisibilityChange);
      window.addEventListener('pageshow', sweep);

      root.classList.add('reveal-on');
    } catch (error) {
      fail();
      throw error;
    }
  });


  /* ==========================================================================
     Further modules
     --------------------------------------------------------------------------
     Each module is a block below this line, inside this same function:

       register('name', function (doc) {
         // find its elements by data attributes; none, return
       });

     A module relies neither on other modules nor on their order; it passes
     state to the styles with is-* classes and CSS variables set through
     style.setProperty.
     ========================================================================== */

}());
