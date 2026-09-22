// cut-042R F6 + cut-043 — SPA skeleton (vanilla JS, zero CDN, zero build).
//
// 三个视图: A (多域 live via /api/v1/demo/*), B (KM 架构说明), C (compliance placeholder).
// cut-043: 视图 A 内增加域下拉, 根据当前域切换表单字段 (procurement / knowledge).
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

  // ----- Domain-specific params form -----
  // cut-043: 表单字段由当前域驱动; 业务语言 placeholder 严禁出现技术词.
  function renderParamsForm(domain) {
    var paramsEl = document.getElementById("params-container");
    if (!paramsEl) return;
    if (domain === "knowledge") {
      // cut-043R R5-B1/R5-B4: 员工身份来自上方"调用方"下拉 (X-User-Id).
      // `today` 是服务器锚定的有效期基准, 严禁前端输入 (避免 2024-06-01
      // 之类的回溯攻击绕过有效期). 规则层从 ctx.user 读 employee 身份,
      // 不需要 employee_id 参数.
      paramsEl.innerHTML =
        '<label><span>制度编号</span>' +
        '<input name="policy_id" type="text" value="KM-POL-001" ' +
        'placeholder="如 KM-POL-001"></label>' +
        '<p class="param-hint">员工身份由上方「调用方」下拉指定, 参照日期由服务器锚定.</p>';
    } else {
      // procurement default (also fallback)
      paramsEl.innerHTML =
        '<label><span>金额（元）</span>' +
        '<input name="amount" type="number" value="1500000" min="0" step="1000"></label>' +
        '<label><span>报价家数</span>' +
        '<input name="quote_count" type="number" value="2" min="0" step="1"></label>';
    }
  }

  function payloadForDomain(domain, fd) {
    if (domain === "knowledge") {
      // cut-043R R5-B1/R5-B4: 不再发送 employee_id / today.
      // 员工身份 → X-User-Id header (F1); today → ECE_SERVER_TODAY_ANCHOR.
      return {
        domain: "knowledge",
        scenario: "default",
        params: {
          policy_id: String(fd.get("policy_id") || ""),
        },
      };
    }
    // procurement default
    return {
      domain: "procurement",
      scenario: "default",
      params: {
        amount: Number(fd.get("amount") || 0),
        quote_count: Number(fd.get("quote_count") || 0),
      },
    };
  }

  // ----- GET /api/v1/demo/domains (proof of life on load + populate domain select) -----
  function loadDomains() {
    var resultEl = document.getElementById("result");
    var domainSel = document.getElementById("domain-select");

    fetch("/api/v1/demo/domains", { headers: { "Accept": "application/json" } })
      .then(function (r) {
        return r.json().then(function (body) {
          return { status: r.status, body: body };
        });
      })
      .then(function (out) {
        var domains = (out.body && out.body.domains) ? out.body.domains : [];

        // cut-043: populate domain select with auto-discovered packs.
        if (domainSel && domains.length > 0) {
          domainSel.innerHTML = domains
            .map(function (d) {
              return '<option value="' + d.name + '">' + d.label + "</option>";
            })
            .join("");
          // Trigger initial form render for the first domain.
          renderParamsForm(domainSel.value);
        }

        var preview = domains.length
          ? domains.map(function (d) { return d.name + " (" + d.label + ")"; }).join(", ")
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

  // cut-043: domain change → re-render params form.
  var domainSel = document.getElementById("domain-select");
  if (domainSel) {
    domainSel.addEventListener("change", function () {
      renderParamsForm(domainSel.value);
    });
  }

  // ----- POST /api/v1/demo/scenarios/generate -----
  var form = document.getElementById("demo-form");
  if (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var fd = new FormData(form);
      var actor = String(fd.get("actor") || "");
      var domainSelEl = document.getElementById("domain-select");
      var domain = domainSelEl ? domainSelEl.value : "procurement";
      var payload = payloadForDomain(domain, fd);

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
