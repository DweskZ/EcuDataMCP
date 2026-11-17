/* Home page behavior: atlas map, chat-style example conversation, theme
   explorer, client tabs and the logo carousel. Vanilla JS. Everything it
   needs (sources, themes, transcripts, UI strings) comes from the
   #home-data JSON island that build.py derives from web/data/*.json. */
(function () {
  "use strict";

  var dataEl = document.getElementById("home-data");
  if (!dataEl) return;
  var D = JSON.parse(dataEl.textContent);
  var UI = D.ui;
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function $(id) { return document.getElementById(id); }
  function all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function scrollToEl(el, block) {
    el.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: block || "start" });
  }
  // Tiny **bold** parser that builds DOM nodes (no innerHTML on data).
  function richText(parent, text) {
    text.split("**").forEach(function (part, i) {
      if (!part) return;
      if (i % 2) {
        var b = document.createElement("b");
        b.textContent = part;
        parent.appendChild(b);
      } else {
        parent.appendChild(document.createTextNode(part));
      }
    });
  }
  // Roving-tabindex tablist (arrow keys, Home, End).
  function tablist(list, onSelect) {
    var tabs = all('[role="tab"]', list);
    function select(i, focus, user) {
      tabs.forEach(function (tab, j) {
        tab.setAttribute("aria-selected", j === i ? "true" : "false");
        tab.tabIndex = j === i ? 0 : -1;
      });
      if (focus) tabs[i].focus();
      onSelect(i, !!user);
    }
    tabs.forEach(function (tab, i) {
      tab.addEventListener("click", function () { select(i, false, true); });
      tab.addEventListener("keydown", function (e) {
        var to;
        if (e.key === "ArrowRight") to = (i + 1) % tabs.length;
        else if (e.key === "ArrowLeft") to = (i - 1 + tabs.length) % tabs.length;
        else if (e.key === "Home") to = 0;
        else if (e.key === "End") to = tabs.length - 1;
        else return;
        e.preventDefault();
        select(to, true, true);
      });
    });
    return { select: select, tabs: tabs };
  }

  /* ---------------------------------------------------------------- map */

  var wrap = $("atlasWrap");
  var tip = $("tip");
  var dots = all(".dot", wrap);
  var chips = all(".chip[data-i]");
  var themeBtns = all("#themes button");
  var groups = all(".src-group");
  var listEl = $("list");
  var listHead = $("listHead");
  var activeTheme = null; // theme currently filtering the map

  var SEC = {
    sources: $("fuentes") || $("sources"),
    how: $("como-funciona") || $("how-it-works")
  };

  function themeName(i) { return D.themes[i].name; }

  function paintDots() {
    dots.forEach(function (d) {
      var k = +d.getAttribute("data-k");
      var t = +d.getAttribute("data-t");
      var show = true;
      if (activeTheme !== null) show = t === activeTheme;
      d.classList.toggle("dim", !show);
    });
  }

  function showExplorer(i) {
    themeBtns.forEach(function (b) {
      b.setAttribute("aria-pressed", +b.getAttribute("data-i") === i ? "true" : "false");
    });
    groups.forEach(function (g) { g.hidden = +g.getAttribute("data-i") !== i; });
    listHead.textContent = "";
    listHead.appendChild(document.createTextNode(themeName(i) + " "));
    var n = document.createElement("span");
    n.textContent = "· " + D.themes[i].n;
    listHead.appendChild(n);
    listEl.scrollTop = 0;
  }

  // force=true selects the theme; otherwise clicking the active theme clears it.
  function setTheme(i, force) {
    activeTheme = !force && activeTheme === i ? null : i;
    chips.forEach(function (c) {
      c.setAttribute("aria-pressed", +c.getAttribute("data-i") === activeTheme ? "true" : "false");
    });
    paintDots();
    showExplorer(activeTheme === null ? defaultTheme : activeTheme);
  }
  var defaultTheme = +themeBtns[0].getAttribute("data-i");

  chips.forEach(function (c) {
    c.addEventListener("click", function () { setTheme(+c.getAttribute("data-i"), false); });
  });
  themeBtns.forEach(function (b) {
    b.addEventListener("click", function () { setTheme(+b.getAttribute("data-i"), true); });
  });

  function showTip(el) {
    var s = D.sources[+el.getAttribute("data-k")];
    tip.textContent = "";
    var b = document.createElement("b");
    b.textContent = s.n;
    tip.appendChild(b);
    tip.appendChild(document.createTextNode(s.i));
    tip.appendChild(document.createElement("br"));
    var span = document.createElement("span");
    span.textContent = themeName(s.t);
    tip.appendChild(span);
    var w = wrap.getBoundingClientRect();
    var r = el.querySelector(".pt").getBoundingClientRect();
    var x = r.left - w.left + r.width / 2 + 12;
    var y = r.top - w.top + r.height / 2 + 12;
    x = Math.max(4, Math.min(x, w.width - tip.offsetWidth - 4));
    if (y + tip.offsetHeight > w.height) y = r.top - w.top - tip.offsetHeight - 8;
    tip.style.left = x + "px";
    tip.style.top = y + "px";
    tip.style.opacity = 1;
  }
  function hideTip() { tip.style.opacity = 0; }

  function focusDot(i) {
    i = (i + dots.length) % dots.length;
    dots.forEach(function (d, j) { d.tabIndex = j === i ? 0 : -1; });
    dots[i].focus();
  }
  dots.forEach(function (d, i) {
    d.addEventListener("mouseenter", function () { showTip(d); });
    d.addEventListener("mouseleave", hideTip);
    d.addEventListener("focus", function () {
      dots.forEach(function (o) { o.tabIndex = o === d ? 0 : -1; });
      showTip(d);
    });
    d.addEventListener("blur", hideTip);
    d.addEventListener("click", function () {
      setTheme(D.sources[+d.getAttribute("data-k")].t, true);
      scrollToEl(SEC.sources);
    });
    d.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); d.dispatchEvent(new Event("click")); }
      else if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); focusDot(i + 1); }
      else if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); focusDot(i - 1); }
      else if (e.key === "Home") { e.preventDefault(); focusDot(0); }
      else if (e.key === "End") { e.preventDefault(); focusDot(dots.length - 1); }
      else if (e.key === "Escape") { hideTip(); }
    });
  });

  /* ------------------------------------------------------------ chat */

  // The example is a timeline of small actions (type a char, show a chip,
  // stream a word...). Pausing just stops the timeline; reduced motion and
  // "paused" both run every action at once, with no delays.

  var tx = $("tx");
  var tsrc = $("tsrc");
  var stepBtns = all("#steps .step");
  var progBars = all("#prog i");
  var toggleBtn = $("termToggle");
  var term = tx.closest(".term");
  var cur = 0; // current example
  var queue = []; // timeline of {step, delay, fn}
  var qi = 0; // next action to run
  var timer = 0;
  var userPaused = false; // the user pressed pause or took control
  var live = {}; // DOM nodes of the conversation being played

  function make(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text) n.textContent = text;
    return n;
  }
  function appendText(parent, text, bold) {
    var last = parent.lastChild;
    if (bold) {
      if (!last || last.nodeName !== "B") {
        last = make("b");
        last.appendChild(document.createTextNode(""));
        parent.appendChild(last);
      }
      last.firstChild.appendData(text);
    } else {
      if (!last || last.nodeType !== 3) {
        last = document.createTextNode("");
        parent.appendChild(last);
      }
      last.appendData(text);
    }
  }
  // Split "plain **bold** plain" into word tokens that keep their bold flag.
  function wordTokens(text) {
    var out = [];
    text.split("**").forEach(function (part, i) {
      (part.match(/\s*\S+\s*|\s+/g) || []).forEach(function (w) { out.push({ t: w, b: i % 2 === 1 }); });
    });
    return out;
  }
  function enter(node) {
    if (!reduce) node.classList.add("enter");
    return node;
  }
  function keepThinkingLast() {
    if (live.think && live.think.parentNode) live.turn.appendChild(live.think);
  }

  function buildQueue(ex) {
    var q = [];
    function add(step, delay, fn) { q.push({ step: step, delay: delay, fn: fn }); }
    var question = ex.steps[0].text;

    add(-1, 0, function () {
      live.userText = make("span", "ut");
      live.caret = make("span", "caret mono", "▍");
      live.caret.setAttribute("aria-hidden", "true");
      var bubble = make("div", "bubble");
      bubble.appendChild(live.userText);
      bubble.appendChild(live.caret);
      var msg = make("div", "msg user");
      msg.appendChild(bubble);
      tx.appendChild(msg);
    });
    for (var k = 1; k <= question.length; k++) {
      (function (k) {
        add(-1, 25 + ((k * 7) % 11), function () { live.userText.textContent = question.slice(0, k); });
      })(k);
    }
    add(-1, 400, function () {
      if (live.caret.parentNode) live.caret.parentNode.removeChild(live.caret);
      var who = make("div", "who");
      who.appendChild(make("span", "av", "E"));
      who.appendChild(make("span", "", "EcuDataMCP"));
      live.turn = make("div", "turn");
      live.think = make("div", "think");
      live.think.appendChild(document.createTextNode(UI.thinking));
      live.think.appendChild(make("span", "dots"));
      live.turn.appendChild(live.think);
      var msg = make("div", "msg bot");
      msg.appendChild(who);
      msg.appendChild(live.turn);
      tx.appendChild(enter(msg));
    });
    add(-1, 750, function () {});

    ex.steps.slice(1).forEach(function (s) {
      if (s.kind === "call") {
        add(s.step, 650, function () {
          var d = enter(make("div", "call"));
          d.appendChild(make("span", "sn", s.n));
          d.appendChild(document.createTextNode(s.tool + "(" + s.args + ")"));
          d.appendChild(document.createElement("br"));
          live.res = make("em", "", "…");
          d.appendChild(live.res);
          live.turn.appendChild(d);
          keepThinkingLast();
        });
        add(s.step, 450, function () { live.res.textContent = "✓ " + s.result; });
      } else if (s.kind === "reason") {
        add(s.step, 900, function () {
          var d = enter(make("div", "call reason"));
          d.appendChild(make("span", "sn", s.n));
          d.appendChild(document.createTextNode(s.text));
          live.turn.appendChild(d);
          keepThinkingLast();
        });
      } else {
        add(s.step, 150, function () {
          if (live.think && live.think.parentNode) live.think.parentNode.removeChild(live.think);
          live.ans = enter(make("div", "ans"));
          live.turn.appendChild(live.ans);
        });
        wordTokens(s.text).forEach(function (tok, i) {
          add(s.step, 30 + ((i * 13) % 21), function () { appendText(live.ans, tok.t, tok.b); });
        });
        add(s.step, 0, function () {
          live.ans.appendChild(document.createTextNode(" "));
          live.ans.appendChild(enter(make("span", "cite", s.cite)));
        });
      }
    });
    return q;
  }

  function setStep(st) {
    stepBtns.forEach(function (b, j) {
      b.classList.toggle("on", j === st);
      if (j === st) b.setAttribute("aria-current", "step");
      else b.removeAttribute("aria-current");
    });
    progBars.forEach(function (b, j) { b.classList.toggle("on", j <= st); });
  }
  function exec(a) {
    a.fn();
    setStep(a.step);
    tx.scrollTop = tx.scrollHeight;
  }
  function reset() {
    tx.textContent = "";
    live = {};
    qi = 0;
    setStep(-1);
    tx.scrollTop = 0;
  }
  function paintSource() {
    var ex = D.transcripts[cur];
    tsrc.textContent = "";
    tsrc.appendChild(document.createTextNode(UI.src_consulted));
    tsrc.appendChild(make("b", "", ex.source.name));
    tsrc.appendChild(document.createTextNode(" · " + ex.source.detail));
  }
  function finish() {
    while (qi < queue.length) exec(queue[qi++]);
    tx.scrollTop = 0;
  }
  // Show the conversation up to (and including) step j, instantly.
  function seek(j) {
    reset();
    while (qi < queue.length && queue[qi].step <= j) exec(queue[qi++]);
    if (qi < queue.length && live.think && live.think.parentNode) live.think.parentNode.removeChild(live.think);
    tx.scrollTop = 0;
  }

  function setLive() {
    // Auto-cycling content must not chatter at screen readers; once the user
    // is driving (paused, or reduced motion) updates are announced politely.
    tx.setAttribute("aria-live", userPaused || reduce ? "polite" : "off");
  }
  function clearTimer() { window.clearTimeout(timer); timer = 0; }
  function running() { return !reduce && !userPaused && !document.hidden; }

  function pump() {
    clearTimer();
    if (!running()) return;
    if (qi >= queue.length) {
      // hold on the finished answer, then move to the next example
      timer = window.setTimeout(function () {
        exTabs.select((cur + 1) % D.transcripts.length, false, false);
      }, 4000);
      return;
    }
    var a = queue[qi++];
    exec(a);
    timer = window.setTimeout(pump, a.delay);
  }

  function playExample(i) {
    clearTimer();
    cur = i;
    queue = buildQueue(D.transcripts[cur]);
    reset();
    paintSource();
    if (reduce || userPaused) finish();
    else pump();
  }

  var exTabs = tablist($("exTabs"), function (i) { playExample(i); });

  stepBtns.forEach(function (b, j) {
    b.addEventListener("click", function () {
      // jump to that step; the user is now in control
      userPaused = true;
      syncToggle();
      clearTimer();
      seek(j);
    });
  });

  function syncToggle() {
    setLive();
    if (!toggleBtn) return;
    toggleBtn.setAttribute("aria-pressed", userPaused ? "true" : "false");
    var label = userPaused ? UI.play : UI.pause;
    toggleBtn.setAttribute("aria-label", label);
    toggleBtn.title = label;
    toggleBtn.innerHTML = userPaused ? "&#9654;" : "&#10074;&#10074;";
  }
  if (toggleBtn) {
    if (reduce) toggleBtn.hidden = true;
    toggleBtn.addEventListener("click", function () {
      userPaused = !userPaused;
      syncToggle();
      if (userPaused) clearTimer();
      else pump();
    });
  }
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) clearTimer();
    else pump();
  });
  setLive();
  playExample(0);

  /* ------------------------------------------------------------- connect */

  var panels = all("#panels .panel");
  tablist($("tabs"), function (i) {
    panels.forEach(function (p, j) { p.classList.toggle("on", j === i); });
  });

  /* ------------------------------------------------------------ carousel */

  (function () {
    var root = document.querySelector("[data-org-carousel]");
    if (!root) return;
    var viewport = root.querySelector(".org-carousel-viewport");
    var prev = root.querySelector("[data-org-prev]");
    var next = root.querySelector("[data-org-next]");
    var btn = document.querySelector("[data-org-toggle]");
    if (!viewport || !prev || !next) return;

    var paused = false;
    var held = false;
    var visible = true;
    var raf = 0;
    var last = 0;
    var speed = 36;

    // duplicate the logos so the loop is seamless; the copies are decorative
    Array.prototype.forEach.call(viewport.children, function (node) {
      var clone = node.cloneNode(true);
      clone.setAttribute("aria-hidden", "true");
      clone.setAttribute("tabindex", "-1");
      viewport.appendChild(clone);
    });

    function wrapScroll() {
      var half = viewport.scrollWidth / 2;
      if (!half) return;
      if (viewport.scrollLeft >= half) viewport.scrollLeft -= half;
      else if (viewport.scrollLeft < 0) viewport.scrollLeft += half;
    }
    function stepSize() {
      var card = viewport.querySelector(".org-logo");
      if (!card) return 180;
      var cs = getComputedStyle(viewport);
      var gap = parseFloat(cs.columnGap || cs.gap) || 0;
      return card.getBoundingClientRect().width + gap;
    }
    function go(dir) {
      if (dir < 0 && viewport.scrollLeft < stepSize()) viewport.scrollLeft += viewport.scrollWidth / 2;
      viewport.scrollBy({ left: dir * stepSize(), behavior: reduce ? "auto" : "smooth" });
      window.setTimeout(wrapScroll, reduce ? 0 : 450);
    }
    function isRunning() { return !reduce && !paused && !held && visible && !document.hidden; }
    function frame(now) {
      raf = 0;
      if (!isRunning()) { last = 0; return; }
      if (!last) last = now;
      var dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      viewport.scrollLeft += speed * dt;
      wrapScroll();
      raf = window.requestAnimationFrame(frame);
    }
    function kick() {
      if (!raf && isRunning()) { last = 0; raf = window.requestAnimationFrame(frame); }
    }

    prev.addEventListener("click", function () { go(-1); });
    next.addEventListener("click", function () { go(1); });
    if (btn) {
      if (reduce) btn.hidden = true;
      btn.addEventListener("click", function () {
        held = !held;
        btn.setAttribute("aria-pressed", held ? "true" : "false");
        var label = btn.getAttribute(held ? "data-label-play" : "data-label-pause");
        if (label) btn.setAttribute("aria-label", label);
        btn.innerHTML = held ? "&#9654;" : "&#10074;&#10074;";
        kick();
      });
    }
    root.addEventListener("pointerenter", function () { paused = true; });
    root.addEventListener("pointerleave", function () { paused = false; kick(); });
    root.addEventListener("focusin", function () { paused = true; });
    root.addEventListener("focusout", function (e) {
      if (!root.contains(e.relatedTarget)) { paused = false; kick(); }
    });
    document.addEventListener("visibilitychange", kick);
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (entries) {
        visible = entries[entries.length - 1].isIntersecting;
        kick();
      }).observe(root);
    }
    kick();
  })();
})();
