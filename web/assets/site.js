function copyCode(btn) {
  const code = btn.parentElement.querySelector("code").textContent;

  navigator.clipboard.writeText(code).then(() => {
    const original = btn.textContent;
    btn.textContent = window.COPY_LABEL_COPIED || "Copied!";
    setTimeout(() => {
      btn.textContent = original;
    }, 1500);
  });
}

// ---- theme toggle (light / dark) ----------------------------------------

(function () {
  var btn = document.querySelector("[data-theme-toggle]");
  var nav = document.querySelector(".site-navbar");

  function currentTheme() {
    return document.documentElement.getAttribute("data-theme") === "light"
      ? "light"
      : "dark";
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("ecudata-theme", theme);
    } catch (e) {}
    if (nav) {
      nav.setAttribute("data-bs-theme", theme === "light" ? "light" : "dark");
    }
    if (btn) {
      var label =
        theme === "dark"
          ? btn.getAttribute("data-label-light")
          : btn.getAttribute("data-label-dark");
      if (label) {
        btn.setAttribute("aria-label", label);
        btn.setAttribute("title", label);
      }
    }
  }

  applyTheme(currentTheme());

  if (!btn) return;
  btn.addEventListener("click", function () {
    applyTheme(currentTheme() === "dark" ? "light" : "dark");
  });
})();

// ---- mobile navbar toggle (replaces bootstrap.bundle.min.js's Collapse) --

(function () {
  var toggler = document.querySelector("[data-nav-toggle]");
  if (!toggler) return;
  var target = document.getElementById(toggler.getAttribute("data-nav-toggle"));
  if (!target) return;

  toggler.addEventListener("click", function () {
    var expanded = target.classList.toggle("show");
    toggler.setAttribute("aria-expanded", expanded ? "true" : "false");
  });
})();

// ---- MCP-client tabs (replaces bootstrap.bundle.min.js's Tab) ------------

(function () {
  var tabButtons = Array.from(document.querySelectorAll("[data-tab-target]"));
  if (tabButtons.length === 0) return;

  tabButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var targetId = btn.getAttribute("data-tab-target");
      var tabList = btn.closest(".nav-tabs");
      var tabContent = tabList.parentElement.querySelector(".tab-content");

      tabList.querySelectorAll(".nav-link").forEach(function (l) {
        l.classList.remove("active");
      });
      btn.classList.add("active");

      tabContent.querySelectorAll(".tab-pane").forEach(function (pane) {
        pane.classList.remove("show", "active");
      });
      var targetPane = document.getElementById(targetId);
      if (targetPane) targetPane.classList.add("show", "active");
    });
  });
})();

// ---- site search ----------------------------------------------------------

(function () {
  var toggle = document.querySelector(".site-search-toggle");
  var panel = document.getElementById("siteSearchPanel");
  var input = document.getElementById("siteSearchInput");
  var results = document.getElementById("siteSearchResults");
  if (!toggle || !panel || !input || !results || typeof Fuse === "undefined") return;

  var fuse = null;
  var indexPromise = null;

  function ensureIndex() {
    if (indexPromise) return indexPromise;
    indexPromise = fetch(window.SITE_SEARCH_INDEX_URL)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        fuse = new Fuse(data, {
          keys: [
            { name: "title", weight: 2 },
            { name: "text", weight: 1 },
          ],
          threshold: 0.35,
          ignoreLocation: true,
        });
      });
    return indexPromise;
  }

  function render(query) {
    if (!query) {
      results.innerHTML = "";
      return;
    }
    var hits = fuse.search(query, { limit: 8 });
    if (hits.length === 0) {
      results.innerHTML = '<p class="site-search-empty">' + (window.SITE_SEARCH_EMPTY_LABEL || "No results.") + "</p>";
      return;
    }
    results.innerHTML = hits
      .map(function (h) {
        var item = h.item;
        var excerpt = item.text.slice(0, 140);
        var href = (window.SITE_ROOT || "") + item.href;
        return (
          '<a class="site-search-result" href="' + href + '">' +
          '<div class="site-search-result-title">' + item.title + "</div>" +
          '<div class="site-search-result-excerpt">' + excerpt + "…</div>" +
          "</a>"
        );
      })
      .join("");
  }

  function open() {
    panel.hidden = false;
    ensureIndex().then(function () {
      input.focus();
    });
  }

  function close() {
    panel.hidden = true;
    input.value = "";
    results.innerHTML = "";
  }

  toggle.addEventListener("click", open);
  panel.addEventListener("click", function (e) {
    if (e.target === panel) close();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !panel.hidden) close();
    if ((e.key === "/" || (e.key === "k" && (e.metaKey || e.ctrlKey))) && panel.hidden) {
      var tag = document.activeElement && document.activeElement.tagName;
      if (tag !== "INPUT" && tag !== "TEXTAREA") {
        e.preventDefault();
        open();
      }
    }
  });
  input.addEventListener("input", function (e) {
    if (fuse) render(e.target.value.trim());
  });
})();

