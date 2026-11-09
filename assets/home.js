/* Home page behavior: atlas map, honest client-side search, terminal
   transcripts, theme explorer, stored answers, client tabs and the logo
   carousel. Vanilla JS. Everything it needs (sources, themes, answers,
   transcripts, search lexicon, UI strings) comes from the #home-data JSON
   island that build.py derives from web/data/*.json. */
(function () {
  "use strict";

  var dataEl = document.getElementById("home-data");
  if (!dataEl) return;
  var D = JSON.parse(dataEl.textContent);
  var UI = D.ui;
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function $(id) { return document.getElementById(id); }
  function all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function norm(t) {
    return String(t).toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  }
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
  var matchSet = null; // Set of source indexes highlighted by a search

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
      if (matchSet) show = matchSet.has(k);
      else if (activeTheme !== null) show = t === activeTheme;
      d.classList.toggle("dim", !show);
      d.classList.toggle("match", !!matchSet && matchSet.has(k));
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
    matchSet = null;
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

  /* ----------------------------------------------------------- terminal */

  var tx = $("tx");
  var tsrc = $("tsrc");
  var stepBtns = all("#steps .step");
  var progBars = all("#prog i");
  var toggleBtn = $("termToggle");
  var term = tx.closest(".term");
  var cur = 0; // current example
  var shown = 0; // steps visible in the current example
  var rendered = { ex: -1, n: 0 };
  var timer = 0;
  var userPaused = false; // the user pressed pause or took control
  var hovering = false;
  var caret = document.createElement("span");
  caret.className = "caret mono";
  caret.setAttribute("aria-hidden", "true");
  caret.textContent = "▍";

  function stepNode(s) {
    var d = document.createElement("div");
    if (s.kind === "question") {
      d.className = "q";
      d.textContent = s.text;
    } else if (s.kind === "call") {
      d.className = "call";
      var n = document.createElement("span");
      n.className = "sn";
      n.textContent = s.n;
      d.appendChild(n);
      d.appendChild(document.createTextNode("→ " + s.tool + "(" + s.args + ")"));
      d.appendChild(document.createElement("br"));
      var em = document.createElement("em");
      em.textContent = "✓ " + s.result;
      d.appendChild(em);
    } else if (s.kind === "reason") {
      d.className = "call reason";
      var rn = document.createElement("span");
      rn.className = "sn";
      rn.textContent = s.n;
      d.appendChild(rn);
      d.appendChild(document.createTextNode(s.text));
    } else {
      d.className = "ans";
      var an = document.createElement("span");
      an.className = "sn y";
      an.textContent = s.n;
      d.appendChild(an);
      richText(d, s.text);
      d.appendChild(document.createTextNode(" "));
      var cite = document.createElement("span");
      cite.className = "cite";
      cite.textContent = s.cite;
      d.appendChild(cite);
    }
    if (!reduce) d.classList.add("enter");
    return d;
  }

  function paintTerminal() {
    var ex = D.transcripts[cur];
    var n = Math.max(0, Math.min(shown, ex.steps.length));
    if (rendered.ex !== cur || n < rendered.n) {
      tx.textContent = "";
      rendered = { ex: cur, n: 0 };
    }
    if (caret.parentNode) caret.parentNode.removeChild(caret);
    for (var i = rendered.n; i < n; i++) tx.appendChild(stepNode(ex.steps[i]));
    rendered.n = n;
    if (n < ex.steps.length) tx.appendChild(caret);
    tx.scrollTop = tx.scrollHeight;
    var st = n ? ex.steps[n - 1].step : -1;
    stepBtns.forEach(function (b, j) {
      b.classList.toggle("on", j === st);
      if (j === st) b.setAttribute("aria-current", "step");
      else b.removeAttribute("aria-current");
    });
    progBars.forEach(function (b, j) { b.classList.toggle("on", j <= st); });
    tsrc.textContent = "";
    tsrc.appendChild(document.createTextNode(UI.src_consulted));
    var strong = document.createElement("b");
    strong.textContent = ex.source.name;
    tsrc.appendChild(strong);
    tsrc.appendChild(document.createTextNode(" · " + ex.source.detail));
  }

  function setLive() {
    // Auto-cycling content must not chatter at screen readers; once the user
    // is driving (paused, or reduced motion) updates are announced politely.
    tx.setAttribute("aria-live", userPaused || reduce ? "polite" : "off");
  }

  function clearTimer() { window.clearTimeout(timer); timer = 0; }
  function running() { return !reduce && !userPaused && !hovering && !document.hidden; }

  function tick() {
    clearTimer();
    paintTerminal();
    if (!running()) return;
    var len = D.transcripts[cur].steps.length;
    if (shown >= len) {
      // dwell on the finished answer, then move to the next example
      timer = window.setTimeout(function () {
        exTabs.select((cur + 1) % D.transcripts.length, false, false);
      }, 4800);
      return;
    }
    shown += 1;
    timer = window.setTimeout(tick, 1500);
  }

  function playExample(i) {
    clearTimer();
    cur = i;
    rendered = { ex: -1, n: 0 };
    if (reduce || userPaused) {
      shown = D.transcripts[cur].steps.length;
      paintTerminal();
    } else {
      shown = 1;
      tick();
    }
  }

  var exTabs = tablist($("exTabs"), function (i, user) {
    if (user && !reduce && !userPaused) {
      // picking an example by hand hands control to the user
      userPaused = true;
      syncToggle();
    }
    playExample(i);
  });

  stepBtns.forEach(function (b, j) {
    b.addEventListener("click", function () {
      // jump to that step; the user is now in control
      var steps = D.transcripts[cur].steps;
      var n = 0;
      steps.forEach(function (s, idx) { if (s.step <= j) n = idx + 1; });
      userPaused = true;
      syncToggle();
      clearTimer();
      shown = Math.max(1, n);
      paintTerminal();
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
      else tick();
    });
  }
  term.addEventListener("pointerenter", function () { hovering = true; clearTimer(); });
  term.addEventListener("pointerleave", function () { hovering = false; if (running()) tick(); });
  term.addEventListener("focusin", function () { hovering = true; clearTimer(); });
  term.addEventListener("focusout", function (e) {
    if (!term.contains(e.relatedTarget)) { hovering = false; if (running()) tick(); }
  });
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) clearTimer();
    else if (running()) tick();
  });
  setLive();
  playExample(0);

  /* ------------------------------------------------------------- answers */

  function openAnswer(id) {
    var d = $("qa-" + id);
    if (!d) return null;
    d.open = true;
    return d;
  }

  /* -------------------------------------------------------------- search */

  var lex = D.lexicon;
  var STOP = new Set(lex.stop.map(norm));
  var SYN = {};
  Object.keys(lex.synonyms).forEach(function (k) { SYN[norm(k)] = lex.synonyms[k].map(norm); });
  var hay = D.sources.map(function (s) { return norm([s.n, s.i, s.d, themeName(s.t)].join(" ")); });
  var ahay = D.answers.map(function (a) { return norm([a.q, a.a, a.tools.join(" "), a.src].join(" ")); });
  var results = $("results");
  var input = $("q");

  function searchTerms(raw) {
    var words = norm(raw).split(/[^a-z0-9.]+/).filter(function (w) { return w.length > 2 && !STOP.has(w); });
    var weights = {};
    function add(t, w) { if (!weights[t] || weights[t] < w) weights[t] = w; }
    words.forEach(function (w) {
      add(w, 2);
      if (w.length > 4 && w.charAt(w.length - 1) === "s") add(w.slice(0, -1), 2);
      (SYN[w] || []).forEach(function (s) { add(s, 1); });
    });
    return weights;
  }
  function score(text, weights) {
    return Object.keys(weights).reduce(function (a, t) { return a + (text.indexOf(t) >= 0 ? weights[t] : 0); }, 0);
  }
  function fill(template, vars) {
    return template.replace(/\{(\w+)\}/g, function (m, k) { return vars[k] !== undefined ? vars[k] : m; });
  }
  function link(text, href, id) {
    var a = document.createElement("a");
    a.href = href;
    a.textContent = text;
    if (id) a.id = id;
    return a;
  }

  function runSearch(raw) {
    results.textContent = "";
    var weights = searchTerms(raw);
    if (!Object.keys(weights).length) {
      matchSet = null;
      activeTheme = null;
      chips.forEach(function (c) { c.setAttribute("aria-pressed", "false"); });
      paintDots();
      return;
    }
    var scored = [];
    hay.forEach(function (h, k) {
      var sc = score(h, weights);
      if (sc > 0) scored.push({ k: k, score: sc });
    });
    scored.sort(function (a, b) { return b.score - a.score || a.k - b.k; });
    activeTheme = null;
    chips.forEach(function (c) { c.setAttribute("aria-pressed", "false"); });
    matchSet = new Set(scored.map(function (x) { return x.k; }));
    paintDots();

    // stored answer: best-scoring question, only when a real word matched
    var best = null;
    ahay.forEach(function (h, i) {
      var sc = score(h, weights);
      if (sc >= 2 && (!best || sc > best.score)) best = { i: i, score: sc };
    });
    var qn = norm(raw).trim();
    D.answers.forEach(function (a, i) { if (norm(a.q) === qn) best = { i: i, score: 99 }; });
    var exId = null;
    var nq = norm(raw);
    lex.examples.some(function (pair) {
      if (nq.indexOf(norm(pair[0])) >= 0) { exId = pair[1]; return true; }
      return false;
    });

    if (!scored.length) {
      var parts = UI.none.split("{q}");
      results.appendChild(document.createTextNode(parts[0]));
      var qEl = document.createElement("b");
      qEl.textContent = raw;
      results.appendChild(qEl);
      results.appendChild(document.createTextNode(parts[1] || ""));
      results.appendChild(document.createTextNode(" "));
      results.appendChild(link(UI.explore_themes, "#" + SEC.sources.id));
    } else {
      var head = document.createElement("span");
      head.innerHTML = fill(scored.length === 1 ? UI.found_one : UI.found_many, { n: scored.length });
      results.appendChild(head);
      results.appendChild(document.createElement("br"));
      scored.slice(0, 6).forEach(function (x) {
        var s = D.sources[x.k];
        var b = document.createElement("button");
        b.type = "button";
        b.className = "hit";
        var dot = document.createElement("i");
        dot.style.background = D.themes[s.t].color;
        b.appendChild(dot);
        b.appendChild(document.createTextNode(s.n + " · " + s.i.replace(/\s*\(.*\)/, "")));
        b.addEventListener("click", function () {
          setTheme(s.t, true);
          scrollToEl(SEC.sources);
        });
        results.appendChild(b);
      });
      if (scored.length > 6) {
        var rest = document.createElement("span");
        rest.className = "more";
        rest.textContent = "+" + (scored.length - 6);
        results.appendChild(rest);
      }
    }
    var links = document.createElement("div");
    links.className = "res-links";
    results.appendChild(links);
    if (exId) {
      var idx = D.transcripts.findIndex(function (t) { return t.id === exId; });
      if (idx >= 0) {
        var ea = link(UI.see_example, "#" + SEC.how.id);
        ea.addEventListener("click", function () { exTabs.select(idx, false, true); });
        links.appendChild(ea);
      }
    }
    if (best) {
      var a = D.answers[best.i];
      var aa = link(UI.see_answer, "#qa-" + a.id);
      aa.addEventListener("click", function (e) {
        e.preventDefault();
        var d = openAnswer(a.id);
        if (d) scrollToEl(d, "center");
      });
      links.appendChild(aa);
    }
  }

  $("sform").addEventListener("submit", function (e) {
    e.preventDefault();
    runSearch(input.value);
  });
  input.addEventListener("input", function () { if (!input.value) runSearch(""); });

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
