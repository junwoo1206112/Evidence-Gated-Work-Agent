(() => {
  "use strict";

  const app = document.getElementById("app");
  const state = {
    runId: app.dataset.runId || "",
    detail: null,
    idemKey: "",
    busy: false,
    error: null,
    success: null,
    probeError: null,
  };

  const REASON_LABELS = {
    missing_source_url: "출처 URL 없음",
    url_not_https: "https 아님",
    url_host_not_allowed: "허용되지 않은 도메인",
    url_has_credentials: "URL 사용자 정보 포함",
    url_has_port: "기본 포트 아님",
    url_ip_host: "IP 주소 호스트",
    excerpt_too_short: "발췌 최소 길이 미달",
    excerpt_not_in_content: "본문에 없는 발췌",
    excerpt_has_ellipsis: "말줄임표 포함",
    below_min_score: "점수 기준 미달",
    not_yet_effective: "시행 전",
    superseded: "유효기간 만료",
    invalid_source_tier: "근거 등급 오류",
    invalid_policy_metadata: "정책 메타데이터 누락",
    duplicate_document: "중복 문서",
  };

  const ACTION_LABELS = {
    create_demo_draft: "데모 초안 생성",
    simulate_notification: "데모 알림 준비",
  };

  const DEMO_MODE_LABELS = {
    none: "정상",
    fail_once: "1차 실패 → 자동 재시도",
    fail_twice: "2회 실패 → 종료",
  };

  const CATEGORY_LABELS = {
    no_evidence: "근거 없음",
    conflict: "상충",
    invalid_citation: "인용 무효",
    low_score: "점수 미달",
    too_few_citations: "인용 부족",
  };

  const RISK_LABELS = { low: "낮음", medium: "중간", high: "높음" };

  // Keep in sync with Settings.min_citation_score (app/config.py).
  const SCORE_THRESHOLD = 0.42;

  // -- DOM helpers -------------------------------------------------------

  function el(tag, props = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(props || {})) {
      if (value === null || value === undefined || value === false) continue;
      if (key === "class") {
        node.className = value;
      } else if (key === "text") {
        node.textContent = String(value);
      } else if (key === "disabled") {
        node.disabled = Boolean(value);
      } else if (key === "value") {
        node.value = String(value);
      } else if (key === "readOnly") {
        node.readOnly = Boolean(value);
      } else if (key.startsWith("on") && typeof value === "function") {
        node.addEventListener(key.slice(2).toLowerCase(), value);
      } else {
        node.setAttribute(key, String(value));
      }
    }
    for (const child of children.flat(Infinity)) {
      if (child === null || child === undefined || child === false) continue;
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function append(parent, ...children) {
    for (const child of children.flat(Infinity)) {
      if (child === null || child === undefined || child === false) continue;
      parent.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
  }

  function badge(label, kind = "quiet") {
    return el("span", { class: `badge badge-${kind}` }, label);
  }

  function statusBadge(status, label) {
    return el("span", { class: "badge badge-status", "data-status": status }, label || status);
  }

  function empty(message) {
    return el("p", { class: "empty" }, message);
  }

  function card(title, subtitle, headerActions, ...body) {
    const head = el(
      "div",
      { class: "card-head" },
      el(
        "div",
        {},
        el("h2", { text: title }),
        subtitle ? el("p", { text: subtitle }) : null
      ),
      headerActions || null
    );
    return el("section", { class: "card" }, head, ...body);
  }

  function kvGrid(items) {
    return el(
      "dl",
      { class: "kv-grid" },
      ...items.map(([term, value]) =>
        el(
          "div",
          { class: "kv" },
          el("dt", { text: term }),
          el("dd", { text: value == null || value === "" ? "—" : String(value) })
        )
      )
    );
  }

  function reasonLabels(reasons) {
    if (!reasons || !reasons.length) return "—";
    return reasons.map((reason) => REASON_LABELS[reason] || reason).join(", ");
  }

  function scoreClass(score) {
    const percent = Math.max(0, Math.min(100, Math.round(Number(score || 0) * 100)));
    const bucket = Math.min(100, Math.round(percent / 10) * 10);
    const tone = percent >= 55 ? "score-high" : percent >= 35 ? "score-mid" : "score-low";
    return { bucket, tone };
  }

  function meter(score) {
    const { bucket, tone } = scoreClass(score);
    return el(
      "div",
      { class: "score-row" },
      el("span", { text: "score" }),
      el(
        "div",
        { class: "meter", role: "img", "aria-label": `검색 점수 ${Math.round(Number(score || 0) * 100)}%, 통과 기준 ${Math.round(SCORE_THRESHOLD * 100)}%` },
        el("span", { class: `meter-fill score-${bucket} ${tone}` }),
        el("span", { class: "meter-threshold", "aria-hidden": "true" })
      ),
      el("span", { text: Number(score || 0).toFixed(2) }),
      el("span", { class: "small muted", text: `기준 ${SCORE_THRESHOLD.toFixed(2)}` })
    );
  }

  function timeText(value) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString("ko-KR", { dateStyle: "medium", timeStyle: "medium" });
  }

  function shortHash(value) {
    if (!value) return "—";
    return String(value).slice(0, 12) + "…";
  }

  function sourceLink(url) {
    if (url && String(url).startsWith("https://")) {
      return el(
        "a",
        { href: url, target: "_blank", rel: "noopener noreferrer", class: "small" },
        "원문 URL"
      );
    }
    return el("span", { class: "small muted" }, "출처 URL 없음");
  }

  function tierBadge(tier) {
    return tier === "public_summary"
      ? badge("공개 요약", "public")
      : badge("합성 fixture", "synthetic");
  }

  function actionLabel(action) {
    return ACTION_LABELS[action] || action || "—";
  }

  function demoModeLabel(mode) {
    return DEMO_MODE_LABELS[mode] || mode || "—";
  }

  function categoryLabel(category) {
    return category ? CATEGORY_LABELS[category] || category : "차단 없음";
  }

  // -- API ---------------------------------------------------------------

  async function api(path, options = {}) {
    const headers = { Accept: "application/json" };
    if (options.body) headers["Content-Type"] = "application/json";
    const response = await fetch(path, { ...options, headers: { ...headers, ...(options.headers || {}) } });
    let data = null;
    const type = response.headers.get("content-type") || "";
    if (type.includes("application/json")) {
      data = await response.json().catch(() => null);
    } else {
      data = await response.text();
    }
    if (!response.ok) {
      const info = (data && data.error) || {
        code: `E_HTTP_${response.status}`,
        message: `HTTP ${response.status}`,
      };
      const error = new Error(info.message || `HTTP ${response.status}`);
      error.code = info.code;
      error.status = response.status;
      error.details = info.details;
      error.body = data;
      throw error;
    }
    return data;
  }

  function newKey() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return "demo-" + window.crypto.randomUUID().replace(/-/g, "").slice(0, 24);
    }
    return "demo-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
  }

  function errorBox(error, title = "요청이 거부되었습니다") {
    if (!error) return null;
    return el(
      "div",
      { class: "error-box", role: "alert" },
      el("div", { class: "error-code", text: `${error.code || "E_UNKNOWN"} · HTTP ${error.status || "?"}` }),
      el("div", { text: error.message || "알 수 없는 오류입니다." }),
      error.details
        ? el("pre", { class: "error-detail", text: JSON.stringify(error.details, null, 2) })
        : null,
      error.body && !error.body.error
        ? el("pre", { class: "error-detail", text: JSON.stringify(error.body, null, 2) })
        : null
    );
  }

  function successBox(message) {
    if (!message) return null;
    return el("div", { class: "success-box", role: "status" }, message);
  }

  // -- landing -----------------------------------------------------------

  function renderLanding() {
    state.detail = null;
    clear(app);
    append(
      app,
      state.error ? errorBox(state.error) : null,
      el(
        "section",
        { class: "card hero" },
        el(
          "div",
          {},
          el("span", { class: "badge badge-demo" }, "2분 데모"),
          el("h2", { text: "근거가 부족하면 계획을 만들지 않습니다." }),
          el(
            "p",
            { text: "요청 → 공개 규정 검색 → 인용/점수/URL/상충 검사 → 제한된 계획 → 사람 승인 → 모의 실행 → 감사 타임라인을 한 화면에서 확인합니다." }
          ),
          el(
            "ul",
            { class: "hero-points" },
            el("li", {}, "근거 부족·상충이면 plans/approvals/executions 행이 0개입니다."),
            el("li", {}, "승인 전 실행은 화면이 아니라 서버가 409로 거절합니다."),
            el("li", {}, "실행은 결정론적 mock이며 외부 시스템·LLM·네트워크를 호출하지 않습니다.")
          )
        ),
        el(
          "div",
          { class: "preset-grid" },
          presetButton(
            "① 충분 근거",
            "공사 계약보증금·지연배상금 요약 2건으로 계획 생성",
            "시설공사 계약보증금과 지연배상금 기준을 확인해 초안을 작성해줘",
            "none"
          ),
          presetButton(
            "② 부족 근거",
            "코퍼스에 없는 우주발사체 질의 → 계획 없음",
            "우주발사체 발사보험 면책 특약과 발사허가 절차를 정리해줘",
            "none"
          ),
          presetButton(
            "③ 상충 근거",
            "같은 정책 키·범위에서 10% vs 5% fixture 충돌",
            "물품 계약보증금 비율 기준을 확인해줘",
            "none"
          ),
          presetButton(
            "④ 실패 → 자동 재시도",
            "1차 실패 후 2차 성공, attempt 2건 기록",
            "시설공사 지연배상금 산정 기준과 계약업무 처리 절차를 확인해 알림을 준비해줘",
            "fail_once"
          )
        )
      ),
      card(
        "직접 요청하기",
        "요청은 500자 이내이며 이메일·전화번호·주민번호·지시 우회 문구는 서버가 거부합니다.",
        null,
        el(
          "form",
          {
            class: "form-grid",
            onSubmit: (event) => {
              event.preventDefault();
              const request = event.currentTarget.elements.request.value;
              const mode = event.currentTarget.elements.demo_mode.value;
              createRun(request, mode);
            },
          },
          el(
            "div",
            { class: "form-row" },
            el("label", { for: "request-input" }, "업무 요청"),
            el("textarea", {
              id: "request-input",
              name: "request",
              maxlength: "500",
              placeholder: "예: 시설공사 계약보증금과 지연배상금 기준을 확인해 초안을 작성해줘",
              required: "required",
            })
          ),
          el(
            "div",
            { class: "button-row" },
            el("button", { class: "button button-primary", type: "submit" }, "요청 실행"),
            el("span", { class: "small muted", text: "기본 시나리오: 정상 실행" })
          ),
          el(
            "details",
            { class: "advanced" },
            el("summary", {}, "고급: 실패 시나리오 (데모 장치)"),
            el(
              "div",
              { class: "form-row" },
              el("label", { for: "demo-mode" }, "실행 시나리오"),
              el(
                "select",
                { id: "demo-mode", name: "demo_mode" },
                el("option", { value: "none" }, "정상 실행"),
                el("option", { value: "fail_once" }, "1차 실패 → 자동 재시도"),
                el("option", { value: "fail_twice" }, "2회 실패 → 최종 실패")
              )
            )
          )
        )
      )
    );
  }

  function presetButton(title, description, request, mode) {
    return el(
      "button",
      {
        class: "preset",
        type: "button",
        onClick: () => createRun(request, mode),
      },
      el("strong", { text: title }),
      el("span", { text: description })
    );
  }

  async function createRun(request, mode) {
    if (state.busy) return;
    state.busy = true;
    state.error = null;
    state.success = null;
    state.probeError = null;
    clear(app);
    app.append(
      el(
        "section",
        { class: "card" },
        el("h2", {}, "요청 처리 중 ", el("span", { class: "loading", "aria-hidden": "true" })),
        el("p", { class: "muted" }, "검색 → 게이트 → 계획 생성을 서버에서 수행합니다.")
      )
    );
    try {
      const detail = await api("/api/runs", {
        method: "POST",
        body: JSON.stringify({ request, demo_mode: mode }),
      });
      state.runId = detail.run.run_id;
      state.idemKey = newKey();
      state.detail = detail;
      state.busy = false;
      history.pushState({ runId: state.runId }, "", `/runs/${state.runId}`);
      renderRun(detail);
    } catch (error) {
      state.error = error;
      state.busy = false;
      renderLanding();
    } finally {
      state.busy = false;
    }
  }

  // -- run page ----------------------------------------------------------

  async function loadRun() {
    clear(app);
    app.append(
      el("section", { class: "card" }, el("h2", {}, "run 불러오는 중"), el("p", { class: "muted" }, state.runId))
    );
    try {
      const detail = await api(`/api/runs/${encodeURIComponent(state.runId)}`);
      state.detail = detail;
      if (!state.idemKey) {
        const first = detail.executions && detail.executions[0];
        state.idemKey = first ? first.idempotency_key : newKey();
      }
      renderRun(detail);
    } catch (error) {
      state.error = error;
      clear(app);
      app.append(
        errorBox(error, "run을 불러오지 못했습니다"),
        el("a", { class: "button", href: "/" }, "새 요청으로 돌아가기")
      );
    }
  }

  async function refresh(message = null) {
    if (!state.runId) return;
    const detail = await api(`/api/runs/${encodeURIComponent(state.runId)}`);
    state.detail = detail;
    if (message) state.success = message;
    renderRun(detail);
  }

  async function decide(decision) {
    if (state.busy || !state.detail) return;
    state.busy = true;
    state.error = null;
    try {
      const reasonInput = document.getElementById("approval-reason");
      const reason = reasonInput ? reasonInput.value : "";
      const detail = await api(`/api/runs/${encodeURIComponent(state.runId)}/approval`, {
        method: "POST",
        body: JSON.stringify({ decision, reason }),
      });
      state.detail = detail;
      state.success = decision === "approve" ? "사람 승인이 기록되었습니다. 이제 모의 실행을 요청할 수 있습니다." : "요청이 반려되었습니다.";
      state.probeError = null;
      state.busy = false;
      renderRun(detail);
    } catch (error) {
      state.error = error;
      state.busy = false;
      renderRun(state.detail);
    } finally {
      state.busy = false;
    }
  }

  async function execute(probe = false) {
    if (state.busy || !state.detail) return;
    state.busy = true;
    state.error = null;
    if (!probe) state.probeError = null;
    const key = (state.idemKey || newKey()).trim();
    state.idemKey = key;
    try {
      const detail = await api(`/api/runs/${encodeURIComponent(state.runId)}/executions`, {
        method: "POST",
        body: JSON.stringify({ idempotency_key: key }),
      });
      state.detail = detail;
      state.success = detail.meta && detail.meta.replayed
        ? "같은 idempotency key 재요청입니다. 신규 실행 없이 기존 결과를 반환했습니다."
        : "모의 실행이 완료되었습니다.";
      state.probeError = null;
      state.busy = false;
      renderRun(detail);
    } catch (error) {
      if (probe) {
        state.probeError = error;
      } else {
        state.error = error;
      }
      state.busy = false;
      renderRun(state.detail);
    } finally {
      state.busy = false;
    }
  }

  function backToLanding() {
    state.runId = "";
    state.detail = null;
    state.idemKey = "";
    state.error = null;
    state.success = null;
    state.probeError = null;
    history.pushState({}, "", "/");
    renderLanding();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // -- render run --------------------------------------------------------

  function renderRun(detail) {
    state.detail = detail;
    const run = detail.run;
    document.title = `${run.status_label} · ${run.run_id.slice(0, 12)} · Evidence-Gated Work Agent`;
    clear(app);

    append(
      app,
      state.error ? errorBox(state.error) : null,
      state.success ? successBox(state.success) : null,
      detail.integrity_warning
        ? errorBox({ code: "E_DATA_INTEGRITY", message: detail.integrity_warning, status: 200 })
        : null,
      renderSummary(detail),
      renderGate(detail),
      renderEvidence(detail),
      renderPlan(detail),
      renderApproval(detail),
      renderExecution(detail),
      renderAudit(detail)
    );
  }

  function renderSummary(detail) {
    const run = detail.run;
    return card(
      "요청과 상태",
      "모든 화면 상태는 서버 응답을 다시 읽어 렌더링합니다.",
      el(
        "div",
        { class: "button-row" },
        el("button", { class: "button", type: "button", onClick: backToLanding }, "새 요청"),
        el(
          "button",
          {
            class: "button",
            type: "button",
            onClick: () => refresh(),
            disabled: state.busy,
          },
          "서버 상태 새로고침"
        )
      ),
      el("div", { class: "button-row" }, statusBadge(run.status, run.status_label), badge(`시나리오: ${demoModeLabel(run.demo_mode)}`, "quiet"), badge(`실행 시도: ${detail.capabilities.execution_attempts}`, "quiet")),
      el("p", { class: "request-text", text: run.user_request }),
      el("div", { style: null }),
      kvGrid([
        ["run_id", run.run_id],
        ["created_at", timeText(run.created_at)],
        ["as_of", run.as_of],
        ["plan hash", detail.plan ? shortHash(detail.plan.plan_hash) : "—"],
        ["evidence fingerprint", shortHash(run.evidence_fingerprint)],
        ["config hash", shortHash(run.config_hash)],
        ["corpus sha256", shortHash(detail.corpus.sha256)],
        ["감사 이벤트", `${detail.audit.length}건 · chain ${detail.audit_chain.valid ? "valid" : "broken"}`],
      ]),
      el("hr", { class: "divider" }),
      stepper(run.status)
    );
  }

  function stepper(status) {
    const labels = ["요청", "근거 검색", "Gate", "계획", "승인", "모의 실행", "감사"];
    const mapping = {
      DRAFT: { active: 1 },
      RETRIEVING: { active: 1 },
      EVIDENCE_INSUFFICIENT: { active: 2, blocked: true },
      PENDING_APPROVAL: { active: 4 },
      APPROVED: { active: 5 },
      EXECUTING: { active: 5 },
      RETRYING: { active: 5 },
      EXECUTED: { active: 7 },
      FAILED: { active: 5, blocked: true, tail: [6] },
      REJECTED: { active: 4, blocked: true, tail: [6] },
    };
    const current = mapping[status] || { active: 0 };
    return el(
      "div",
      { class: "step-strip", role: "list", "aria-label": "워크플로 단계" },
      ...labels.map((label, index) => {
        let cls = "step";
        if (current.tail && current.tail.includes(index)) cls += " done";
        else if (index < current.active) cls += " done";
        else if (index === current.active) cls += current.blocked ? " blocked" : " active";
        return el(
          "div",
          { class: cls, role: "listitem" },
          el("span", { class: "step-dot", "aria-hidden": "true" }),
          label
        );
      })
    );
  }

  function renderGate(detail) {
    const gate = detail.gate;
    const header = el(
      "div",
      { class: "button-row" },
      gate && gate.passed ? badge("PASS", "valid") : badge("BLOCKED", "invalid"),
      badge("서버 판정", "quiet")
    );
    if (!gate) {
      return card("Evidence Gate", "게이트 판정이 없습니다.", header, empty("게이트 결과 없음"));
    }
    const reasons = el(
      "ul",
      { class: "gate-reasons" },
      ...(gate.reasons && gate.reasons.length ? gate.reasons : ["차단 사유 없음"]).map((reason) =>
        el("li", { text: reason })
      )
    );
    return card(
      "Evidence Gate",
      "인용 2개 이상 · 점수 하한 · https/도메인 · 본문 일치 · 유효기간 · 상충 검사를 서버에서 수행합니다.",
      header,
      el(
        "div",
        { class: gate.passed ? "gate gate-pass" : "gate gate-fail" },
        el(
          "div",
          { class: "gate-title" },
          el("h3", { text: gate.passed ? "근거 충분: 계획 생성 가능" : "근거 부족: 계획 생성 차단" }),
          badge(`공개 유효 ${gate.public_valid_count}/${gate.required_count}`, gate.passed ? "valid" : "invalid"),
          badge(`전체 유효 ${gate.valid_count} (합성 포함)`, "quiet"),
          badge(`차단 범주: ${categoryLabel(gate.category)}`, "quiet"),
          badge(`점수 기준 ${SCORE_THRESHOLD.toFixed(2)}`, "quiet")
        ),
        reasons
      ),
      gate.checks && gate.checks.length
        ? el(
            "div",
            { class: "table-scroll" },
            el(
              "table",
              { class: "checks-table" },
              el(
                "thead",
                {},
                el(
                  "tr",
                  {},
                  el("th", {}, "문서"),
                  el("th", {}, "점수"),
                  el("th", {}, "판정"),
                  el("th", {}, "사유"),
                  el("th", {}, "등급")
                )
              ),
              el(
                "tbody",
                {},
                ...gate.checks.map((check) =>
                  el(
                    "tr",
                    {},
                    el("td", {}, el("div", { class: "mono", text: check.document_id })),
                    el("td", {}, Number(check.score || 0).toFixed(2)),
                    el("td", {}, check.citation_valid ? badge("valid", "valid") : badge("invalid", "invalid")),
                    el("td", { text: reasonLabels(check.invalid_reasons || (check.invalid_reason ? [check.invalid_reason] : [])) }),
                    el("td", {}, tierBadge(check.source_tier))
                  )
                )
              )
            )
          )
        : empty("검색된 근거 후보가 없습니다.")
    );
  }

  function renderEvidence(detail) {
    const evidence = detail.evidence || [];
    return card(
      "근거 후보",
      "검색 점수는 절대값(IDF 가중 coverage + BM25)이며 min-max 정규화를 사용하지 않습니다.",
      badge(`${evidence.length} candidates`, "quiet"),
      evidence.length
        ? el(
            "div",
            { class: "evidence-grid" },
            ...evidence.map((item) => {
              const valid = Boolean(item.citation_valid);
              const reasons = item.invalid_reason ? [item.invalid_reason] : [];
              return el(
                "article",
                { class: `evidence-card ${valid ? "valid" : "invalid"}` },
                el(
                  "div",
                  { class: "evidence-head" },
                  el(
                    "div",
                    {},
                    el("div", { class: "evidence-title", text: item.title }),
                    el("div", { class: "evidence-section", text: `${item.section} · ${item.document_id}` })
                  ),
                  valid ? badge("valid", "valid") : badge("invalid", "invalid")
                ),
                el("div", { class: "button-row" }, tierBadge(item.source_tier), badge(`일치 ${item.matched_terms.length}`, "quiet")),
                meter(item.retrieval_score),
                el("blockquote", { class: "excerpt", text: item.excerpt }),
                item.matched_terms.length
                  ? el("div", { class: "small muted", text: `일치어: ${item.matched_terms.join(", ")}` })
                  : null,
                !valid ? el("div", { class: "small", text: `사유: ${reasonLabels(reasons)} ${item.invalid_detail || ""}` }) : null,
                item.policy_key
                  ? el("div", { class: "small muted", text: `정책 키: ${item.policy_key} / ${item.policy_value}` })
                  : null,
                sourceLink(item.source_url)
              );
            })
          )
        : empty("검색된 근거 후보가 없습니다.")
    );
  }

  function renderPlan(detail) {
    const plan = detail.plan;
    const header = plan
      ? el("div", { class: "button-row" }, badge(actionLabel(plan.plan.allowed_action), "quiet"), badge(`위험도: ${RISK_LABELS[plan.plan.risk_level] || plan.plan.risk_level}`, "quiet"))
      : badge("no plan", "invalid");
    if (!plan) {
      return card(
        "제한 계획",
        "근거 부족이면 계획 레코드를 만들지 않습니다.",
        header,
        empty("계획이 생성되지 않았습니다. 이것이 이 데모의 핵심 차단 동작입니다.")
      );
    }
    const planData = plan.plan;
    const copyButton = el(
      "button",
      {
        class: "button",
        type: "button",
        onClick: async () => {
          try {
            await navigator.clipboard.writeText(JSON.stringify(planData, null, 2));
            state.success = "계획 JSON을 클립보드에 복사했습니다.";
            renderRun(state.detail);
          } catch (error) {
            state.error = { code: "E_CLIPBOARD", message: "클립보드 복사에 실패했습니다.", status: 0 };
            renderRun(state.detail);
          }
        },
      },
      "JSON 복사"
    );
    return card(
      "제한 계획",
      "자유 텍스트가 아니라 steps / required_evidence_ids / risk_level / allowed_action으로 제한된 JSON입니다.",
      el("div", { class: "button-row" }, header, copyButton),
      el(
        "div",
        { class: "split" },
        el(
          "div",
          { class: "panel" },
          el("h3", {}, "계획 단계"),
          el(
            "ol",
            { class: "steps-list" },
            ...planData.steps.map((step) =>
              el(
                "li",
                {},
                el("strong", { text: `${step.step_id}. ${step.title}` }),
                el("span", { text: step.description }),
                step.uses_evidence_ids && step.uses_evidence_ids.length
                  ? el("div", { class: "mono muted", text: `evidence: ${step.uses_evidence_ids.join(", ")}` })
                  : null
              )
            )
          ),
          el("hr", { class: "divider" }),
          kvGrid([
            ["allowed_action", actionLabel(planData.allowed_action)],
            ["required_evidence_ids", planData.required_evidence_ids.join(", ")],
            ["plan_hash", plan.plan_hash],
            ["simulation.mode", demoModeLabel(planData.simulation.mode)],
            ["max_attempts", planData.simulation.max_attempts],
            ["external_side_effects", planData.simulation.external_side_effects ? "있음" : "없음"],
          ])
        ),
        el(
          "div",
          { class: "panel" },
          el("h3", {}, "계획 JSON"),
          el("pre", { class: "json", text: JSON.stringify(planData, null, 2) })
        )
      )
    );
  }

  function renderApproval(detail) {
    const run = detail.run;
    const approval = detail.approval;
    const capabilities = detail.capabilities;
    if (!detail.plan) {
      return card(
        "사람 승인",
        "계획이 없으면 승인 API도 호출할 수 없습니다.",
        badge("blocked", "invalid"),
        empty("승인할 계획이 없습니다.")
      );
    }
    if (approval) {
      return card(
        "사람 승인",
        "승인은 계획 hash에 결속됩니다.",
        badge(approval.decision === "approve" ? "approved" : "rejected", approval.decision === "approve" ? "valid" : "invalid"),
        kvGrid([
          ["approved_by", approval.approved_by],
          ["decision", approval.decision],
          ["plan_hash", shortHash(approval.plan_hash)],
          ["decided_at", timeText(approval.decided_at)],
          ["reason", approval.reason || "—"],
        ]),
        el("p", { class: "small muted", text: "demo-reviewer는 공개 데모의 고정 비식별자이며 실제 신원 인증이 아닙니다." })
      );
    }

    if (run.status !== "PENDING_APPROVAL") {
      return card(
        "사람 승인",
        "승인 대기 상태가 아닙니다.",
        badge("blocked", "invalid"),
        empty(capabilities.approval_block_reason || "현재 상태에서는 승인할 수 없습니다.")
      );
    }

    return card(
      "사람 승인",
      "승인 전에는 서버가 실행 요청을 409로 거절합니다.",
      badge("pending", "quiet"),
      el(
        "div",
        { class: "form-grid" },
        el(
          "div",
          { class: "form-row" },
          el("label", { for: "approval-reason" }, "승인/반려 사유 (선택)"),
          el("input", { id: "approval-reason", type: "text", maxlength: "300", placeholder: "예: 근거 2건과 계획 범위를 확인함" })
        ),
        state.probeError ? errorBox(state.probeError, "승인 전 실행 시도 결과") : null,
        el(
          "p",
          { class: "small muted", text: "승인 전에 아래 버튼을 누르면 실행 API를 직접 호출해 서버 차단(409)을 확인할 수 있습니다." }
        ),
        el(
          "button",
          {
            class: "button button-danger",
            type: "button",
            disabled: state.busy,
            onClick: () => execute(true),
          },
          "승인 전 실행 시도 (409 확인)"
        ),
        el(
          "div",
          { class: "button-row" },
          el(
            "button",
            {
              class: "button button-primary",
              type: "button",
              disabled: !capabilities.can_approve || state.busy,
              onClick: () => decide("approve"),
            },
            "승인"
          ),
          el(
            "button",
            {
              class: "button button-danger",
              type: "button",
              disabled: !capabilities.can_reject || state.busy,
              onClick: () => decide("reject"),
            },
            "반려"
          )
        )
      )
    );
  }

  function renderExecution(detail) {
    const run = detail.run;
    const capabilities = detail.capabilities;
    const executions = detail.executions || [];
    const body = [];

    if (run.status === "PENDING_APPROVAL") {
      body.push(empty("사람 승인 후 모의 실행을 요청할 수 있습니다. 승인 패널에서 409 차단을 먼저 확인하세요."));
    } else if (capabilities.can_execute || capabilities.can_replay) {
      body.push(
        el(
          "div",
          { class: "form-row" },
          el("label", { for: "idempotency-key" }, "idempotency key"),
          el("input", {
            id: "idempotency-key",
            type: "text",
            value: state.idemKey,
            maxlength: "64",
            readOnly: executions.length > 0,
            onInput: (event) => {
              state.idemKey = event.currentTarget.value;
            },
          })
        ),
        el(
          "p",
          { class: "small muted", text: executions.length
            ? "실행 후에는 키를 변경할 수 없습니다. 변경 요청은 409 E_ALREADY_EXECUTED로 거절됩니다."
            : "같은 키 재요청은 신규 실행 없이 기존 결과를 반환합니다. 다른 키로 재실행할 수 없습니다." }
        ),
        el(
          "div",
          { class: "button-row" },
          el(
            "button",
            {
              class: "button button-primary",
              type: "button",
              disabled: state.busy,
              onClick: () => execute(false),
            },
            capabilities.can_replay ? "같은 키로 재요청 (멱등 확인)" : "모의 실행"
          )
        )
      );
    } else {
      body.push(empty(capabilities.execution_block_reason || "현재 상태에서는 실행할 수 없습니다."));
    }

    if (executions.length) {
      body.push(
        el(
          "div",
          { class: "table-scroll" },
          el(
            "table",
            { class: "checks-table" },
            el(
              "thead",
              {},
              el("tr", {}, el("th", {}, "attempt"), el("th", {}, "status"), el("th", {}, "key"), el("th", {}, "error"), el("th", {}, "result"))
            ),
            el(
              "tbody",
              {},
              ...executions.map((execution) =>
                el(
                  "tr",
                  {},
                  el("td", { text: String(execution.attempt) }),
                  el("td", {}, execution.status === "EXECUTED" ? badge("EXECUTED", "valid") : badge("FAILED", "invalid")),
                  el("td", { class: "mono", text: execution.idempotency_key }),
                  el("td", { text: execution.error_reason || "—" }),
                  el(
                    "td",
                    {},
                    execution.result
                      ? el("details", {}, el("summary", {}, "결과 보기"), el("pre", { class: "error-detail", text: JSON.stringify(execution.result, null, 2) }))
                      : "—"
                  )
                )
              )
            )
          )
        )
      );
    }

    return card(
      "모의 실행",
      "결정론적 mock만 허용합니다. 외부 메일·결재·조달 시스템으로 나가는 호출은 없습니다.",
      badge(`실행 시도 ${executions.length}`, "quiet"),
      ...body
    );
  }

  function renderAudit(detail) {
    const events = detail.audit || [];
    return card(
      "감사 타임라인",
      "상태 변경과 감사 이벤트는 같은 트랜잭션에서 기록되고, hash chain으로 연결됩니다.",
      badge(detail.audit_chain.valid ? `hash chain valid · ${detail.audit_chain.events} events` : "hash chain broken", detail.audit_chain.valid ? "valid" : "invalid"),
      events.length
        ? el(
            "ol",
            { class: "timeline" },
            ...events.map((event) => {
              const type = event.event_type;
              const dotClass = type.startsWith("DENIED_") ? "denied" : type === "STATE_TRANSITION" ? "state" : "";
              return el(
                "li",
                { class: "timeline-item" },
                el("span", { class: `timeline-dot ${dotClass}`, "aria-hidden": "true" }),
                el(
                  "div",
                  { class: "timeline-body" },
                  el(
                    "div",
                    { class: "timeline-head" },
                    el("strong", { text: `#${event.seq} ${type}` }),
                    badge(shortHash(event.event_hash), "quiet"),
                    el("time", { text: timeText(event.occurred_at) })
                  ),
                  el(
                    "details",
                    {},
                    el("summary", {}, "payload 보기"),
                    el("pre", { text: JSON.stringify(event.payload, null, 2) })
                  )
                )
              );
            })
          )
        : empty("감사 이벤트가 없습니다.")
    );
  }

  // -- boot --------------------------------------------------------------

  window.addEventListener("popstate", () => {
    const match = window.location.pathname.match(/^\/runs\/([^/]+)$/);
    if (match) {
      state.runId = decodeURIComponent(match[1]);
      state.idemKey = "";
      loadRun();
    } else {
      state.runId = "";
      renderLanding();
    }
  });

  if (state.runId) {
    loadRun();
  } else {
    renderLanding();
  }
})();