// ---- hero chat examples (real MCP answers, prev / next, autoplay) ------

(function () {
  var root = document.querySelector("[data-chat-demo]");
  if (!root) return;

  var body = root.querySelector("[data-chat-body]");
  var statusEl = root.querySelector("[data-chat-status]");
  var labelEl = root.querySelector("[data-chat-label]");
  var dataEl = root.querySelector("[data-chat-examples]");
  var prevBtn = root.querySelector("[data-chat-prev]");
  var nextBtn = root.querySelector("[data-chat-next]");
  if (!body || !dataEl || !prevBtn || !nextBtn) return;

  var examples;
  try {
    examples = JSON.parse(dataEl.textContent);
  } catch (e) {
    return;
  }
  if (!examples.length) return;

  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var DWELL = 8400;
  var index = 0;
  var timer = 0;
  var swapTimer = 0;
  var generation = 0;
  var paused = false;
  var deadline = 0;
  var remaining = DWELL;
  var swapping = false;
  var pending = 0;

  var progress = document.createElement("div");
  progress.className = "chat-progress";
  progress.setAttribute("aria-hidden", "true");
  var progressBar = document.createElement("span");
  progress.appendChild(progressBar);
  if (!reduce) body.insertAdjacentElement("afterend", progress);

  function renderTurn(step, i) {
    var bubble = document.createElement("div");
    bubble.className = "chat-bubble " + (step.role === "user" ? "user" : "assistant");
    if (!reduce) {
      bubble.classList.add("chat-enter");
      bubble.style.animationDelay = (i * 80) + "ms";
    }
    if (step.role === "user") {
      bubble.textContent = step.text || "";
      return bubble;
    }
    if (step.tool) {
      var tool = document.createElement("span");
      tool.className = "chat-tool";
      tool.textContent = "tool · " + step.tool;
      bubble.appendChild(tool);
    }
    if (step.html || step.text) {
      var p = document.createElement("p");
      if (step.html) p.innerHTML = step.html;
      else p.textContent = step.text;
      bubble.appendChild(p);
    }
    if (step.code) {
      var pre = document.createElement("pre");
      pre.className = "chat-code";
      pre.textContent = step.code;
      bubble.appendChild(pre);
    }
    if (step.cite) {
      var cite = document.createElement("span");
      cite.className = "chat-cite";
      cite.textContent = step.cite;
      bubble.appendChild(cite);
    }
    return bubble;
  }

  function restartBar() {
    progressBar.style.animation = "none";
    void progressBar.offsetWidth;
    progressBar.style.animation = "";
  }

  function schedule(ms) {
    generation += 1;
    var gen = generation;
    window.clearTimeout(timer);
    remaining = ms;
    deadline = Date.now() + ms;
    timer = window.setTimeout(function () {
      if (gen !== generation) return;
      go(1);
    }, ms);
  }

  function beginCycle() {
    generation += 1;
    window.clearTimeout(timer);
    remaining = DWELL;
    if (reduce) return;
    restartBar();
    root.classList.add("is-playing");
    if (paused || document.hidden) {
      root.classList.add("is-paused");
      return;
    }
    root.classList.remove("is-paused");
    schedule(DWELL);
  }

  function pause() {
    if (paused || reduce) return;
    paused = true;
    generation += 1;
    root.classList.add("is-paused");
    window.clearTimeout(timer);
    if (deadline) remaining = Math.max(400, deadline - Date.now());
  }

  function resume() {
    if (!paused) return;
    paused = false;
    if (reduce || document.hidden) return;
    root.classList.remove("is-paused");
    if (swapping) return;
    schedule(remaining);
  }

  function paint(example) {
    var nodes = example.turns.map(renderTurn);
    body.replaceChildren.apply(body, nodes);
    if (labelEl) labelEl.textContent = example.label + " · " + (index + 1) + " / " + examples.length;
    if (statusEl) statusEl.textContent = example.label;
  }

  function go(delta) {
    var base = swapping ? pending : index;
    pending = (base + delta + examples.length) % examples.length;
    generation += 1;
    window.clearTimeout(timer);
    function commit() {
      index = pending;
      swapping = false;
      body.classList.remove("is-leaving");
      paint(examples[index]);
      beginCycle();
    }
    if (reduce) {
      commit();
      return;
    }
    swapping = true;
    window.clearTimeout(swapTimer);
    body.classList.add("is-leaving");
    swapTimer = window.setTimeout(commit, 200);
  }

  if (!reduce) {
    Array.prototype.forEach.call(body.children, function (node, i) {
      node.classList.add("chat-enter");
      node.style.animationDelay = (i * 80) + "ms";
    });
  }
  if (statusEl && examples[0].label) statusEl.textContent = examples[0].label;
  beginCycle();

  prevBtn.addEventListener("click", function () { go(-1); });
  nextBtn.addEventListener("click", function () { go(1); });
  root.addEventListener("pointerenter", pause);
  root.addEventListener("pointerleave", resume);
  root.addEventListener("focusin", pause);
  root.addEventListener("focusout", function (event) {
    if (!root.contains(event.relatedTarget)) resume();
  });
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) {
      generation += 1;
      window.clearTimeout(timer);
      if (deadline) remaining = Math.max(400, deadline - Date.now());
      root.classList.add("is-paused");
    } else if (!paused && !swapping) {
      root.classList.remove("is-paused");
      schedule(remaining);
    }
  });
})();

