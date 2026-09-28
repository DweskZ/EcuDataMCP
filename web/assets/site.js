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

// ---- hero chat demo (AI typing / tool streaming) ------------------------

(function () {
  var root = document.querySelector("[data-chat-demo]");
  if (!root) return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  var body = root.querySelector("[data-chat-body]");
  var statusEl = root.querySelector("[data-chat-status]");
  if (!body) return;

  var lang = root.getAttribute("data-chat-demo") || "es";
  var labels =
    lang === "en"
      ? {
          typing: "typing…",
          tool: "running tool…",
          done: "done",
        }
      : {
          typing: "escribiendo…",
          tool: "usando tool…",
          done: "listo",
        };

  var script =
    lang === "en"
      ? [
          {
            role: "user",
            text: "What does the BCE say about remittances in 2025?",
          },
          {
            role: "assistant",
            tool: "search_ecuador",
            html: "I found <strong>BCE</strong> publications on remittances. Want me to open the series and show recent values?",
            cite: "source · contenido.bce.fin.ec",
          },
          { role: "user", text: "Yes — show me a preview." },
          {
            role: "assistant",
            tool: "preview_resource_data",
            code: "month, remittances_usd_m\n2025-01, 412.3\n2025-02, 398.7\n2025-03, 421.1",
          },
        ]
      : [
          {
            role: "user",
            text: "¿Qué dice el BCE sobre remesas en 2025?",
          },
          {
            role: "assistant",
            tool: "search_ecuador",
            html: "Encontré publicaciones del <strong>BCE</strong> sobre remesas. ¿Quieres que abra la serie y te muestre los valores recientes?",
            cite: "fuente · contenido.bce.fin.ec",
          },
          { role: "user", text: "Sí, muéstrame el preview." },
          {
            role: "assistant",
            tool: "preview_resource_data",
            code: "mes, remesas_usd_m\n2025-01, 412.3\n2025-02, 398.7\n2025-03, 421.1",
          },
        ];

  function sleep(ms) {
    return new Promise(function (resolve) {
      setTimeout(resolve, ms);
    });
  }

  function setStatus(text) {
    if (!statusEl) return;
    statusEl.textContent = text || "";
    statusEl.hidden = !text;
  }

  function typeText(el, text, cps) {
    cps = cps || 38;
    return new Promise(function (resolve) {
      var i = 0;
      el.classList.add("is-typing");
      function tick() {
        i += 1;
        el.textContent = text.slice(0, i);
        if (i < text.length) {
          setTimeout(tick, 1000 / cps);
        } else {
          el.classList.remove("is-typing");
          resolve();
        }
      }
      tick();
    });
  }

  function typeHtml(el, html, cps) {
    // Stream plain text, then swap in final HTML for bold bits.
    var tmp = document.createElement("div");
    tmp.innerHTML = html;
    var plain = tmp.textContent || "";
    return typeText(el, plain, cps || 42).then(function () {
      el.innerHTML = html;
    });
  }

  function makeTypingIndicator() {
    var bubble = document.createElement("div");
    bubble.className = "chat-bubble assistant chat-typing";
    bubble.innerHTML =
      '<span class="chat-typing-dots" aria-hidden="true"><i></i><i></i><i></i></span>';
    return bubble;
  }

  async function playUser(step) {
    setStatus(labels.typing);
    var bubble = document.createElement("div");
    bubble.className = "chat-bubble user chat-enter";
    var span = document.createElement("span");
    span.className = "chat-stream-text";
    bubble.appendChild(span);
    body.appendChild(bubble);
    await typeText(span, step.text, 34);
    setStatus("");
    await sleep(280);
  }

  async function playAssistant(step) {
    var typing = makeTypingIndicator();
    body.appendChild(typing);
    setStatus(step.tool ? labels.tool : labels.typing);
    await sleep(step.tool ? 700 : 450);
    typing.remove();

    var bubble = document.createElement("div");
    bubble.className = "chat-bubble assistant chat-enter";
    body.appendChild(bubble);

    if (step.tool) {
      var tool = document.createElement("span");
      tool.className = "chat-tool chat-tool-pop";
      tool.textContent = "tool · " + step.tool;
      bubble.appendChild(tool);
      await sleep(220);
    }

    if (step.html) {
      var p = document.createElement("p");
      p.className = "chat-stream-text";
      bubble.appendChild(p);
      await typeHtml(p, step.html, 44);
    }

    if (step.code) {
      var pre = document.createElement("pre");
      pre.className = "chat-code chat-stream-text";
      bubble.appendChild(pre);
      var lines = step.code.split("\n");
      var built = "";
      for (var i = 0; i < lines.length; i += 1) {
        built += (i ? "\n" : "") + lines[i];
        pre.textContent = built;
        pre.classList.add("is-typing");
        await sleep(160);
      }
      pre.classList.remove("is-typing");
    }

    if (step.cite) {
      var cite = document.createElement("span");
      cite.className = "chat-cite chat-tool-pop";
      cite.textContent = step.cite;
      bubble.appendChild(cite);
    }

    setStatus(labels.done);
    await sleep(500);
    setStatus("");
  }

  async function runLoop() {
    root.classList.add("is-animated");
    while (true) {
      body.innerHTML = "";
      setStatus("");
      await sleep(400);
      for (var i = 0; i < script.length; i += 1) {
        var step = script[i];
        if (step.role === "user") {
          await playUser(step);
        } else {
          await playAssistant(step);
        }
      }
      await sleep(2600);
    }
  }

  if ("IntersectionObserver" in window) {
    var started = false;
    var io = new IntersectionObserver(
      function (entries) {
        if (started) return;
        if (entries.some(function (e) { return e.isIntersecting; })) {
          started = true;
          io.disconnect();
          runLoop();
        }
      },
      { threshold: 0.35 }
    );
    io.observe(root);
  } else {
    runLoop();
  }
})();
