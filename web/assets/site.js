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

// ---- site search (replaces quarto-search/autocomplete.umd.js) -----------

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