// ---- landing atmosphere + scroll reveal --------------------------------

(function () {
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var hero = document.querySelector(".landing.hero");
  if (hero && !reduce && !hero.querySelector(".hero-orbs")) {
    var wrap = document.createElement("div");
    wrap.className = "hero-orbs";
    wrap.setAttribute("aria-hidden", "true");
    ["y", "b", "r"].forEach(function (name) {
      var orb = document.createElement("span");
      orb.className = "hero-orb hero-orb-" + name;
      wrap.appendChild(orb);
    });
    hero.prepend(wrap);
  }

  if (reduce || !("IntersectionObserver" in window)) return;

  var nodes = document.querySelectorAll(".landing:not(.hero), .closing-cta");
  if (!nodes.length) return;
  var statsStarted = false;

  function countUp(el) {
    var finalText = el.textContent.trim();
    var target = Number(finalText.replace(/[^\d.]/g, ""));
    if (!isFinite(target)) return;
    var start = performance.now();
    var dur = 900;
    function frame(now) {
      var t = Math.min(1, (now - start) / dur);
      var eased = 1 - Math.pow(1 - t, 3);
      var value = Math.round(target * eased);
      el.textContent = finalText.indexOf(",") >= 0 ? value.toLocaleString("en-US") : String(value);
      if (t < 1) requestAnimationFrame(frame);
      else el.textContent = finalText;
    }
    requestAnimationFrame(frame);
  }

  function revealStats() {
    if (statsStarted) return;
    statsStarted = true;
    document.querySelectorAll(".hero-stat .num").forEach(countUp);
  }

  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (!entry.isIntersecting) return;
      entry.target.classList.add("is-in");
      if (entry.target.classList.contains("strip-section")) revealStats();
      io.unobserve(entry.target);
    });
  }, { threshold: 0, rootMargin: "0px 0px 12% 0px" });

  nodes.forEach(function (el) {
    var top = el.getBoundingClientRect().top;
    if (top < window.innerHeight * 0.92) {
      el.classList.add("is-in");
      if (el.classList.contains("strip-section")) revealStats();
      return;
    }
    el.classList.add("reveal");
    io.observe(el);
  });
})();

// ---- institution logo carousel ------------------------------------------

(function () {
  var root = document.querySelector("[data-org-carousel]");
  if (!root) return;
  var viewport = root.querySelector(".org-carousel-viewport");
  var prev = root.querySelector("[data-org-prev]");
  var next = root.querySelector("[data-org-next]");
  if (!viewport || !prev || !next) return;

  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var timer = 0;
  var paused = false;

  function stepSize() {
    var card = viewport.querySelector(".org-logo");
    if (!card) return 180;
    var styles = getComputedStyle(viewport);
    var gap = parseFloat(styles.columnGap || styles.gap) || 0;
    return card.getBoundingClientRect().width + gap;
  }

  function go(dir) {
    var max = viewport.scrollWidth - viewport.clientWidth;
    var behavior = reduce ? "auto" : "smooth";
    if (dir > 0 && viewport.scrollLeft >= max - 4) {
      viewport.scrollTo({ left: 0, behavior: behavior });
      return;
    }
    if (dir < 0 && viewport.scrollLeft <= 4) {
      viewport.scrollTo({ left: max, behavior: behavior });
      return;
    }
    viewport.scrollBy({ left: dir * stepSize(), behavior: behavior });
  }

  function arm() {
    window.clearInterval(timer);
    if (reduce || paused || document.hidden) return;
    timer = window.setInterval(function () { go(1); }, 3200);
  }

  prev.addEventListener("click", function () { go(-1); });
  next.addEventListener("click", function () { go(1); });
  root.addEventListener("pointerenter", function () {
    paused = true;
    window.clearInterval(timer);
  });
  root.addEventListener("pointerleave", function () {
    paused = false;
    arm();
  });
  root.addEventListener("focusin", function () {
    paused = true;
    window.clearInterval(timer);
  });
  root.addEventListener("focusout", function (event) {
    if (!root.contains(event.relatedTarget)) {
      paused = false;
      arm();
    }
  });
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) window.clearInterval(timer);
    else arm();
  });
  arm();
})();
