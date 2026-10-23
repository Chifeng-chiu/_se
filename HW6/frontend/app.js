/* TestPulse Omni — dashboard controller
   Vanilla JS, Monaco, Chart.js and the six FastAPI test engines. */
(() => {
  'use strict';

  const MODULES = {
    unit: {
      kicker: 'Module 01 / Unit',
      title: '單元測試沙箱',
      description: '在無網路的 Docker 容器中執行 pytest，隔離使用者程式碼並捕捉測試結果。',
    },
    integration: {
      kicker: 'Module 02 / Integration',
      title: '整合測試鏈',
      description: '依序執行多步驟 API 請求，驗證 Token 與回應資料能正確流入下一個模組。',
    },
    e2e: {
      kicker: 'Module 03 / End-to-End',
      title: '端到端瀏覽器測試',
      description: '使用 Headless Chromium 實際開啟頁面，驗證標題、元素、點擊、文字與最終網址。',
    },
    load: {
      kicker: 'Module 04 / Performance',
      title: '效能與壓力測試',
      description: '以 httpx 非同步送出高併發請求，量測 RPS、延遲百分位與成功率。',
    },
    security: {
      kicker: 'Module 05 / Security',
      title: '資安基礎掃描',
      description: '檢查 Security Headers、Cookie 旗標、CORS 設定，並執行無害的 XSS / SQLi 反射探測。',
    },
    visual: {
      kicker: 'Module 06 / Visual',
      title: 'UI 視覺回歸',
      description: 'Playwright 截圖 + Pillow 像素差異比對，第一次建立 Baseline，之後產生紅色差異標示圖。',
    },
  };

  const MODULE_LABELS = {
    unit: 'Unit',
    integration: 'Integration',
    e2e: 'E2E',
    load: 'Load',
    security: 'Security',
    visual: 'Visual',
  };

  const SAMPLE_UNIT_CODE = `from math import sqrt


def normalize_scores(scores):
    """Convert raw scores to a 0..1 scale and drop invalid values."""
    if not scores:
        return []
    valid = [float(score) for score in scores if score is not None]
    if not valid:
        return []
    high = max(valid)
    if high == 0:
        return [0.0 for _ in valid]
    return [round(sqrt(score / high), 4) for score in valid]
`;

  const SAMPLE_UNIT_TESTS = `from solution import normalize_scores


def test_empty_input():
    assert normalize_scores([]) == []


def test_relative_scaling():
    assert normalize_scores([0, 25, 100]) == [0.0, 0.5, 1.0]


def test_all_zero_scores():
    assert normalize_scores([0, 0, 0]) == [0.0, 0.0, 0.0]
`;

  const SAMPLE_INTEGRATION = `[
  {
    "name": "Create session",
    "method": "POST",
    "url": "https://httpbin.org/post",
    "json": { "username": "pulse-demo", "role": "admin" },
    "extract": {
      "demo_user": "body.json.username",
      "demo_role": "body.json.role"
    },
    "assertions": [
      { "source": "status", "op": "eq", "value": 200 },
      { "source": "body.json.role", "op": "eq", "value": "admin" }
    ]
  },
  {
    "name": "Read profile with extracted context",
    "method": "GET",
    "url": "https://httpbin.org/get",
    "params": {
      "user": "{{demo_user}}",
      "role": "{{demo_role}}"
    },
    "assertions": [
      { "source": "status", "op": "eq", "value": 200 },
      { "source": "body.args.user", "op": "eq", "value": "pulse-demo" }
    ]
  }
]`;

  const state = {
    module: 'unit',
    editors: {},
    monacoReady: false,
    loadChart: null,
    history: [],
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    }[char]));
  }

  function formatDate(value) {
    if (!value) return '—';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString('zh-TW', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  }

  function formatMs(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
    const number = Number(value);
    if (number >= 1000) return `${(number / 1000).toFixed(2)}s`;
    return `${Math.round(number)}ms`;
  }

  function formatValue(value) {
    if (value === null) return 'null';
    if (value === undefined) return 'undefined';
    if (typeof value === 'object') {
      try { return JSON.stringify(value); } catch { return String(value); }
    }
    return String(value);
  }

  function statusBadge(status) {
    const normalized = String(status || 'unknown').toLowerCase();
    if (normalized === 'passed') return '<span class="badge badge-pass">● PASS</span>';
    if (normalized === 'failed') return '<span class="badge badge-fail">● FAIL</span>';
    if (normalized === 'error') return '<span class="badge badge-fail">● ERROR</span>';
    return `<span class="badge badge-info">${esc(normalized)}</span>`;
  }

  function severityBadge(severity) {
    const value = String(severity || 'info').toLowerCase();
    const cls = value === 'high' || value === 'critical' ? 'badge-fail'
      : value === 'medium' ? 'badge-warn' : 'badge-info';
    return `<span class="badge ${cls}">${esc(value.toUpperCase())}</span>`;
  }

  function emptyCard(title, subtitle) {
    return `<div class="empty-state"><div class="text-[12px]">${esc(title)}</div><div class="font-mono text-[9px] uppercase tracking-widest text-slate-700">${esc(subtitle)}</div></div>`;
  }

  function errorCard(message) {
    return `<div class="result-banner fail">
      <div class="min-w-0">
        <div class="mb-2 flex items-center gap-2"><span class="badge badge-fail">● REQUEST ERROR</span></div>
        <div class="break-words text-[13px] text-rose-100/90">${esc(message)}</div>
      </div>
    </div>`;
  }

  function resultBanner(result) {
    const ok = Boolean(result.passed);
    const recorded = String(result.recorded_status || (ok ? 'passed' : 'failed')).toLowerCase();
    const label = recorded === 'error' ? 'ERROR' : ok ? 'PASS' : 'FAIL';
    const cls = ok ? 'pass' : 'fail';
    const badgeCls = ok ? 'badge-pass' : 'badge-fail';
    const history = result.history_id ? `RUN #${result.history_id}` : 'NOT PERSISTED';
    return `<div class="result-banner ${cls}">
      <div class="min-w-0">
        <div class="mb-2 flex flex-wrap items-center gap-2">
          <span class="badge ${badgeCls}">● ${label}</span>
          <span class="font-mono text-[9px] uppercase tracking-wider text-slate-600">${history}</span>
        </div>
        <div class="break-words text-[13px] leading-relaxed text-slate-200">${esc(result.summary || 'No summary returned.')}</div>
      </div>
      <div class="shrink-0 text-right">
        <div class="metric-label">Wall time</div>
        <div class="mt-1 font-mono text-sm text-slate-300">${formatMs(result.duration_ms)}</div>
      </div>
    </div>`;
  }

  function metric(label, value, accent = 'text-slate-100', note = '') {
    return `<div class="stat-card">
      <div class="metric-label">${esc(label)}</div>
      <div class="mt-2 font-mono text-[17px] ${accent}">${esc(value)}</div>
      ${note ? `<div class="mt-1 text-[9px] text-slate-600">${esc(note)}</div>` : ''}
    </div>`;
  }

  function sectionTitle(title, aside = '') {
    return `<div class="mb-3 flex items-center justify-between gap-3">
      <div class="flex items-center gap-2"><span class="h-1 w-1 rounded-full bg-pulse"></span><h3 class="font-mono text-[10px] uppercase tracking-[0.16em] text-slate-400">${esc(title)}</h3></div>
      ${aside ? `<span class="font-mono text-[9px] text-slate-600">${esc(aside)}</span>` : ''}
    </div>`;
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      method: options.method || 'GET',
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
    let data = null;
    try { data = await response.json(); } catch { data = null; }
    if (!response.ok) {
      let message = `HTTP ${response.status}`;
      if (data && data.detail) {
        if (Array.isArray(data.detail)) {
          message = data.detail.map((item) => item.msg || JSON.stringify(item)).join('; ');
        } else {
          message = String(data.detail);
        }
      }
      throw new Error(message);
    }
    return data;
  }

  let toastTimer = null;
  function notify(message, type = 'success') {
    const toast = $('#toast');
    const icon = $('#toast-icon');
    const text = $('#toast-message');
    text.textContent = String(message).slice(0, 240);
    icon.textContent = type === 'error' ? '!' : '✓';
    icon.style.color = type === 'error' ? '#fb7185' : '#34f5c5';
    icon.style.background = type === 'error' ? 'rgba(251,113,133,.12)' : 'rgba(52,245,197,.12)';
    toast.classList.add('show');
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => toast.classList.remove('show'), 3800);
  }

  async function runEngine(button, resultEl, request, renderer) {
    const original = button.innerHTML;
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    button.innerHTML = 'Running…';
    try {
      const result = await request();
      renderer(result);
      notify(result && result.passed ? 'Test completed successfully.' : 'Test finished with findings.', result && result.passed ? 'success' : 'error');
    } catch (error) {
      resultEl.innerHTML = errorCard(error.message || error);
      notify(error.message || 'Request failed', 'error');
    } finally {
      button.disabled = false;
      button.removeAttribute('aria-busy');
      button.innerHTML = original;
      refreshDashboard();
    }
  }

  /* --------------------------------------------------------------------- */
  /* Module navigation                                                      */
  /* --------------------------------------------------------------------- */

  function switchModule(name) {
    if (!MODULES[name]) return;
    state.module = name;
    $$('.nav-item[data-module]').forEach((button) => {
      button.classList.toggle('active', button.dataset.module === name);
    });
    $$('[data-panel]').forEach((panel) => {
      panel.classList.toggle('hidden', panel.dataset.panel !== name);
    });
    const meta = MODULES[name];
    $('#module-kicker').textContent = meta.kicker;
    $('#module-title').textContent = meta.title;
    $('#module-description').textContent = meta.description;
    window.setTimeout(() => {
      Object.values(state.editors).forEach((editor) => {
        try { editor.layout(); } catch { /* noop */ }
      });
      if (state.loadChart) state.loadChart.resize();
    }, 40);
  }

  /* --------------------------------------------------------------------- */
  /* Monaco editors (with textarea fallback)                                */
  /* --------------------------------------------------------------------- */

  function fallbackEditor(id, initial) {
    const container = document.getElementById(id);
    container.innerHTML = '';
    const textarea = document.createElement('textarea');
    textarea.className = 'code-block';
    textarea.style.cssText = 'height:100%;width:100%;border:0;border-radius:0;resize:none;padding:14px;background:#070b14;';
    textarea.spellcheck = false;
    textarea.value = initial;
    container.appendChild(textarea);
    return {
      getValue: () => textarea.value,
      setValue: (value) => { textarea.value = value; },
      layout: () => {},
    };
  }

  function initEditors() {
    const defaults = {
      unitCode: SAMPLE_UNIT_CODE,
      unitTests: SAMPLE_UNIT_TESTS,
      integration: SAMPLE_INTEGRATION,
    };

    if (!window.require) {
      state.editors.unitCode = fallbackEditor('unit-code', defaults.unitCode);
      state.editors.unitTests = fallbackEditor('unit-tests', defaults.unitTests);
      state.editors.integration = fallbackEditor('integration-editor', defaults.integration);
      return;
    }

    window.require.config({ paths: { vs: 'https://cdn.jsdelivr.net/npm/monaco-editor@0.52.0/min/vs' } });
    window.require(['vs/editor/editor.main'], () => {
      window.monaco.editor.defineTheme('testpulse', {
        base: 'vs-dark',
        inherit: true,
        rules: [
          { token: 'comment', foreground: '52657f', fontStyle: 'italic' },
          { token: 'keyword', foreground: '8b5cf6' },
          { token: 'string', foreground: '34f5c5' },
          { token: 'number', foreground: 'fbbf24' },
          { token: 'type', foreground: '7dd3fc' },
        ],
        colors: {
          'editor.background': '#070b14',
          'editor.foreground': '#b7c6da',
          'editorLineNumber.foreground': '#293a54',
          'editorLineNumber.activeForeground': '#5eead4',
          'editor.selectionBackground': '#143b3b',
          'editor.inactiveSelectionBackground': '#10282a',
          'editorCursor.foreground': '#34f5c5',
          'editor.lineHighlightBackground': '#0b1322',
          'editorIndentGuide.background1': '#132138',
          'editorWidget.background': '#0a1220',
          'editorSuggestWidget.background': '#0a1220',
          'editorSuggestWidget.selectedBackground': '#143b3b',
        },
      });

      const common = {
        theme: 'testpulse',
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 12,
        lineHeight: 20,
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
        automaticLayout: true,
        padding: { top: 12, bottom: 12 },
        renderLineHighlight: 'all',
        roundedSelection: true,
        smoothScrolling: true,
        tabSize: 4,
      };

      state.editors.unitCode = window.monaco.editor.create($('#unit-code'), {
        ...common, value: defaults.unitCode, language: 'python',
      });
      state.editors.unitTests = window.monaco.editor.create($('#unit-tests'), {
        ...common, value: defaults.unitTests, language: 'python',
      });
      state.editors.integration = window.monaco.editor.create($('#integration-editor'), {
        ...common, value: defaults.integration, language: 'json',
      });
      state.monacoReady = true;
    }, () => {
      state.editors.unitCode = fallbackEditor('unit-code', defaults.unitCode);
      state.editors.unitTests = fallbackEditor('unit-tests', defaults.unitTests);
      state.editors.integration = fallbackEditor('integration-editor', defaults.integration);
    });
  }

  function getEditor(key) {
    return state.editors[key] || null;
  }

  function editorValue(key, fallback = '') {
    const editor = getEditor(key);
    return editor ? editor.getValue() : fallback;
  }

  function setEditorValue(key, value) {
    const editor = getEditor(key);
    if (editor) editor.setValue(value);
  }

  /* --------------------------------------------------------------------- */
  /* Result renderers                                                       */
  /* --------------------------------------------------------------------- */

  function renderUnit(result) {
    const counts = result.counts || {};
    const output = result.output || result.error || '(no stdout)';
    const info = [
      result.timed_out ? '<span class="badge badge-warn">● TIMEOUT</span>' : '',
      result.network === 'disabled' ? '<span class="badge badge-info">NETWORK OFF</span>' : '',
      result.image ? `<span class="font-mono text-[9px] text-slate-600">${esc(result.image)}</span>` : '',
    ].join(' ');
    $('#unit-result').innerHTML = `
      ${resultBanner(result)}
      <div class="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-5">
        ${metric('Passed', counts.passed ?? 0, 'text-pulse')}
        ${metric('Failed', counts.failed ?? 0, 'text-rose-300')}
        ${metric('Errors', counts.errors ?? 0, 'text-rose-300')}
        ${metric('Skipped', counts.skipped ?? 0, 'text-slate-400')}
        ${metric('Exit code', result.exit_code ?? '—', result.exit_code === 0 ? 'text-pulse' : 'text-rose-300')}
      </div>
      <div class="mt-3 glass rounded-xl p-4">
        <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div class="flex items-center gap-2"><span class="h-1 w-1 rounded-full bg-pulse"></span><span class="font-mono text-[10px] uppercase tracking-[0.15em] text-slate-400">pytest output</span></div>
          <div class="flex flex-wrap items-center gap-2">${info}</div>
        </div>
        <pre class="code-block max-h-[420px]">${esc(output)}</pre>
      </div>`;
  }

  function renderIntegration(result) {
    const steps = Array.isArray(result.steps) ? result.steps : [];
    const timeline = steps.map((step) => {
      const passed = Boolean(step.passed);
      const assertions = Array.isArray(step.assertions) ? step.assertions : [];
      const assertionHtml = assertions.map((assertion) => `
        <div class="flex flex-wrap items-center gap-2 font-mono text-[10px]">
          <span class="${assertion.passed ? 'text-pulse' : 'text-rose-300'}">${assertion.passed ? '✓' : '✕'}</span>
          <span class="text-slate-500">${esc(assertion.source)}</span>
          <span class="text-slate-600">${esc(assertion.op)}</span>
          <span class="text-slate-400">${esc(formatValue(assertion.expected))}</span>
          <span class="text-slate-700">→</span>
          <span class="${assertion.passed ? 'text-slate-300' : 'text-rose-300'}">${esc(formatValue(assertion.actual))}</span>
        </div>`).join('');
      const extracted = step.extracted_masked || step.extracted || {};
      const extractedKeys = Object.keys(extracted);
      const extractedHtml = extractedKeys.length
        ? `<div class="mt-2 flex flex-wrap gap-1.5">${extractedKeys.map((key) => `<span class="rounded border border-violet/20 bg-violet/[0.06] px-2 py-1 font-mono text-[9px] text-violet-200/80">${esc(key)} = ${esc(formatValue(extracted[key]))}</span>`).join('')}</div>`
        : '';
      return `<div class="timeline-step ${passed ? 'pass' : 'fail'}">
        <span class="timeline-dot"></span>
        <div class="flex flex-wrap items-center gap-2">
          <span class="font-mono text-[10px] text-slate-500">STEP ${step.index + 1}</span>
          <span class="badge ${passed ? 'badge-pass' : 'badge-fail'}">${passed ? 'PASS' : 'FAIL'}</span>
          <span class="text-[12px] font-medium text-slate-200">${esc(step.name)}</span>
          <span class="font-mono text-[9px] text-slate-600">${formatMs(step.duration_ms)}</span>
        </div>
        <div class="mt-2 flex flex-wrap items-center gap-2 font-mono text-[10px]">
          <span class="rounded bg-white/[0.035] px-1.5 py-0.5 text-pulse/80">${esc(step.method)}</span>
          <span class="break-all text-slate-500">${esc(step.url || '—')}</span>
          <span class="${step.status && step.status < 400 ? 'text-slate-300' : 'text-rose-300'}">HTTP ${esc(step.status ?? '—')}</span>
        </div>
        ${step.error ? `<div class="mt-2 rounded border border-rose-400/15 bg-rose-400/[0.04] px-2.5 py-2 font-mono text-[10px] text-rose-200/80">${esc(step.error)}</div>` : ''}
        ${assertionHtml ? `<div class="mt-2 space-y-1.5 rounded-lg border border-white/[0.04] bg-black/20 p-2.5">${assertionHtml}</div>` : ''}
        ${extractedHtml}
      </div>`;
    }).join('');

    const vars = result.variables && Object.keys(result.variables).length
      ? `<div class="mt-3 rounded-xl border border-violet/15 bg-violet/[0.03] p-3">
          <div class="mb-2 font-mono text-[9px] uppercase tracking-wider text-violet-300/70">Extracted variables (masked)</div>
          <div class="flex flex-wrap gap-2">${Object.entries(result.variables).map(([key, value]) => `<span class="rounded border border-violet/20 bg-violet/[0.06] px-2 py-1 font-mono text-[9px] text-violet-200/80">${esc(key)} = ${esc(formatValue(value))}</span>`).join('')}</div>
        </div>`
      : '';

    $('#integration-result').innerHTML = `
      ${resultBanner(result)}
      <div class="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        ${metric('Total steps', result.total_steps ?? steps.length)}
        ${metric('Executed', result.executed_steps ?? steps.length, 'text-pulse')}
        ${metric('Data flow', result.data_flow_verified ? 'VERIFIED' : 'BROKEN', result.data_flow_verified ? 'text-pulse' : 'text-rose-300')}
        ${metric('Duration', formatMs(result.duration_ms))}
      </div>
      <div class="mt-3 glass rounded-xl p-4">
        ${sectionTitle('Stateful chain timeline', `${steps.length} executed`)}
        ${timeline || '<div class="text-[12px] text-slate-500">No steps executed.</div>'}
        ${vars}
      </div>`;
  }

  function renderE2E(result) {
    const checks = Array.isArray(result.checks) ? result.checks : [];
    const checksHtml = checks.map((check) => `
      <div class="flex items-start gap-3 rounded-lg border border-white/[0.045] bg-black/15 px-3 py-2.5">
        <span class="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full ${check.passed ? 'bg-pulse/10 text-pulse' : 'bg-rose-400/10 text-rose-300'}">${check.passed ? '✓' : '✕'}</span>
        <div class="min-w-0 flex-1">
          <div class="text-[12px] text-slate-200">${esc(check.name)}</div>
          <div class="mt-1 break-words font-mono text-[10px] text-slate-500">expected: ${esc(formatValue(check.expected))} <span class="text-slate-700">→</span> actual: ${esc(formatValue(check.actual))}</div>
          ${check.error ? `<div class="mt-1 font-mono text-[10px] text-rose-300/80">${esc(check.error)}</div>` : ''}
        </div>
      </div>`).join('');

    const consoleErrors = [
      ...(result.console_errors || []).map((item) => `console: ${item}`),
      ...(result.page_errors || []).map((item) => `pageerror: ${item}`),
    ];
    const errorsHtml = consoleErrors.length
      ? `<div class="mt-3 rounded-xl border border-amber-400/15 bg-amber-400/[0.035] p-3">
          <div class="mb-2 font-mono text-[9px] uppercase tracking-wider text-amber-300/70">Browser console / page errors</div>
          <div class="space-y-1.5">${consoleErrors.slice(0, 12).map((item) => `<div class="break-words font-mono text-[10px] text-amber-100/70">${esc(item)}</div>`).join('')}</div>
        </div>`
      : '';

    const shot = result.screenshot_url
      ? `<div class="mt-3 glass rounded-xl p-3">
          <div class="mb-2 flex items-center justify-between">
            <div class="font-mono text-[9px] uppercase tracking-wider text-slate-500">Captured viewport</div>
            <a href="${esc(result.screenshot_url)}" target="_blank" rel="noopener" class="btn-ghost !py-1 !text-[9px]">Open full size ↗</a>
          </div>
          <a href="${esc(result.screenshot_url)}" target="_blank" rel="noopener">
            <img src="${esc(result.screenshot_url)}" alt="E2E screenshot" loading="lazy" class="max-h-[520px] w-full rounded-lg border border-white/[0.05] object-contain bg-black/30" />
          </a>
        </div>`
      : '';

    $('#e2e-result').innerHTML = `
      ${resultBanner(result)}
      <div class="mt-3 grid grid-cols-2 gap-2 lg:grid-cols-5">
        ${metric('Checks', `${result.checks_passed ?? 0}/${result.checks_total ?? checks.length}`, result.passed ? 'text-pulse' : 'text-rose-300')}
        ${metric('HTTP status', result.status_code ?? '—')}
        ${metric('Final URL', result.final_url ? new URL(result.final_url).pathname || '/' : '—', 'text-slate-300', result.final_url || '')}
        ${metric('Title', result.title || '—')}
        ${metric('Duration', formatMs(result.duration_ms))}
      </div>
      <div class="mt-3 glass rounded-xl p-4">
        ${sectionTitle('Assertion checks', `${result.viewport ? `${result.viewport.width}×${result.viewport.height}` : 'browser'}`)}
        <div class="space-y-2">${checksHtml || '<div class="text-[12px] text-slate-500">No checks executed.</div>'}</div>
        ${errorsHtml}
      </div>
      ${shot}`;
  }

  function renderLoad(result) {
    const latency = result.latency || {};
    const statuses = result.status_distribution || {};
    const statusHtml = Object.entries(statuses).length
      ? Object.entries(statuses).map(([code, count]) => {
          const numeric = Number(code);
          const cls = numeric >= 500 ? 'badge-fail' : numeric >= 400 ? 'badge-warn' : 'badge-pass';
          return `<span class="badge ${cls}">HTTP ${esc(code)} · ${esc(count)}</span>`;
        }).join('')
      : '<span class="text-[10px] text-slate-600">No responses</span>';

    const errorHtml = (result.errors_sample || []).length
      ? `<div class="mt-3 rounded-xl border border-rose-400/15 bg-rose-400/[0.035] p-3">
          <div class="mb-2 font-mono text-[9px] uppercase tracking-wider text-rose-300/70">Sampled errors</div>
          ${result.errors_sample.slice(0, 8).map((item) => `<div class="break-words font-mono text-[10px] text-rose-100/65">${esc(item)}</div>`).join('')}
        </div>`
      : '';

    $('#load-result').innerHTML = `
      ${resultBanner(result)}
      <div class="mt-3 grid grid-cols-2 gap-2 lg:grid-cols-6">
        ${metric('RPS', Number(result.rps ?? 0).toFixed(1), 'text-pulse')}
        ${metric('Success rate', `${(Number(result.success_rate ?? 0) * 100).toFixed(1)}%`, Number(result.success_rate) >= Number(result.min_success_rate || 0) ? 'text-pulse' : 'text-rose-300')}
        ${metric('Average latency', `${Number(latency.avg_ms ?? 0).toFixed(1)} ms`)}
        ${metric('p95 latency', `${Number(latency.p95_ms ?? 0).toFixed(1)} ms`)}
        ${metric('Max latency', `${Number(latency.max_ms ?? 0).toFixed(1)} ms`)}
        ${metric('Completed', `${result.completed_requests ?? 0}/${result.total_requests ?? 0}`)}
      </div>
      <div class="mt-3 grid gap-3 xl:grid-cols-[1.4fr_.6fr]">
        <div class="glass rounded-xl p-4">
          ${sectionTitle('Throughput and latency timeline', 'per-second buckets')}
          <div class="h-[280px]"><canvas id="load-chart"></canvas></div>
        </div>
        <div class="glass rounded-xl p-4">
          ${sectionTitle('Response distribution', `${result.concurrency} concurrent`)}
          <div class="flex flex-wrap gap-2">${statusHtml}</div>
          <div class="mt-4 grid grid-cols-2 gap-2">
            ${metric('p50', `${Number(latency.p50_ms ?? 0).toFixed(1)} ms`)}
            ${metric('p90', `${Number(latency.p90_ms ?? 0).toFixed(1)} ms`)}
            ${metric('p99', `${Number(latency.p99_ms ?? 0).toFixed(1)} ms`)}
            ${metric('Min', `${Number(latency.min_ms ?? 0).toFixed(1)} ms`)}
          </div>
          <div class="mt-3 font-mono text-[9px] uppercase tracking-wider text-slate-600">${esc(result.method || 'GET')} · ${esc(result.elapsed_seconds ?? '—')}s elapsed</div>
        </div>
      </div>
      ${errorHtml}`;

    drawLoadChart(result.timeline || []);
  }

  function drawLoadChart(timeline) {
    const canvas = document.getElementById('load-chart');
    if (!canvas) return;
    if (state.loadChart) {
      state.loadChart.destroy();
      state.loadChart = null;
    }
    if (!window.Chart) {
      canvas.parentElement.innerHTML = '<div class="flex h-full items-center justify-center text-[11px] text-slate-600">Chart.js unavailable</div>';
      return;
    }
    const labels = timeline.map((item) => `${item.second}s`);
    state.loadChart = new window.Chart(canvas, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: 'RPS',
            data: timeline.map((item) => item.rps),
            borderColor: '#34f5c5',
            backgroundColor: 'rgba(52,245,197,.09)',
            borderWidth: 2,
            pointRadius: 2,
            pointBackgroundColor: '#34f5c5',
            tension: 0.32,
            fill: true,
            yAxisID: 'y',
          },
          {
            label: 'Avg latency (ms)',
            data: timeline.map((item) => item.avg_latency_ms),
            borderColor: '#8b5cf6',
            backgroundColor: 'rgba(139,92,246,.04)',
            borderWidth: 1.5,
            pointRadius: 1.5,
            borderDash: [4, 3],
            tension: 0.32,
            yAxisID: 'y1',
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: {
            labels: { color: '#7d90ad', font: { family: 'JetBrains Mono', size: 9 }, boxWidth: 14, usePointStyle: true },
          },
          tooltip: {
            backgroundColor: '#0a1220',
            borderColor: '#243550',
            borderWidth: 1,
            titleFont: { family: 'JetBrains Mono', size: 10 },
            bodyFont: { family: 'JetBrains Mono', size: 10 },
            titleColor: '#d7e2f3',
            bodyColor: '#94a8c4',
          },
        },
        scales: {
          x: { ticks: { color: '#52657f', font: { family: 'JetBrains Mono', size: 9 }, maxTicksLimit: 12 }, grid: { color: 'rgba(74,99,137,.08)' } },
          y: { position: 'left', beginAtZero: true, ticks: { color: '#52657f', font: { family: 'JetBrains Mono', size: 9 } }, grid: { color: 'rgba(74,99,137,.08)' }, title: { display: true, text: 'req/s', color: '#52657f', font: { size: 9 } } },
          y1: { position: 'right', beginAtZero: true, ticks: { color: '#6d5da8', font: { family: 'JetBrains Mono', size: 9 } }, grid: { drawOnChartArea: false }, title: { display: true, text: 'ms', color: '#6d5da8', font: { size: 9 } } },
        },
      },
    });
  }

  function renderSecurity(result) {
    const score = Math.max(0, Math.min(100, Number(result.score ?? 0)));
    const color = score >= 80 ? '#34f5c5' : score >= 60 ? '#fbbf24' : '#fb7185';
    const severity = result.severity_counts || {};
    const findings = Array.isArray(result.findings) ? result.findings : [];
    const findingsHtml = findings.length
      ? `<div class="space-y-2">${findings.map((finding) => `
          <div class="finding ${esc(finding.severity || 'info')}">
            <div class="flex flex-wrap items-center gap-2">
              ${severityBadge(finding.severity)}
              <span class="text-[12px] font-medium text-slate-200">${esc(finding.title)}</span>
              ${finding.weight ? `<span class="ml-auto font-mono text-[9px] text-rose-300/60">-${esc(finding.weight)} pts</span>` : ''}
            </div>
            <div class="mt-1.5 text-[11px] leading-relaxed text-slate-400">${esc(finding.detail)}</div>
            ${finding.evidence ? `<div class="mt-2 break-all rounded bg-black/25 px-2 py-1.5 font-mono text-[9px] text-amber-100/60">${esc(finding.evidence)}</div>` : ''}
            <div class="mt-1.5 text-[10px] text-slate-600">↳ ${esc(finding.recommendation)}</div>
          </div>`).join('')}</div>`
      : '<div class="rounded-lg border border-pulse/15 bg-pulse/[0.035] px-3 py-3 text-[11px] text-pulse/80">No findings. The tested surface passed the baseline checks.</div>';

    const headers = Array.isArray(result.header_checks) ? result.header_checks : [];
    const headerRows = headers.map((header) => `
      <tr>
        <td class="font-mono text-[10px] text-slate-300">${esc(header.header)}</td>
        <td>${header.present === null ? '<span class="badge badge-info">N/A</span>' : header.present ? '<span class="badge badge-pass">PRESENT</span>' : '<span class="badge badge-fail">MISSING</span>'}</td>
        <td class="max-w-[280px] break-all font-mono text-[9px] text-slate-600">${esc(header.value || '—')}</td>
      </tr>`).join('');

    const probes = Array.isArray(result.probes) ? result.probes : [];
    const probeRows = probes.map((probe) => `
      <tr>
        <td><span class="badge badge-info">${esc(String(probe.type || '').toUpperCase())}</span></td>
        <td class="text-[11px] text-slate-400">${esc(probe.label)}</td>
        <td class="max-w-[210px] break-all font-mono text-[9px] text-slate-600">${esc(probe.payload)}</td>
        <td class="font-mono text-[10px]">${esc(probe.status ?? '—')}</td>
        <td>${probe.finding ? '<span class="badge badge-fail">FLAGGED</span>' : '<span class="badge badge-pass">CLEAN</span>'}</td>
      </tr>`).join('');

    $('#sec-result').innerHTML = `
      ${resultBanner(result)}
      <div class="mt-3 grid gap-3 lg:grid-cols-[220px_1fr]">
        <div class="glass flex flex-col items-center justify-center rounded-xl p-5">
          <div class="score-ring" style="--score:${score};--score-color:${color}">
            <div>
              <div class="font-mono text-[30px] font-semibold text-white">${score}</div>
              <div class="font-mono text-[8px] uppercase tracking-widest text-slate-500">/ 100 · ${esc(result.grade || '—')}</div>
            </div>
          </div>
          <div class="mt-4 flex flex-wrap justify-center gap-1.5">
            ${severity.critical ? `<span class="badge badge-fail">CRIT ${esc(severity.critical)}</span>` : ''}
            ${severity.high ? `<span class="badge badge-fail">HIGH ${esc(severity.high)}</span>` : ''}
            ${severity.medium ? `<span class="badge badge-warn">MED ${esc(severity.medium)}</span>` : ''}
            ${severity.low ? `<span class="badge badge-info">LOW ${esc(severity.low)}</span>` : ''}
          </div>
        </div>
        <div class="glass rounded-xl p-4">
          ${sectionTitle('Security header audit', result.url || '')}
          <div class="max-h-[280px] overflow-auto">
            <table class="data-table"><thead><tr><th>Header</th><th>State</th><th>Value</th></tr></thead><tbody>${headerRows || '<tr><td colspan="3" class="text-slate-600">No header data</td></tr>'}</tbody></table>
          </div>
        </div>
      </div>
      <div class="mt-3 grid gap-3 xl:grid-cols-2">
        <div class="glass rounded-xl p-4">
          ${sectionTitle('Findings', `${findings.length} observed`)}
          ${findingsHtml}
        </div>
        <div class="glass rounded-xl p-4">
          ${sectionTitle('Benign reflection probes', `${probes.length} payloads`)}
          <div class="overflow-auto">
            <table class="data-table"><thead><tr><th>Type</th><th>Probe</th><th>Payload</th><th>HTTP</th><th>Result</th></tr></thead><tbody>${probeRows || '<tr><td colspan="5" class="text-slate-600">No probes executed</td></tr>'}</tbody></table>
          </div>
        </div>
      </div>`;
  }

  function renderVisual(result) {
    const first = Boolean(result.first_run || result.baseline_created);
    const images = [
      { title: 'Baseline', url: result.baseline_url, subtitle: 'reference image' },
      { title: 'Current', url: result.current_url, subtitle: 'latest capture' },
      { title: 'Diff', url: result.diff_url, subtitle: first ? 'created on next run' : 'red = changed pixels' },
    ];
    const cacheKey = Date.now();
    const imageHtml = images.map((image) => `
      <div class="img-card">
        <div class="flex items-center justify-between border-b border-white/[0.05] px-3 py-2">
          <div>
            <div class="font-mono text-[9px] uppercase tracking-wider text-slate-400">${esc(image.title)}</div>
            <div class="mt-0.5 text-[9px] text-slate-600">${esc(image.subtitle)}</div>
          </div>
          ${image.url ? `<a href="${esc(image.url)}" target="_blank" rel="noopener" class="text-[10px] text-slate-500 hover:text-pulse">↗</a>` : ''}
        </div>
        ${image.url
          ? `<a href="${esc(image.url)}" target="_blank" rel="noopener"><img src="${esc(image.url)}?v=${cacheKey}" alt="${esc(image.title)}" loading="lazy" /></a>`
          : `<div class="flex h-[240px] items-center justify-center font-mono text-[9px] uppercase tracking-wider text-slate-700">No diff yet</div>`}
      </div>`).join('');

    const sizeWarning = result.size_changed
      ? `<div class="mt-3 rounded-lg border border-amber-400/20 bg-amber-400/[0.04] px-3 py-2 font-mono text-[10px] text-amber-200/80">Page dimensions changed: ${esc(result.baseline_dimensions?.width)}×${esc(result.baseline_dimensions?.height)} → ${esc(result.current_dimensions?.width)}×${esc(result.current_dimensions?.height)}</div>`
      : '';

    $('#visual-result').innerHTML = `
      ${resultBanner(result)}
      <div class="mt-3 grid grid-cols-2 gap-2 lg:grid-cols-5">
        ${metric('Diff', `${Number(result.diff_percent ?? 0).toFixed(3)}%`, Number(result.diff_percent ?? 0) <= Number(result.threshold_percent ?? 0) ? 'text-pulse' : 'text-rose-300')}
        ${metric('Changed pixels', Number(result.changed_pixels ?? 0).toLocaleString())}
        ${metric('Threshold', `${Number(result.threshold_percent ?? 0).toFixed(2)}%`)}
        ${metric('Pixel tolerance', result.pixel_threshold ?? '—')}
        ${metric('Viewport', `${result.dimensions?.width ?? '—'}×${result.dimensions?.height ?? '—'}`)}
      </div>
      ${first ? `<div class="mt-3 rounded-lg border border-pulse/20 bg-pulse/[0.04] px-3 py-2 font-mono text-[10px] text-pulse/80">Baseline ${result.baseline_updated ? 'updated' : 'created'}. 下一次以相同 URL / Viewport 執行時，才會產生差異比對。</div>` : ''}
      ${sizeWarning}
      <div class="mt-3 grid gap-3 lg:grid-cols-3">${imageHtml}</div>`;
  }

  /* --------------------------------------------------------------------- */
  /* History, telemetry, health                                             */
  /* --------------------------------------------------------------------- */

  async function loadStats() {
    try {
      const stats = await api('/api/stats');
      $('#stat-total').textContent = stats.total_runs ?? 0;
      $('#stat-pass-rate').textContent = `${Number(stats.pass_rate ?? 0).toFixed(1)}%`;
      $('#stat-avg').textContent = formatMs(stats.avg_duration_ms);
      $('#sidebar-runs').textContent = stats.total_runs ?? 0;
      $('#sidebar-rate').textContent = `${Number(stats.pass_rate ?? 0).toFixed(0)}%`;
    } catch {
      /* Dashboard telemetry is non-critical. */
    }
  }

  async function loadHistory() {
    const body = $('#history-body');
    try {
      const data = await api('/api/history?limit=30');
      state.history = data.items || [];
      $('#history-count').textContent = state.history.length;
      if (!state.history.length) {
        body.innerHTML = '<tr><td colspan="7" class="py-8 text-center font-mono text-[10px] uppercase tracking-wider text-slate-600">No executions yet</td></tr>';
        return;
      }
      body.innerHTML = state.history.map((item) => `
        <tr>
          <td>${statusBadge(item.status)}</td>
          <td><span class="font-mono text-[10px] text-slate-300">${esc(MODULE_LABELS[item.test_type] || item.test_type)}</span></td>
          <td class="max-w-[430px]">
            <div class="truncate font-mono text-[9px] text-slate-600" title="${esc(item.target)}">${esc(item.target || '—')}</div>
            <div class="mt-1 text-[11px] leading-snug text-slate-400">${esc(item.summary || '—')}</div>
          </td>
          <td class="font-mono text-[10px]">${item.score === null || item.score === undefined ? '—' : esc(Math.round(item.score))}</td>
          <td class="font-mono text-[10px]">${formatMs(item.duration_ms)}</td>
          <td class="whitespace-nowrap font-mono text-[9px] text-slate-600">${esc(formatDate(item.created_at))}</td>
          <td><button class="history-detail btn-ghost !px-2 !py-1 !text-[9px]" data-id="${esc(item.id)}">Detail</button></td>
        </tr>`).join('');
    } catch (error) {
      body.innerHTML = `<tr><td colspan="7" class="py-8 text-center font-mono text-[10px] text-rose-300/70">${esc(error.message)}</td></tr>`;
    }
  }

  async function showHistoryDetail(id) {
    const modal = $('#detail-modal');
    const pre = $('#detail-json');
    pre.textContent = 'Loading…';
    $('#detail-modal-title').textContent = `Execution #${id}`;
    modal.classList.remove('hidden');
    modal.classList.add('flex');
    try {
      const detail = await api(`/api/history/${id}`);
      pre.textContent = JSON.stringify(detail, null, 2);
    } catch (error) {
      pre.textContent = `Failed to load detail: ${error.message}`;
    }
  }

  function closeDetail() {
    const modal = $('#detail-modal');
    modal.classList.add('hidden');
    modal.classList.remove('flex');
  }

  async function refreshDashboard() {
    await Promise.all([loadStats(), loadHistory()]);
  }

  async function checkHealth() {
    const dot = $('#api-dot');
    const label = $('#api-status');
    try {
      const health = await api('/api/health');
      dot.className = 'h-1.5 w-1.5 rounded-full bg-pulse shadow-[0_0_8px_#34f5c5]';
      label.textContent = 'Online';
      label.className = 'font-mono text-[8px] uppercase tracking-wider text-pulse/80';
      return health;
    } catch {
      dot.className = 'h-1.5 w-1.5 rounded-full bg-rose-400';
      label.textContent = 'Offline';
      label.className = 'font-mono text-[8px] uppercase tracking-wider text-rose-300';
      return null;
    }
  }

  /* --------------------------------------------------------------------- */
  /* Event wiring                                                           */
  /* --------------------------------------------------------------------- */

  function numberValue(id, fallback) {
    const value = Number(document.getElementById(id).value);
    return Number.isFinite(value) ? value : fallback;
  }

  function nullableText(id) {
    const value = document.getElementById(id).value.trim();
    return value ? value : null;
  }

  function wireEvents() {
    $$('.nav-item[data-module]').forEach((button) => {
      button.addEventListener('click', () => switchModule(button.dataset.module));
    });

    $('#unit-example').addEventListener('click', () => {
      setEditorValue('unitCode', SAMPLE_UNIT_CODE);
      setEditorValue('unitTests', SAMPLE_UNIT_TESTS);
      notify('Loaded the pytest example.', 'success');
    });

    $('#unit-run').addEventListener('click', () => {
      const code = editorValue('unitCode', SAMPLE_UNIT_CODE);
      const tests = editorValue('unitTests', SAMPLE_UNIT_TESTS);
      runEngine($('#unit-run'), $('#unit-result'), () => api('/api/tests/unit', {
        method: 'POST',
        body: { code, tests, timeout_seconds: numberValue('unit-timeout', 5) },
      }), renderUnit);
    });

    $('#integration-example').addEventListener('click', () => {
      setEditorValue('integration', SAMPLE_INTEGRATION);
      notify('Loaded the stateful API-chain example.', 'success');
    });

    $('#integration-run').addEventListener('click', () => {
      let steps;
      try {
        steps = JSON.parse(editorValue('integration', SAMPLE_INTEGRATION));
      } catch (error) {
        $('#integration-result').innerHTML = errorCard(`Invalid JSON: ${error.message}`);
        notify('The chain editor contains invalid JSON.', 'error');
        return;
      }
      if (!Array.isArray(steps) || !steps.length) {
        $('#integration-result').innerHTML = errorCard('The chain must be a non-empty JSON array.');
        return;
      }
      runEngine($('#integration-run'), $('#integration-result'), () => api('/api/tests/integration', {
        method: 'POST',
        body: {
          steps,
          stop_on_failure: $('#integration-stop').checked,
          default_timeout_seconds: numberValue('integration-timeout', 15),
        },
      }), renderIntegration);
    });

    $('#e2e-run').addEventListener('click', () => {
      runEngine($('#e2e-run'), $('#e2e-result'), () => api('/api/tests/e2e', {
        method: 'POST',
        body: {
          url: $('#e2e-url').value.trim(),
          expected_title: nullableText('e2e-title'),
          title_match: $('#e2e-title-match').value,
          selector: nullableText('e2e-selector'),
          click_selector: nullableText('e2e-click'),
          expected_text: nullableText('e2e-text'),
          text_selector: nullableText('e2e-text-selector'),
          wait_for_selector: nullableText('e2e-wait-selector'),
          expected_url_contains: nullableText('e2e-url-contains'),
          wait_after_click_ms: 300,
          timeout_ms: numberValue('e2e-timeout', 15000),
          viewport_width: numberValue('e2e-viewport-width', 1280),
          viewport_height: numberValue('e2e-viewport-height', 720),
          wait_until: 'domcontentloaded',
          full_page_screenshot: $('#e2e-full-page').checked,
          capture_screenshot: $('#e2e-screenshot').checked,
          ignore_https_errors: false,
        },
      }), renderE2E);
    });

    $('#load-run').addEventListener('click', () => {
      runEngine($('#load-run'), $('#load-result'), () => api('/api/tests/load', {
        method: 'POST',
        body: {
          url: $('#load-url').value.trim(),
          method: $('#load-method').value,
          concurrency: numberValue('load-concurrency', 20),
          total_requests: numberValue('load-total', 100),
          timeout_seconds: numberValue('load-timeout', 10),
          min_success_rate: numberValue('load-min-success', 0.95),
        },
      }), renderLoad);
    });

    $('#sec-run').addEventListener('click', () => {
      runEngine($('#sec-run'), $('#sec-result'), () => api('/api/tests/security', {
        method: 'POST',
        body: {
          url: $('#sec-url').value.trim(),
          timeout_seconds: numberValue('sec-timeout', 10),
        },
      }), renderSecurity);
    });

    $('#visual-run').addEventListener('click', () => {
      const update = $('#visual-update').checked;
      if (update && !window.confirm('Replace the saved baseline with a new screenshot?')) return;
      runEngine($('#visual-run'), $('#visual-result'), () => api('/api/tests/visual', {
        method: 'POST',
        body: {
          url: $('#visual-url').value.trim(),
          viewport_width: numberValue('visual-width', 1280),
          viewport_height: numberValue('visual-height', 720),
          full_page: $('#visual-full').checked,
          update_baseline: update,
          diff_threshold_percent: numberValue('visual-threshold', 0.5),
          pixel_threshold: numberValue('visual-pixel', 20),
          wait_seconds: numberValue('visual-wait', 0.5),
          wait_until: 'networkidle',
          fail_on_size_change: $('#visual-fail-size').checked,
          ignore_https_errors: false,
        },
      }), renderVisual);
    });

    $('#refresh-history').addEventListener('click', () => {
      refreshDashboard();
      notify('History refreshed.', 'success');
    });

    $('#history-body').addEventListener('click', (event) => {
      const button = event.target.closest('.history-detail');
      if (button) showHistoryDetail(button.dataset.id);
    });

    $('#detail-close').addEventListener('click', closeDetail);
    $('#detail-backdrop').addEventListener('click', closeDetail);
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') closeDetail();
    });
  }

  function boot() {
    initEditors();
    wireEvents();
    switchModule('unit');
    checkHealth();
    refreshDashboard();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
