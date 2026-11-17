function copyCode(btn) {
  const code = btn.parentElement.querySelector("code").textContent;

  function done() {
    const original = btn.textContent;
    btn.textContent = window.COPY_LABEL_COPIED || "Copied!";
    setTimeout(() => {
      btn.textContent = original;
    }, 1500);
  }

  function fallback() {
    const ta = document.createElement("textarea");
    ta.value = code;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch (e) {}
    document.body.removeChild(ta);
    if (ok) done();
  }

  if (!navigator.clipboard || !navigator.clipboard.writeText) {
    fallback();
    return;
  }
  navigator.clipboard.writeText(code).then(done, fallback);
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
      .then(function (r) {
        if (!r.ok) throw new Error("search index " + r.status);
        return r.json();
      })
      .then(function (data) {
        fuse = new Fuse(data, {
          keys: [
            { name: "title", weight: 2 },
            { name: "text", weight: 1 },
          ],
          threshold: 0.35,
          ignoreLocation: true,
        });
      })
      .catch(function (err) {
        indexPromise = null;
        throw err;
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
    toggle.setAttribute("aria-expanded", "true");
    ensureIndex().then(
      function () { input.focus(); },
      function () {
        input.focus();
        results.innerHTML = '<p class="site-search-empty">' + (window.SITE_SEARCH_EMPTY_LABEL || "No results.") + "</p>";
      }
    );
  }

  function close() {
    panel.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
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
