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

// ---- hero chat examples (real MCP answers, prev / next) ----------------

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

  var index = 0;

  function renderTurn(step) {
    var bubble = document.createElement("div");
    bubble.className = "chat-bubble " + (step.role === "user" ? "user" : "assistant");
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

  function show(nextIndex) {
    index = (nextIndex + examples.length) % examples.length;
    var example = examples[index];
    body.replaceChildren.apply(body, example.turns.map(renderTurn));
    if (labelEl) labelEl.textContent = example.label + " · " + (index + 1) + " / " + examples.length;
    if (statusEl) statusEl.textContent = example.label;
  }

  prevBtn.addEventListener("click", function () { show(index - 1); });
  nextBtn.addEventListener("click", function () { show(index + 1); });
  show(0);
})();
