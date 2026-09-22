// cut-042R F6 — SPA skeleton (vanilla JS, zero CDN, zero build).
//
// Three views: A (procurement, live via /api/v1/demo/*), B (knowledge
// placeholder for cut-043), C (compliance placeholder for cut-044).
//
// Auth convention: caller supplies X-User-Id via the actor dropdown.
// Body NEVER overrides the actor (cut-042R F1).

(function () {
  "use strict";

  // ----- View switching -----
  function switchView(name) {
    var views = document.querySelectorAll(".view");
    for (var i = 0; i < views.length; i++) {
      var v = views[i];
      if (v.getAttribute("data-view") === name) {
        v.classList.add("active");
        v.removeAttribute("hidden");
      } else {
        v.classList.remove("active");
        v.setAttribute("hidden", "");
      }
    }
    var buttons = document.querySelectorAll("nav button");
    for (var j = 0; j < buttons.length; j++) {
      var b = buttons[j];
      if (b.getAttribute("data-view") === name) {
        b.classList.add("active");
      } else {
        b.classList.remove("active");
      }
    }
  }

  var navButtons = document.querySelectorAll("nav button");
  for (var k = 0; k < navButtons.length; k++) {
    navButtons[k].addEventListener("click", function (e) {
      var target = e.currentTarget.getAttribute("data-view");
      switchView(target);
    });
  }

  // ----- GET /api/v1/demo/domains (proof of life on load) -----
  function loadDomains() {
    var resultEl = document.getElementById("result");
    fetch("/api/v1/demo/domains", { headers: { "Accept": "application/json" } })
      .then(function (r) {
        return r.json().then(function (body) {
          return { status: r.status, body: body };
        });
      })
      .then(function (out) {
        var preview = (out.body && out.body.domains)
          ? out.body.domains.map(function (d) { return d.name + " (" + d.label + ")"; }).join(", ")
          : "(no domains)";
        resultEl.textContent =
          "[GET /api/v1/demo/domains → " + out.status + "]\n" +
          "Domains: " + preview + "\n\n" +
          "调整上方表单后点击 \"运行六步闭环\" 触发 POST /api/v1/demo/scenarios/generate";
      })
      .catch(function (err) {
        resultEl.textContent =
          "[GET /api/v1/demo/domains 失败]\n" + (err && err.message ? err.message : err);
      });
  }

  // ----- POST /api/v1/demo/scenarios/generate -----
  var form = document.getElementById("demo-form");
  if (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var fd = new FormData(form);
      var actor = String(fd.get("actor") || "");
      var amount = Number(fd.get("amount") || 0);
      var quoteCount = Number(fd.get("quote_count") || 0);

      var payload = {
        domain: "procurement",
        scenario: "default",
        params: {
          amount: amount,
          quote_count: quoteCount
        }
      };

      var resultEl = document.getElementById("result");
      resultEl.textContent = "[POST /api/v1/demo/scenarios/generate → 等待响应…]";

      // F1: X-User-Id header sets the actor. Body MUST NOT override.
      fetch("/api/v1/demo/scenarios/generate", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json",
          "X-User-Id": actor
        },
        body: JSON.stringify(payload)
      })
        .then(function (r) {
          return r.json().then(function (body) {
            return { status: r.status, body: body };
          });
        })
        .then(function (out) {
          resultEl.textContent =
            "[POST /api/v1/demo/scenarios/generate → " + out.status + "]\n" +
            JSON.stringify(out.body, null, 2);
        })
        .catch(function (err) {
          resultEl.textContent =
            "[POST /api/v1/demo/scenarios/generate 失败]\n" + (err && err.message ? err.message : err);
        });
    });
  }

  // Initial probe so the SPA exercises the API on first paint.
  loadDomains();
})();
