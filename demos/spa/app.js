// cut-042R F6 + cut-043 + cut-044 — SPA skeleton (vanilla JS, zero CDN, zero build).
//
// 三个视图: A (多域 live via /api/v1/demo/*), B (kernel 架构说明 — 第三域 closure 后升级),
//          C (蓝图 live — 域包演进时间线 + 状态徽章).
// cut-043: 视图 A 内增加域下拉, 根据当前域切换表单字段 (procurement / knowledge).
// cut-044: 视图 A 增加 compliance 分支 (audit-period 字段); view C 升级 live.
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
      // KC-001: lazily load consulting library on first view-d entry
      if (target === "d") {
        loadConsultingLibrary();
      }
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
    } else if (domain === "compliance") {
      // cut-044: compliance 的 today 是 caller-supplied "审计期间" 基准
      // (与 KM 的 server-anchored today 语义不同 — R5-B1 镜像).
      // 控制项身份来自 params.control_id (route_root_via_params); 员工
      // 身份来自上方"调用方"下拉 (X-User-Id).
      paramsEl.innerHTML =
        '<label><span>控制项编号</span>' +
        '<input name="control_id" type="text" value="COMP-CTL-001" ' +
        'placeholder="如 COMP-CTL-001"></label>' +
        '<label><span>审计期间起</span>' +
        '<input name="period_start" type="date" value="2026-07-01"></label>' +
        '<label><span>审计期间止</span>' +
        '<input name="period_end" type="date" value="2026-09-30"></label>' +
        '<label><span>裁定基准日</span>' +
        '<input name="today" type="date" value="2026-09-22"></label>' +
        '<p class="param-hint">员工身份由上方「调用方」下拉指定, 审计期间由业务方提供 (PRD §6 row 3).</p>';
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
    if (domain === "compliance") {
      // cut-044: today 是 caller-supplied 审计基准 (与 KM 的 server-anchored
      // 语义不同). control_id 由 params 决定 (route_root_via_params).
      return {
        domain: "compliance",
        scenario: "default",
        params: {
          control_id: String(fd.get("control_id") || ""),
          period_start: String(fd.get("period_start") || ""),
          period_end: String(fd.get("period_end") || ""),
          today: String(fd.get("today") || ""),
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

  // -----------------------------------------------------------------------
  // KC-001 — Consulting Knowledge Library (view-d) client.
  // Vanilla JS, zero CDN, zero build. All copy is business-facing (no
  // internal field names leak — guarded by test_consulting_spa_view).
  // -----------------------------------------------------------------------

  var CONSULTING_TYPE_LABEL = {
    "case": "案例",
    "methodology": "方法论",
    "proposal_play": "提案打法",
    "deliverable_template": "交付模板",
    "risk_check": "风险检查",
    "industry_note": "行业观察"
  };

  var CONSULTING_SOURCE_LABEL = {
    "founder_case": "真实案例 (脱敏)",
    "methodology_note": "方法论整理",
    "synthetic_variant": "合成示例",
    "licensed_public": "公开资料"
  };

  var consultingFacetsLoaded = false;

  function populateConsultingSelect(selectEl, values, allLabel) {
    while (selectEl.options.length > 1) {
      selectEl.remove(1);
    }
    if (!values || values.length === 0) return;
    for (var i = 0; i < values.length; i++) {
      var opt = document.createElement("option");
      opt.value = values[i];
      opt.textContent = values[i];
      selectEl.appendChild(opt);
    }
    if (allLabel) {
      selectEl.options[0].textContent = allLabel;
    }
  }

  function loadConsultingFacets() {
    if (consultingFacetsLoaded) return Promise.resolve();
    return fetch("/api/v1/consulting/facets", { headers: { "Accept": "application/json" } })
      .then(function (r) { return r.json(); })
      .then(function (body) {
        var f = (body && body.facets) ? body.facets : {};
        populateConsultingSelect(document.getElementById("filter-type"), f.types || [], "全部类型");
        populateConsultingSelect(document.getElementById("filter-practice"), f.practices || [], "全部实践");
        populateConsultingSelect(document.getElementById("filter-phase"), f.engagement_phases || [], "全部阶段");
        populateConsultingSelect(document.getElementById("filter-industry"), f.client_industries || [], "全部行业");
        populateConsultingSelect(document.getElementById("filter-problem"), f.problem_types || [], "全部问题");
        populateConsultingSelect(document.getElementById("filter-source"), f.source_origins || [], "全部来源");
        consultingFacetsLoaded = true;
      });
  }

  function readConsultingFilters() {
    function v(id) {
      var el = document.getElementById(id);
      return el && el.value ? el.value : "";
    }
    var q = document.getElementById("consulting-search").value.trim();
    var params = new URLSearchParams();
    if (q) params.set("q", q);
    if (v("filter-type")) params.set("type", v("filter-type"));
    if (v("filter-practice")) params.append("practice", v("filter-practice"));
    if (v("filter-phase")) params.append("engagement_phase", v("filter-phase"));
    if (v("filter-industry")) params.append("client_industry", v("filter-industry"));
    if (v("filter-problem")) params.append("problem_type", v("filter-problem"));
    if (v("filter-source")) params.set("source_origin", v("filter-source"));
    return params;
  }

  function renderConsultingCards(items) {
    var cardsEl = document.getElementById("consulting-cards");
    var emptyEl = document.getElementById("consulting-empty");
    cardsEl.innerHTML = "";
    if (!items || items.length === 0) {
      emptyEl.style.display = "block";
      return;
    }
    emptyEl.style.display = "none";
    for (var i = 0; i < items.length; i++) {
      (function (o) {
        var card = document.createElement("div");
        card.className = "consulting-card";
        card.setAttribute("data-object-id", o.id);
        var typeLabel = CONSULTING_TYPE_LABEL[o.type] || o.type;
        var sourceLabel = CONSULTING_SOURCE_LABEL[o.source_origin] || o.source_origin;
        var title = document.createElement("h3");
        title.textContent = o.title;
        var summary = document.createElement("p");
        summary.textContent = o.summary;
        var meta = document.createElement("div");
        meta.className = "consulting-meta";
        var b1 = document.createElement("span");
        b1.className = "badge badge-done";
        b1.textContent = typeLabel;
        var b2 = document.createElement("span");
        b2.className = "badge badge-wip";
        b2.textContent = sourceLabel;
        meta.appendChild(b1);
        meta.appendChild(b2);
        card.appendChild(title);
        card.appendChild(summary);
        card.appendChild(meta);
        card.addEventListener("click", function () { openConsultingDetail(o.id); });
        cardsEl.appendChild(card);
      })(items[i]);
    }
  }

  // ----- OEI-006 — second source: documents recalled from the content engine.
  // Additive only: the static catalogue rendering above is unchanged. The
  // engine group is a *hint rail* next to the catalogue, never a replacement.

  var CONSULTING_ENGINE_STATUS_COPY = {
    "ok": "",
    "unavailable": "内容引擎暂时不可用 — 以下仅为静态目录.",
    "disabled": "本环境未接入内容引擎 — 以下仅为静态目录.",
    "skipped": "输入关键词即可同时检索已索引文档."
  };

  var CONSULTING_ENGINE_SNIPPET_CHARS = 180;

  function formatConsultingEngineTime(value) {
    if (!value) return "—";
    return String(value).replace("T", " ").replace("Z", "").slice(0, 16);
  }

  function consultingEngineSnippet(value) {
    var text = value ? String(value) : "";
    if (text.length <= CONSULTING_ENGINE_SNIPPET_CHARS) return text;
    return text.slice(0, CONSULTING_ENGINE_SNIPPET_CHARS) + "…";
  }

  function renderConsultingEngine(items, status, staticTotal) {
    var groupEl = document.getElementById("consulting-engine");
    if (!groupEl) return;
    var statusEl = document.getElementById("consulting-engine-status");
    var cardsEl = document.getElementById("consulting-engine-cards");
    var emptyEl = document.getElementById("consulting-engine-empty");

    var list = items || [];
    var copy = CONSULTING_ENGINE_STATUS_COPY[status] || "";
    statusEl.textContent = copy;
    statusEl.style.display = copy ? "block" : "none";

    cardsEl.innerHTML = "";
    for (var i = 0; i < list.length; i++) {
      (function (doc) {
        var card = document.createElement("div");
        card.className = "consulting-card consulting-card-engine";
        card.setAttribute("data-engine-doc-id", doc.engine_doc_id);

        var title = document.createElement("h3");
        title.textContent = doc.title || "(无标题)";

        var snippet = document.createElement("p");
        snippet.className = "consulting-snippet";
        snippet.textContent = consultingEngineSnippet(doc.snippet);

        var meta = document.createElement("div");
        meta.className = "consulting-meta";
        var b1 = document.createElement("span");
        b1.className = "badge badge-done";
        b1.textContent = "引擎召回";
        var b2 = document.createElement("span");
        b2.className = "badge badge-wip";
        b2.textContent = doc.source_type || "—";
        var b3 = document.createElement("span");
        b3.className = "badge";
        b3.textContent = "更新 " + formatConsultingEngineTime(doc.updated_at);
        meta.appendChild(b1);
        meta.appendChild(b2);
        meta.appendChild(b3);

        card.appendChild(title);
        card.appendChild(snippet);
        card.appendChild(meta);
        card.addEventListener("click", function () { openConsultingEngineDetail(doc); });
        cardsEl.appendChild(card);
      })(list[i]);
    }

    // The group is shown when it has something to say: cards to display, or an
    // explanation of why there are none (engine down / not wired up).
    groupEl.hidden = !(list.length > 0 || copy !== "");

    // Empty state must name WHICH source came up empty (TASK step 3): "the
    // catalogue has no match" and "the indexed documents have no match" are
    // different messages, and on this engine they genuinely differ.
    if (staticTotal === 0) {
      var staticEmptyEl = document.getElementById("consulting-empty");
      if (staticEmptyEl) {
        staticEmptyEl.textContent = (status === "ok" && list.length > 0)
          ? "目录无命中 — 已索引文档里有相关内容, 见下方「引擎召回」."
          : "目录无命中 — 已索引文档里也没有找到相近内容.";
      }
    }
    emptyEl.hidden = list.length > 0;
  }

  // Engine cards reuse the existing detail drawer: no second panel, no extra
  // round trip (the snippet is already in hand).
  function openConsultingEngineDetail(doc) {
    var drawer = document.getElementById("consulting-detail");
    var titleEl = document.getElementById("consulting-detail-title");
    var summaryEl = document.getElementById("consulting-detail-summary");
    var fieldsEl = document.getElementById("consulting-detail-fields");
    titleEl.textContent = doc.title || "(无标题)";
    summaryEl.textContent = doc.snippet || "";
    fieldsEl.innerHTML = "";
    var rows = [
      ["来源分组", "引擎召回 (已索引文档)"],
      ["来源类型", doc.source_type || "—"],
      ["更新时间", formatConsultingEngineTime(doc.updated_at)],
      ["文档编号", doc.engine_doc_id || "—"]
    ];
    for (var i = 0; i < rows.length; i++) {
      var dt = document.createElement("dt");
      dt.textContent = rows[i][0];
      var dd = document.createElement("dd");
      dd.textContent = String(rows[i][1] || "—");
      fieldsEl.appendChild(dt);
      fieldsEl.appendChild(dd);
    }
    drawer.classList.add("open");
    drawer.setAttribute("aria-hidden", "false");
  }

  function runConsultingSearch() {
    var params = readConsultingFilters();
    var totalEl = document.getElementById("consulting-total");
    totalEl.textContent = "载入中…";
    fetch("/api/v1/consulting/library?" + params.toString(), {
      headers: { "Accept": "application/json" }
    })
      .then(function (r) { return r.json(); })
      .then(function (body) {
        var total = body && typeof body.total === "number" ? body.total : 0;
        totalEl.textContent = "共 " + total + " 条结果";
        renderConsultingCards(body && body.items ? body.items : []);
        renderConsultingEngine(
          body && body.engine_items ? body.engine_items : [],
          body && body.engine_status ? body.engine_status : "disabled",
          total
        );
      })
      .catch(function (err) {
        totalEl.textContent = "[GET /api/v1/consulting/library 失败] " +
          (err && err.message ? err.message : err);
      });
  }

  function loadConsultingLibrary() {
    var p = loadConsultingFacets();
    if (p && typeof p.then === "function") {
      p.then(runConsultingSearch);
    } else {
      runConsultingSearch();
    }
  }

  function renderTagList(values) {
    var ul = document.createElement("ul");
    ul.className = "tag-list";
    if (!values || values.length === 0) {
      var li = document.createElement("li");
      li.textContent = "—";
      ul.appendChild(li);
      return ul;
    }
    for (var i = 0; i < values.length; i++) {
      var li2 = document.createElement("li");
      li2.textContent = values[i];
      ul.appendChild(li2);
    }
    return ul;
  }

  function openConsultingDetail(objectId) {
    var drawer = document.getElementById("consulting-detail");
    var titleEl = document.getElementById("consulting-detail-title");
    var summaryEl = document.getElementById("consulting-detail-summary");
    var fieldsEl = document.getElementById("consulting-detail-fields");
    titleEl.textContent = "载入中…";
    summaryEl.textContent = "";
    fieldsEl.innerHTML = "";
    drawer.classList.add("open");
    drawer.setAttribute("aria-hidden", "false");

    fetch("/api/v1/consulting/objects/" + encodeURIComponent(objectId), {
      headers: { "Accept": "application/json" }
    })
      .then(function (r) {
        if (r.status === 404) {
          titleEl.textContent = "未找到";
          summaryEl.textContent = "未在咨询知识库中找到此条目 (id=" + objectId + ")";
          return null;
        }
        return r.json();
      })
      .then(function (o) {
        if (!o) return;
        titleEl.textContent = o.title;
        summaryEl.textContent = o.summary;
        fieldsEl.innerHTML = "";
        var rows = [
          ["类型", document.createTextNode(CONSULTING_TYPE_LABEL[o.type] || o.type)],
          ["来源", document.createTextNode(CONSULTING_SOURCE_LABEL[o.source_origin] || o.source_origin)],
          ["置信度", document.createTextNode(o.confidence)],
          ["状态", document.createTextNode(o.review_state)],
          ["实践", renderTagList(o.practice || [])],
          ["阶段", renderTagList(o.engagement_phase || [])],
          ["行业", renderTagList(o.client_industry || [])],
          ["问题类型", renderTagList(o.problem_types || [])],
          ["方法", renderTagList(o.methods || [])],
          ["交付物", renderTagList(o.deliverables || [])],
          ["产出", renderTagList(o.outcomes || [])]
        ];
        for (var i = 0; i < rows.length; i++) {
          var dt = document.createElement("dt");
          dt.textContent = rows[i][0];
          var dd = document.createElement("dd");
          if (rows[i][1] instanceof Node) {
            dd.appendChild(rows[i][1]);
          } else {
            dd.textContent = String(rows[i][1] || "—");
          }
          fieldsEl.appendChild(dt);
          fieldsEl.appendChild(dd);
        }
      })
      .catch(function (err) {
        titleEl.textContent = "载入失败";
        summaryEl.textContent = (err && err.message ? err.message : err);
      });
  }

  function closeConsultingDetail() {
    var drawer = document.getElementById("consulting-detail");
    drawer.classList.remove("open");
    drawer.setAttribute("aria-hidden", "true");
  }

  // ----- Consulting filter / search event wiring -----
  var searchInput = document.getElementById("consulting-search");
  if (searchInput) {
    searchInput.addEventListener("input", function () {
      // Debounce-free immediate search; SPA is in-memory small dataset.
      runConsultingSearch();
    });
  }

  var filterIds = [
    "filter-type", "filter-practice", "filter-phase",
    "filter-industry", "filter-problem", "filter-source"
  ];
  for (var fi = 0; fi < filterIds.length; fi++) {
    (function (id) {
      var el = document.getElementById(id);
      if (el) el.addEventListener("change", runConsultingSearch);
    })(filterIds[fi]);
  }

  var resetBtn = document.getElementById("consulting-reset");
  if (resetBtn) {
    resetBtn.addEventListener("click", function () {
      document.getElementById("consulting-search").value = "";
      for (var ri = 0; ri < filterIds.length; ri++) {
        document.getElementById(filterIds[ri]).value = "";
      }
      runConsultingSearch();
    });
  }

  var closeBtn = document.getElementById("consulting-detail-close");
  if (closeBtn) {
    closeBtn.addEventListener("click", closeConsultingDetail);
  }

  // ----- OEI-007 — upload + status wiring (additive; does not touch search) -----
  var uploadBtn = document.getElementById("consulting-upload-submit");
  if (uploadBtn) {
    uploadBtn.addEventListener("click", submitConsultingUpload);
  }

  function renderUploadRow(rec) {
    var li = document.createElement("li");
    li.className = "consulting-upload-row" + (rec.accepted ? "" : " rejected");
    li.setAttribute("data-document-id", rec.document_id || "");

    var name = document.createElement("span");
    name.className = "upload-row-name";
    name.textContent = rec.name;
    li.appendChild(name);

    if (rec.accepted) {
      var st = document.createElement("span");
      st.className = "badge " + (rec.status || "processing").toLowerCase();
      st.textContent = rec.status + (rec.chunk_count != null ? " · " + rec.chunk_count + " 块" : "");
      li.appendChild(st);

      var pollBtn = document.createElement("button");
      pollBtn.type = "button";
      pollBtn.textContent = "查询状态";
      pollBtn.addEventListener("click", function () {
        pollConsultingDocument(rec.document_id, li);
      });
      li.appendChild(pollBtn);
    } else {
      var reason = document.createElement("span");
      reason.className = "upload-row-reason";
      reason.textContent = rec.reason || "未知原因";
      li.appendChild(reason);
    }
    return li;
  }

  function pollConsultingDocument(docId, li) {
    fetch("/api/v1/consulting/documents/" + encodeURIComponent(docId))
      .then(function (r) { return r.json().then(function (b) { return { status: r.status, body: b }; }); })
      .then(function (r) {
        if (r.status !== 200) {
          setUploadStatus("状态查询失败: HTTP " + r.status + " — " + (r.body && r.body.detail || "未知"), true);
          return;
        }
        // Update the status badge inside the row.
        var badges = li.getElementsByClassName("badge");
        for (var bi = 0; bi < badges.length; bi++) {
          var b = badges[bi];
          b.className = "badge " + (r.body.status || "processing").toLowerCase();
          b.textContent = r.body.status + (r.body.chunk_count != null ? " · " + r.body.chunk_count + " 块" : "");
        }
        if (r.body.status === "FAILED" && r.body.failure_reason) {
          var existing = li.getElementsByClassName("upload-row-reason")[0];
          if (!existing) {
            var reason = document.createElement("span");
            reason.className = "upload-row-reason";
            reason.textContent = "失败原因: " + r.body.failure_reason;
            li.appendChild(reason);
          } else {
            existing.textContent = "失败原因: " + r.body.failure_reason;
          }
        }
        setUploadStatus("状态已更新: " + r.body.status);
      })
      .catch(function (e) { setUploadStatus("状态查询异常: " + e, true); });
  }

  function setUploadStatus(text, isError) {
    var s = document.getElementById("consulting-upload-status");
    if (!s) return;
    s.textContent = text;
    s.className = "muted" + (isError ? " error" : "");
  }

  function submitConsultingUpload() {
    var fileInput = document.getElementById("consulting-upload-file");
    var titleInput = document.getElementById("consulting-upload-title");
    var listEl = document.getElementById("consulting-upload-list");
    var rowsEl = document.getElementById("consulting-upload-rows");
    if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
      setUploadStatus("请先选择至少一个文件.", true);
      return;
    }
    var btn = document.getElementById("consulting-upload-submit");
    if (btn) btn.disabled = true;
    setUploadStatus("上传中…");

    var fd = new FormData();
    var title = titleInput && titleInput.value ? titleInput.value : "";
    for (var i = 0; i < fileInput.files.length; i++) {
      fd.append("file", fileInput.files[i], fileInput.files[i].name);
      fd.append("title", title);
    }

    fetch("/api/v1/consulting/documents", { method: "POST", body: fd })
      .then(function (r) { return r.json().then(function (b) { return { status: r.status, body: b }; }); })
      .then(function (r) {
        var docs = (r.body && r.body.documents) || [];
        var acceptedCount = 0;
        var rejectedCount = 0;
        for (var di = 0; di < docs.length; di++) {
          if (docs[di].accepted) acceptedCount++;
          else rejectedCount++;
          if (listEl && rowsEl) {
            listEl.hidden = false;
            rowsEl.appendChild(renderUploadRow(docs[di]));
          }
        }
        var msg = "上传完成: " + acceptedCount + " 个成功";
        if (rejectedCount > 0) msg += ", " + rejectedCount + " 个被拒绝";
        setUploadStatus(msg, rejectedCount > 0 && acceptedCount === 0);
        if (fileInput) fileInput.value = "";
        // After successful upload the new docs may be searchable. Trigger a search
        // refresh so the "engine recall" group populates without a manual reload.
        if (acceptedCount > 0) {
          runConsultingSearch();
        }
      })
      .catch(function (e) {
        setUploadStatus("上传失败: " + e, true);
      })
      .finally(function () {
        if (btn) btn.disabled = false;
      });
  }
})();
