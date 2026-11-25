#!/usr/bin/env python3
"""Generates both:
  1. `docs/index.html`    — English PoC Architecture, 2-Tier Token Diet & Outcome Verification Portal
  2. `docs/index_ko.html` — Korean Verification Portal (all technical nouns in original English)
from `benchmarks/scenario_benchmark_results.json`, featuring:
  - Live `As-Is` vs `To-Be` A/B comparisons across Scenarios S1–S5
  - Real `Vertex AI usage_metadata` (`prompt_token_count`) measurements
  - Interactive 2-Tier + `BQCA 90% Cached Input ($0.30/1M)` Effective Cost Simulator
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BENCHMARK_JSON = REPO_ROOT / "benchmarks" / "scenario_benchmark_results.json"
OUT_HTML_EN = REPO_ROOT / "docs" / "index.html"
OUT_HTML_KO = REPO_ROOT / "docs" / "index_ko.html"

SHARED_CSS = r"""
    :root {
      --bg: #F8F9FA;
      --surface: #FFFFFF;
      --surface-subtle: #F1F3F4;
      --border: #DADCE0;
      --border-strong: #BDC1C6;
      --text: #202124;
      --text-secondary: #5F6368;
      --blue: #1A73E8;
      --blue-soft: #E8F0FE;
      --green: #137333;
      --green-soft: #E6F4EA;
      --amber: #B06000;
      --amber-soft: #FEF7E0;
      --red: #C5221F;
      --red-soft: #FCE8E6;
      --code-bg: #1E222A;
      --code-text: #E8EAED;
      --radius: 10px;
      --shadow-sm: 0 1px 3px rgba(32,33,36,0.06);
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body {
      max-width: 100%;
      overflow-x: hidden;
      scroll-behavior: smooth;
    }
    body {
      font-family: 'Inter', 'Noto Sans KR', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.68;
      font-size: 15px;
      word-break: keep-all;
      overflow-wrap: break-word;
      -webkit-font-smoothing: antialiased;
    }
    code, pre, .mono {
      font-family: 'Roboto Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
    }
    p code, li code, td code, .kpi-sub .mono, .sub-box .mono, .info-card .mono, .route-trace {
      overflow-wrap: anywhere;
      word-break: break-word;
    }

    .topbar {
      position: sticky;
      top: 0;
      z-index: 100;
      background: rgba(255, 255, 255, 0.96);
      backdrop-filter: blur(8px);
      border-bottom: 1px solid var(--border);
    }
    .topbar-inner {
      max-width: 1240px;
      margin: 0 auto;
      padding: 12px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 10px;
      font-weight: 700;
      font-size: 14.5px;
      color: var(--text);
      text-decoration: none;
      min-width: 0;
    }
    .brand-mark {
      flex-shrink: 0;
      display: inline-flex;
      width: 10px;
      height: 24px;
      border-radius: 3px;
      background: linear-gradient(180deg, #4285F4 0 25%, #EA4335 25% 50%, #FBBC04 50% 75%, #34A853 75% 100%);
    }
    .nav-links { display: flex; gap: 4px; flex-wrap: wrap; }
    .nav-links a {
      text-decoration: none;
      color: var(--text-secondary);
      font-size: 13px;
      font-weight: 600;
      padding: 6px 10px;
      border-radius: 6px;
      transition: background 0.15s, color 0.15s;
    }
    .nav-links a:hover { background: var(--blue-soft); color: var(--blue); }
    .topbar-right { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .gh-link {
      text-decoration: none;
      font-size: 12px;
      font-weight: 700;
      padding: 5px 11px;
      border-radius: 7px;
      border: 1px solid var(--border-strong);
      background: var(--surface);
      color: var(--text);
      transition: border-color 0.15s, color 0.15s;
    }
    .gh-link:hover { border-color: var(--blue); color: var(--blue); }
    .lang-switch {
      display: inline-flex;
      border: 1px solid var(--border);
      border-radius: 7px;
      overflow: hidden;
      background: var(--surface-subtle);
    }
    .lang-switch a {
      text-decoration: none;
      font-size: 12px;
      font-weight: 700;
      padding: 5px 10px;
      color: var(--text-secondary);
    }
    .lang-switch a.active { background: var(--blue); color: #FFFFFF; }
    .lang-switch a:not(.active):hover { color: var(--blue); background: #FFFFFF; }
    .env-pill {
      font-size: 12px;
      font-weight: 600;
      padding: 5px 10px;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: var(--surface-subtle);
      color: var(--text-secondary);
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--green); flex-shrink: 0; }

    .container {
      width: 100%;
      max-width: 1240px;
      margin: 0 auto;
      padding: 32px 24px 72px;
    }
    section { margin-bottom: 52px; scroll-margin-top: 76px; width: 100%; min-width: 0; }
    .eyebrow {
      display: inline-block;
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--blue);
      background: var(--blue-soft);
      padding: 4px 10px;
      border-radius: 4px;
      margin-bottom: 12px;
    }
    h1 { font-size: 29px; line-height: 1.3; font-weight: 700; letter-spacing: -0.02em; margin-bottom: 14px; max-width: 1020px; }
    h2 { font-size: 22px; line-height: 1.34; font-weight: 700; letter-spacing: -0.01em; margin-bottom: 8px; }
    h3 { font-size: 16px; line-height: 1.4; font-weight: 700; margin-bottom: 8px; }
    .lead { font-size: 15.6px; color: var(--text-secondary); max-width: 980px; margin-bottom: 24px; }
    .section-desc { color: var(--text-secondary); max-width: 960px; margin-bottom: 20px; font-size: 14.5px; }

    .hero-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 28px;
      box-shadow: var(--shadow-sm);
      width: 100%;
      min-width: 0;
    }
    .meta-strip {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 24px;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--border);
    }
    .meta-chip {
      font-size: 12.5px;
      background: var(--surface-subtle);
      border: 1px solid var(--border);
      padding: 5px 11px;
      border-radius: 6px;
      max-width: 100%;
      overflow-wrap: anywhere;
    }
    .meta-chip strong { color: var(--text-secondary); font-weight: 600; margin-right: 4px; }

    /* Safe CSS Grids (`minmax(0, 1fr)` + `min-width: 0` on all children) */
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 16px;
      margin-top: 8px;
    }
    @media (max-width: 1080px) { .kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
    @media (max-width: 600px) { .kpi-grid { grid-template-columns: minmax(0, 1fr); } }

    .two-col {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
      margin-bottom: 18px;
    }
    @media (max-width: 960px) { .two-col { grid-template-columns: minmax(0, 1fr); } }

    /* Vertical Stack List (아래로 리스팅하는 구조) for text-heavy / table-heavy content */
    .stack-list {
      display: flex;
      flex-direction: column;
      gap: 16px;
      margin-bottom: 18px;
      width: 100%;
      min-width: 0;
    }

    .kpi-grid > *, .two-col > *, .stack-list > *, .metric-ribbon > *, .calc-grid > * {
      min-width: 0;
      max-width: 100%;
    }

    .kpi-card {
      background: var(--bg);
      border: 1px solid var(--border);
      border-top: 3px solid var(--blue);
      border-radius: 8px;
      padding: 18px;
    }
    .kpi-card.green { border-top-color: var(--green); }
    .kpi-card.amber { border-top-color: var(--amber); }
    .kpi-label { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; color: var(--text-secondary); margin-bottom: 6px; }
    .kpi-value { font-size: 28px; font-weight: 700; color: var(--text); letter-spacing: -0.02em; line-height: 1.15; margin-bottom: 6px; }
    .kpi-card.green .kpi-value { color: var(--green); }
    .kpi-card.blue .kpi-value { color: var(--blue); }
    .kpi-sub { font-size: 12.8px; color: var(--text-secondary); line-height: 1.52; }

    .info-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 22px;
      box-shadow: var(--shadow-sm);
      width: 100%;
      min-width: 0;
    }
    .tag {
      display: inline-block;
      font-size: 11.5px;
      font-weight: 700;
      padding: 3px 9px;
      border-radius: 4px;
      margin-bottom: 8px;
      max-width: 100%;
    }
    .tag-red { background: var(--red-soft); color: var(--red); }
    .tag-green { background: var(--green-soft); color: var(--green); }
    .tag-blue { background: var(--blue-soft); color: var(--blue); }
    .tag-amber { background: var(--amber-soft); color: var(--amber); }

    .tab-bar { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
    .tab-btn {
      appearance: none;
      border: 1px solid var(--border);
      background: var(--surface);
      color: var(--text-secondary);
      padding: 9px 14px;
      border-radius: 8px;
      font-size: 13.3px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s;
      font-family: inherit;
      text-align: left;
    }
    .tab-btn:hover { border-color: var(--blue); color: var(--blue); }
    .tab-btn.active {
      background: var(--blue);
      border-color: var(--blue);
      color: #FFFFFF;
      box-shadow: 0 2px 6px rgba(26, 115, 232, 0.24);
    }

    .diagram-frame {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 20px;
      box-shadow: var(--shadow-sm);
      width: 100%;
      min-width: 0;
    }
    .diagram-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 16px;
      margin-bottom: 14px;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--surface-subtle);
      flex-wrap: wrap;
    }
    .diagram-header > div { flex: 1 1 520px; min-width: 0; }
    .diagram-canvas {
      width: 100%;
      overflow-x: auto;
      background: #FFFFFF;
      border: 1px solid var(--surface-subtle);
      border-radius: 8px;
      padding: 12px;
      text-align: center;
    }
    .diagram-canvas img { max-width: 100%; height: auto; display: block; margin: 0 auto; cursor: zoom-in; }

    /* Tables: wrap cleanly inside container; scroll horizontally ONLY inside .table-wrap when needed */
    .table-wrap {
      width: 100%;
      max-width: 100%;
      overflow-x: auto;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      box-shadow: var(--shadow-sm);
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13.3px;
    }
    th {
      background: var(--surface-subtle);
      color: var(--text);
      font-weight: 700;
      text-align: left;
      padding: 11px 13px;
      border-bottom: 1px solid var(--border);
      white-space: normal;
      line-height: 1.45;
      overflow-wrap: anywhere;
    }
    td {
      padding: 11px 13px;
      border-bottom: 1px solid #ECEFF1;
      vertical-align: top;
      line-height: 1.55;
      overflow-wrap: anywhere;
    }
    .matrix-table {
      table-layout: fixed;
      min-width: 760px;
    }
    .matrix-table th:nth-child(1), .matrix-table td:nth-child(1) { width: 17%; }
    .matrix-table th:nth-child(2), .matrix-table td:nth-child(2) { width: 26%; }
    .matrix-table th:nth-child(3), .matrix-table td:nth-child(3) { width: 25%; }
    .matrix-table th:nth-child(4), .matrix-table td:nth-child(4) { width: 32%; }

    .data-table th { white-space: nowrap; }
    .data-table td { white-space: normal; }
    tr:last-child td { border-bottom: none; }
    tr.highlight-row td { background: #F4F8FE; }

    .scenario-shell {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 24px;
      box-shadow: var(--shadow-sm);
      width: 100%;
      min-width: 0;
    }
    .scenario-top {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 14px;
      flex-wrap: wrap;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--border);
      margin-bottom: 18px;
    }
    .scenario-top > div {
      flex: 1 1 560px;
      min-width: 0;
    }
    .route-trace {
      font-size: 12.2px;
      background: var(--blue-soft);
      color: #174EA6;
      padding: 7px 12px;
      border-radius: 6px;
      display: block;
      width: 100%;
      margin-top: 8px;
      font-weight: 500;
      line-height: 1.5;
    }
    .btn-live {
      flex-shrink: 0;
      appearance: none;
      border: 1px solid var(--green);
      background: var(--green);
      color: #FFFFFF;
      font-family: inherit;
      font-size: 13px;
      font-weight: 600;
      padding: 9px 16px;
      border-radius: 7px;
      cursor: pointer;
    }
    .btn-live:hover { opacity: 0.92; }
    .btn-live:disabled { background: var(--surface-subtle); border-color: var(--border); color: var(--text-secondary); cursor: not-allowed; }
    .btn-outline {
      flex-shrink: 0;
      appearance: none;
      border: 1px solid var(--border-strong);
      background: var(--surface);
      color: var(--text);
      font-family: inherit;
      font-size: 12.5px;
      font-weight: 600;
      padding: 6px 12px;
      border-radius: 6px;
      cursor: pointer;
    }
    .btn-outline:hover { border-color: var(--blue); color: var(--blue); }

    .sub-box {
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 15px 18px;
      width: 100%;
      min-width: 0;
    }
    .sub-box.asis-border { border-left: 4px solid var(--red); }
    .sub-box.tobe-border { border-left: 4px solid var(--green); }
    .sub-box-title {
      font-size: 11.5px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-secondary);
      margin-bottom: 6px;
    }

    /* Vertical 4-Scope State Rows */
    .scope-list {
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin-bottom: 18px;
      width: 100%;
    }
    .scope-row {
      display: grid;
      grid-template-columns: 220px minmax(0, 1fr);
      gap: 14px;
      align-items: baseline;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 11px 16px;
      font-size: 13.3px;
    }
    @media (max-width: 720px) {
      .scope-row { grid-template-columns: minmax(0, 1fr); gap: 4px; }
    }
    .scope-key {
      font-size: 12px;
      font-weight: 700;
      color: var(--text-secondary);
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }

    .prompt-box {
      background: #F8FAFD;
      border: 1px solid #C2D7FA;
      border-left: 4px solid var(--blue);
      border-radius: 8px;
      padding: 14px 16px;
      margin-bottom: 18px;
      font-size: 14.2px;
      font-weight: 500;
      width: 100%;
      min-width: 0;
    }

    .metric-ribbon {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }
    @media (max-width: 900px) { .metric-ribbon { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
    @media (max-width: 520px) { .metric-ribbon { grid-template-columns: minmax(0, 1fr); } }
    .metric-cell { background: var(--surface-subtle); border-radius: 8px; padding: 11px 14px; }
    .metric-cell .m-k { font-size: 11.5px; color: var(--text-secondary); font-weight: 600; }
    .metric-cell .m-v { font-size: 16.5px; font-weight: 700; color: var(--text); margin-top: 3px; overflow-wrap: anywhere; }
    .metric-cell .m-v.good { color: var(--green); }

    pre.sql-block {
      width: 100%;
      max-width: 100%;
      background: var(--code-bg);
      color: var(--code-text);
      padding: 14px 16px;
      border-radius: 8px;
      font-size: 12.2px;
      line-height: 1.58;
      overflow-x: auto;
      white-space: pre;
      max-height: 340px;
    }
    .answer-box {
      background: #FFFFFF;
      border: 1px solid var(--border);
      border-left: 4px solid var(--green);
      border-radius: 8px;
      padding: 16px 18px;
      font-size: 14px;
      width: 100%;
      min-width: 0;
    }
    .answer-box p { margin-bottom: 8px; }
    .answer-box ul { margin-left: 20px; margin-bottom: 8px; }

    .evidence-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 8px;
    }
    .evidence-header .tag { margin-bottom: 0; }

    .live-output {
      margin-top: 16px;
      background: #F0FDF4;
      border: 1px solid #86EFAC;
      border-radius: 8px;
      padding: 16px;
      display: none;
      width: 100%;
      min-width: 0;
    }
    .live-output.visible { display: block; }

    .calc-grid {
      display: grid;
      grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr);
      gap: 20px;
      align-items: stretch;
    }
    @media (max-width: 960px) { .calc-grid { grid-template-columns: minmax(0, 1fr); } }
    .slider-group { margin-bottom: 16px; }
    .slider-head { display: flex; justify-content: space-between; gap: 10px; flex-wrap: wrap; font-size: 13.5px; font-weight: 600; margin-bottom: 6px; }
    input[type="range"] { width: 100%; accent-color: var(--blue); cursor: pointer; }
    .tco-result-box {
      background: #F4F8FE;
      border: 1px solid #C2D7FA;
      border-radius: var(--radius);
      padding: 22px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }
    .tco-tier-strip {
      border-top: 1px solid #C2D7FA;
      padding-top: 12px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      font-size: 13px;
    }
    .tco-tier-strip > div {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 12px;
      flex-wrap: wrap;
      background: #FFFFFF;
      border: 1px solid #DCE8FC;
      border-radius: 6px;
      padding: 8px 12px;
    }
    .savings-big { font-size: 32px; font-weight: 700; color: var(--green); letter-spacing: -0.02em; }

    .modal-backdrop {
      position: fixed;
      inset: 0;
      background: rgba(32, 33, 36, 0.82);
      z-index: 999;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }
    .modal-backdrop.open { display: flex; }
    .modal-box { background: #FFFFFF; border-radius: 10px; max-width: 96vw; max-height: 92vh; overflow: auto; padding: 20px; }
    .modal-box img { width: 100%; min-width: 980px; height: auto; display: block; }
    .footer {
      border-top: 1px solid var(--border);
      padding-top: 24px;
      color: var(--text-secondary);
      font-size: 13px;
      display: flex;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 12px;
    }
    .footer a { color: var(--blue); text-decoration: none; }
"""


HTML_EN = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>PoC Architecture &amp; 2-Tier Token Optimization Blueprint — Google ADK + BigQuery CAA</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+KR:wght@400;500;700&family=Roboto+Mono:wght@400;500;600&display=swap" rel="stylesheet" />
  <style>__SHARED_CSS__</style>
</head>
<body>

  <header class="topbar">
    <div class="topbar-inner">
      <a href="#overview" class="brand">
        <span class="brand-mark"></span>
        <span>Google ADK + BigQuery CAA · State, Routing &amp; 2-Tier Token Blueprint</span>
      </a>
      <nav class="nav-links">
        <a href="#overview">1. PoC Challenges &amp; KPIs</a>
        <a href="#architecture">2. Best-Practice Architecture</a>
        <a href="#scenarios">3. As-Is vs To-Be Scenarios (S1–S5)</a>
        <a href="#benchmarks">4. 2-Tier Token &amp; 90% Cache TCO</a>
        <a href="#repository">5. Git Repo &amp; Quickstart</a>
      </nav>
      <div class="topbar-right">
        <a href="https://github.com/rhkim77/agentic_bi_showcase" target="_blank" rel="noopener" class="gh-link">GitHub Repo</a>
        <div class="lang-switch" aria-label="Language Switcher">
          <a href="./index.html" class="active">EN</a>
          <a href="./index_ko.html">한국어</a>
        </div>
        <span class="env-pill" id="live-status-pill">
          <span class="status-dot"></span>
          <span class="mono" id="live-status-text">Empirical GCP Telemetry Loaded</span>
        </span>
      </div>
    </div>
  </header>

  <main class="container">

    <section id="overview">
      <div class="hero-card">
        <span class="eyebrow">PoC Engineering Verification Blueprint · Google ADK + BigQuery CAA</span>
        <h1>Best-Practice State, Stateless, Memory &amp; Routing Architecture + End-to-End 2-Tier Token Optimization</h1>
        <p class="lead">
          Purpose-built to resolve the two core engineering bottlenecks encountered in enterprise NL2SQL platform PoCs:
          <strong>(1) State, Stateless, Memory &amp; Routing orchestration between a Google ADK Root Agent and BigQuery Conversational Analytics (BQCA) Sub-Agents</strong>, and
          <strong>(2) 2-Tier Token Optimization combining upstream ADK compaction (measured via real <span class="mono">Vertex AI usage_metadata</span>) with downstream BQCA schema scoping and <span class="mono">90%</span> Cached Input Token discounts (<span class="mono">$0.30/1M</span>)</strong>.
        </p>

        <div class="meta-strip">
          <span class="meta-chip"><strong>Track 1:</strong> Root ↔ Sub-Agent State · Stateless 3-Turn Window · 4-Scope Memory · Hybrid Routing</span>
          <span class="meta-chip"><strong>Track 2:</strong> Measured <span class="mono">Vertex AI usage_metadata</span> + BQCA <span class="mono">90%</span> Cached Input Cost Model</span>
          <span class="meta-chip"><strong>Timestamp:</strong> <span class="mono" id="bench-ts"></span></span>
        </div>

        <div class="kpi-grid" id="hero-kpi-grid"></div>
      </div>

      <div class="stack-list" style="margin-top:20px;margin-bottom:0;">
        <div class="info-card">
          <span class="tag tag-blue">PoC Objective 1 · State, Stateless, Memory &amp; Routing</span>
          <h3>Why Default ADK Toolsets &amp; Stateful Conversations Stall</h3>
          <ul style="font-size:13.8px;padding-left:18px;color:var(--text-secondary);margin-top:6px;">
            <li style="margin-bottom:6px;"><strong>Default <span class="mono">ask_data_agent</span> (One-Shot Stateless):</strong> Calls <span class="mono">_get_data_agent_info</span> discovery every turn and sends <span class="mono">single UserMessage</span>—causing Turn-2 context amnesia.</li>
            <li style="margin-bottom:6px;"><strong>Managed <span class="mono">ConversationReference</span> (Stateful):</strong> Locks <span class="mono">1 Conversation = 1 Fixed DataAgent</span>, blocking cross-domain pivots and serializing multi-domain queries.</li>
            <li><strong>Proposed Best Practice:</strong> Static <span class="mono">enum transfer_to_agent</span> + Peer Handoff + <span class="mono">ThreadPoolExecutor</span> parallel <span class="mono">Chat API</span> + ADK <span class="mono">4-Scope State</span> &amp; <span class="mono">MemoryService</span> + <span class="mono">App(context_cache_config=...)</span>.</li>
          </ul>
        </div>

        <div class="info-card">
          <span class="tag tag-green">PoC Objective 2 · 2-Tier Token Diet &amp; 90% Cache Cost</span>
          <h3>5-Stage End-to-End Token Optimization Pipeline</h3>
          <ul style="font-size:13.8px;padding-left:18px;color:var(--text-secondary);margin-top:6px;">
            <li style="margin-bottom:6px;"><strong>Stage 1–2 (BQCA Schema Diet):</strong> Remove runtime discovery tools and split 110K-token monolithic DDL into 3 least-privilege Domain Agents (<span class="mono">4 / 3 / 5</span> tables).</li>
            <li style="margin-bottom:6px;"><strong>Stage 3–4 (Dual O(1) Sliding Windows):</strong> Strip <span class="mono">THOUGHT</span> logs, cap tool tables at 20 rows (Turn Scope auto-eviction), bound BQCA 3-Turn Sliding Window (6 Messages), and compact upstream ADK <span class="mono">llm_request.contents</span> via <span class="mono">before_model_callback</span>.</li>
            <li><strong>Stage 5 (Effective Billed Cost):</strong> Maximize BQCA <span class="mono">90%</span> Cached Input (<span class="mono">$0.30/1M</span> vs <span class="mono">$3.00/1M</span>) and short-circuit repeat session recalls via <span class="mono">MemoryService</span> (<span class="mono">0</span> BQCA tokens).</li>
          </ul>
        </div>
      </div>
    </section>

    <section id="architecture">
      <h2>2. Best-Practice Multi-Agent Architecture &amp; Trade-Off Matrix</h2>
      <p class="section-desc">
        Inspect the four official Google Cloud vector architecture views and the unbiased trade-off evaluation across One-Shot Stateless, Server-Managed Stateful, and Proposed ADK-Managed Hybrid architectures.
      </p>

      <div class="tab-bar" id="diagram-tabs">
        <button class="tab-btn active" data-fig="fig1">Fig 1. 3-Tier System Architecture</button>
        <button class="tab-btn" data-fig="fig2">Fig 2. Stateless vs Stateful vs Hybrid State</button>
        <button class="tab-btn" data-fig="fig3">Fig 3. Hybrid Routing (Paths A / B / C)</button>
        <button class="tab-btn" data-fig="fig4">Fig 4. 4-Scope State &amp; 2-Tier Token Diet</button>
      </div>

      <div class="diagram-frame" style="margin-bottom: 24px;">
        <div class="diagram-header">
          <div>
            <h3 id="fig-title" style="margin-bottom:4px;">Fig 1. End-to-End 3-Tier Enterprise System Architecture</h3>
            <p id="fig-caption" style="font-size:13.5px;color:var(--text-secondary);">
              Tier 1 (ADK Root Orchestrator, ContextCacheConfig &amp; 4-Scope State/Memory) → Tier 2 (3 Scoped Stateless BigQuery CAA Agents) → Tier 3 (BigQuery &amp; Hop-1 Glossary).
            </p>
          </div>
          <button class="btn-outline" id="zoom-fig-btn">Expand Full Resolution</button>
        </div>
        <div class="diagram-canvas">
          <img id="fig-img" src="./diagrams/fig1_3tier_system_architecture.svg" alt="System Architecture Diagram" />
        </div>
      </div>

      <div class="table-wrap">
        <table class="matrix-table">
          <thead>
            <tr>
              <th>Architecture Dimension</th>
              <th>Option 1: Default ADK <span class="mono">DataAgentToolset</span> (As-Is One-Shot)</th>
              <th>Option 2: BQCA Managed <span class="mono">ConversationReference</span> (Stateful)</th>
              <th>Option 3 (Proposed Best Practice): ADK 4-Scope + Stateless Chat API (3-Turn Window) + <span class="mono">ContextCacheConfig</span></th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><strong>Root → Sub-Agent Routing</strong></td>
              <td>Calls <span class="mono">list_accessible_data_agents</span> + <span class="mono">get_data_agent_info</span> every turn (+4K–8K tok)</td>
              <td>Fixed to 1 <span class="mono">DataAgent</span> at conversation creation; cannot route dynamically</td>
              <td><strong>Path A:</strong> <span class="mono">enum transfer_to_agent</span> | <strong>Path B:</strong> Direct Peer Handoff | <strong>Path C:</strong> Parallel <span class="mono">ThreadPoolExecutor</span></td>
            </tr>
            <tr class="highlight-row">
              <td><strong>Multi-Turn Context &amp; Lock-In</strong></td>
              <td><span style="color:var(--red);font-weight:600;">Sends single UserMessage only → Turn-2 Amnesia</span></td>
              <td>Retains single-agent history (180d TTL) but <strong>breaks on domain switch</strong></td>
              <td><strong style="color:var(--green);">100% multi-turn retention via 3-Turn Sliding Window + seamless cross-domain pivots</strong></td>
            </tr>
            <tr>
              <td><strong>Upstream ADK Token Scaling</strong></td>
              <td>Unbounded <span class="mono">Session.events</span> (raw JSON + THOUGHT logs accumulate O(N))</td>
              <td>N/A (single-agent UI) or unbounded if wrapped in ADK</td>
              <td><strong>Flat O(1) ceiling via <span class="mono">before_model_callback</span> 3-turn compaction + 20-row cap</strong></td>
            </tr>
            <tr class="highlight-row">
              <td><strong>BQCA Token &amp; 90% Cache Discount</strong></td>
              <td>110,764+ tok on monolithic agent</td>
              <td>90% implicit cache within 1 agent, but linear history growth up to cap</td>
              <td><strong style="color:var(--green);">11.4K–13.9K scoped tokens + <span class="mono">$0.30/1M</span> (90% discount) on cached prefix</strong></td>
            </tr>
            <tr>
              <td><strong>Cross-Session Memory &amp; CMEK</strong></td>
              <td>Wiped on <strong>New Session</strong></td>
              <td>Isolated per conversation ID; no CMEK in <span class="mono">global</span> location</td>
              <td><strong><strong>User Scope</strong> + <span class="mono">ADK MemoryService</span> (0-BQCA-token recall across sessions; CMEK DB ready)</strong></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section id="scenarios">
      <h2>3. Live As-Is vs. To-Be PoC Scenario Verification (S1 – S5)</h2>
      <p class="section-desc">
        Each tab below contrasts the <strong>As-Is Anti-Pattern</strong> directly against the <strong>To-Be Best Practice</strong> with real <span class="mono">Vertex AI usage_metadata</span> token counts, BigQuery SQL diffs, 4-Scope state snapshots, and live Cloud Run re-execution.
      </p>

      <div class="tab-bar" id="scenario-tabs"></div>
      <div class="scenario-shell" id="scenario-detail"></div>
    </section>

    <section id="benchmarks">
      <h2>4. 2-Tier Token Scaling Curves &amp; 90% Cached Input Effective Cost Simulator</h2>
      <p class="section-desc">
        Left: Combined 10-Turn 2-Tier Input Token scaling (ADK Orchestrator + BQCA). Right: Directly measured 5-Turn <span class="mono">Vertex AI usage_metadata.prompt_token_count</span> proving upstream ADK compaction. Below: Interactive PAYG Effective Cost Simulator incorporating the official <strong>90% BQCA Cached Input Token discount (<span class="mono">$0.30/1M</span> vs <span class="mono">$3.00/1M</span>)</strong>.
      </p>

      <div class="two-col" style="margin-bottom: 24px;">
        <div class="info-card">
          <h3>10-Turn Combined 2-Tier Input Token Scaling (ADK + BQCA)</h3>
          <p style="font-size:13px;color:var(--text-secondary);margin-bottom:12px;">
            Bounding both ADK <span class="mono">llm_request.contents</span> (3 user turns) and BQCA <span class="mono">DataAgentContext.messages (3-Turn Window)</span> locks total 2-tier tokens at an O(1) ceiling from Turn 4 onward.
          </p>
          <div id="svg-turn-chart"></div>
        </div>

        <div class="info-card">
          <h3>Live 5-Turn Measured <span class="mono">Vertex AI usage_metadata</span> (ADK Tier Only)</h3>
          <p style="font-size:13px;color:var(--text-secondary);margin-bottom:12px;">
            Real <span class="mono">prompt_token_count</span> recorded by <span class="mono">after_model_callback</span> on <span class="mono">gemini-2.5-flash</span>: As-Is Unbounded JSON/THOUGHT accumulation vs. To-Be 3-Turn Compaction.
          </p>
          <div id="svg-adk-measured-chart"></div>
        </div>
      </div>

      <div class="info-card">
        <div style="margin-bottom:16px;">
          <span class="tag tag-green">2-Tier + 90% Cached Input FinOps Simulator</span>
          <h3>Effective PAYG Token Cost &amp; Annual Savings Calculator (<span class="mono">$3.00/1M</span> Non-Cached vs <span class="mono">$0.30/1M</span> Cached Input)</h3>
        </div>
        <div class="calc-grid">
          <div>
            <div class="slider-group">
              <div class="slider-head">
                <span>Daily Enterprise NL2SQL Queries</span>
                <span class="mono" id="lbl-qpd">10,000 queries / day</span>
              </div>
              <input type="range" id="rng-qpd" min="1000" max="50000" step="1000" value="10000" />
            </div>

            <div class="slider-group">
              <div class="slider-head">
                <span>Average Conversation Depth (Turns / Session)</span>
                <span class="mono" id="lbl-turns">5 turns</span>
              </div>
              <input type="range" id="rng-turns" min="1" max="10" step="1" value="5" />
            </div>

            <div class="slider-group" style="margin-bottom: 6px;">
              <div class="slider-head">
                <span>BQCA Static Prefix Cache Hit Ratio (90% Discounted @ <span class="mono">$0.30/1M</span>)</span>
                <span class="mono" id="lbl-cache">60% cached prefix</span>
              </div>
              <input type="range" id="rng-cache" min="0" max="85" step="5" value="60" />
              <p style="font-size:12px;color:var(--text-secondary);margin-top:6px;">
                Official Data Cloud Agent PAYG rates: Non-cached Input <span class="mono">$3.00/1M</span>, Cached Input <span class="mono">$0.30/1M</span> (90% discount), Output <span class="mono">$20.00/1M</span>; Vertex AI <span class="mono">gemini-2.5-flash</span> Orchestrator <span class="mono">$0.30/1M</span> input, <span class="mono">$2.50/1M</span> output.
              </p>
            </div>
          </div>

          <div class="tco-result-box">
            <div>
              <div style="font-size:12px;font-weight:700;text-transform:uppercase;color:var(--text-secondary);margin-bottom:4px;">
                Net Annual Effective Cost Savings (vs. As-Is Monolithic w/ Same Cache Ratio)
              </div>
              <div class="savings-big" id="tco-annual-savings">$0 / yr</div>
              <div style="font-size:13px;color:var(--text-secondary);margin-bottom:14px;" id="tco-pct-note"></div>
            </div>

            <div class="tco-tier-strip">
              <div>
                <div style="color:var(--text-secondary);">As-Is (0% Cache)</div>
                <div class="mono" style="font-weight:700;font-size:15px;color:#5F6368;" id="tco-asis-nocache">$0</div>
                <div class="mono" style="font-size:11px;color:var(--text-secondary);">Unscoped $3.00/1M</div>
              </div>
              <div>
                <div style="color:var(--text-secondary);">As-Is (With Cache)</div>
                <div class="mono" style="font-weight:700;font-size:15px;color:var(--red);" id="tco-asis-cached">$0</div>
                <div class="mono" style="font-size:11px;color:var(--text-secondary);" id="tco-mono-tok"></div>
              </div>
              <div>
                <div style="color:var(--text-secondary);">To-Be (Scoped + Cache)</div>
                <div class="mono" style="font-weight:700;font-size:15px;color:var(--green);" id="tco-tobe-cached">$0</div>
                <div class="mono" style="font-size:11px;color:var(--text-secondary);" id="tco-scoped-tok"></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section id="repository">
      <h2>5. Git Repository Implementation Map &amp; 4-Step PoC Reproduction</h2>
      <div class="stack-list">
        <div class="info-card">
          <h3>Key Implementation Files</h3>
          <pre class="sql-block" style="max-height:none;font-size:12px;">agentic_bi_showcase/  (https://github.com/rhkim77/agentic_bi_showcase)
├── agents/
│   ├── bq_caa_3domain_multi_agent/agent.py      # Root + 3 Sub-Agents + ContextCacheConfig + 4-Scope State
│   │                                            # + before_model_callback (3-turn cap) + after_model_callback
│   ├── bq_caa_streaming_agent/agent.py          # SequentialAgent + BaseAgent :chat SSE Streamer
│   └── bq_caa_toolset_agent/agent.py            # Built-in DataAgentToolset baseline comparison
├── scripts/
│   ├── 04_run_scenario_benchmarks.py            # Runs live S1-S5 As-Is vs To-Be + Vertex usage_metadata
│   ├── provision_cymbal_caa_agents.py           # Provisions 3 Domain-Scoped BigQuery CAA Agents
│   └── build_outcome_portal.py                  # Compiles EN (index.html) &amp; KO (index_ko.html) portals
├── benchmarks/scenario_benchmark_results.json   # Empirical SQL, state diffs &amp; usage_metadata telemetry
└── docs/
    ├── ARCHITECTURE_AND_CONFIGURATION_GUIDE.md
    └── SCENARIO_WALKTHROUGH_AND_BENCHMARKS.md</pre>
        </div>

        <div class="info-card">
          <h3>Reproduce All 5 A/B Scenarios on GCP</h3>
          <pre class="sql-block" style="max-height:none;font-size:12px;margin-bottom:12px;">gcloud auth application-default login \
  --scopes="https://www.googleapis.com/auth/cloud-platform"
export GOOGLE_GENAI_USE_VERTEXAI=TRUE
export GOOGLE_CLOUD_PROJECT="your-gcp-project-id"

git clone https://github.com/rhkim77/agentic_bi_showcase.git
cd agentic_bi_showcase
uv sync
uv run python scripts/provision_cymbal_caa_agents.py
uv run python scripts/04_run_scenario_benchmarks.py
uv run python scripts/build_outcome_portal.py
uv run adk web agents --port 8000</pre>
          <p style="font-size:12.8px;color:var(--text-secondary);">
            References: <a href="https://cloud.google.com/gemini/docs/conversational-analytics-api/integration-patterns" target="_blank" style="color:var(--blue);">CAA Integration Patterns</a> ·
            <a href="https://cloud.google.com/gemini/docs/conversational-analytics-api/state-management" target="_blank" style="color:var(--blue);">CAA State Management</a> ·
            <a href="https://cloud.google.com/products/data-agents/pricing" target="_blank" style="color:var(--blue);">Data Agents Pricing (90% Cached Input)</a> ·
            <a href="https://google.github.io/adk-docs/sessions/" target="_blank" style="color:var(--blue);">ADK Sessions &amp; Memory</a>
          </p>
        </div>
      </div>
    </section>

    <footer class="footer">
      <div>Google Cloud Customer Engineering · ADK + BigQuery CAA State, Routing &amp; 2-Tier Token Optimization Blueprint</div>
      <div>Empirical Telemetry: <span class="mono">Vertex AI usage_metadata</span> + <span class="mono">geminidataanalytics.googleapis.com/v1</span></div>
    </footer>
  </main>

  <div class="modal-backdrop" id="fig-modal">
    <div class="modal-box">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
        <strong id="modal-title">Architecture Diagram</strong>
        <button class="btn-outline" id="close-modal-btn">Close (Esc)</button>
      </div>
      <img id="modal-img" src="" alt="Full Resolution Diagram" />
    </div>
  </div>

  <script>
    const BENCHMARK_DATA = __BENCHMARK_JSON_PAYLOAD__;
    const UI_STRINGS = __UI_STRINGS_PAYLOAD__;
    __PORTAL_JS__
  </script>
</body>
</html>
"""


HTML_KO = r"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>PoC 기술 검증 Portal — ADK + BigQuery CAA State·Routing 및 2-Tier Token 최적화 (한국어)</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+KR:wght@400;500;700&family=Roboto+Mono:wght@400;500;600&display=swap" rel="stylesheet" />
  <style>__SHARED_CSS__</style>
</head>
<body>

  <header class="topbar">
    <div class="topbar-inner">
      <a href="#overview" class="brand">
        <span class="brand-mark"></span>
        <span>Google ADK + BigQuery CAA · State·Routing 및 Token 최적화 PoC</span>
      </a>
      <nav class="nav-links">
        <a href="#overview">1. PoC 핵심 과제 및 실측 KPI</a>
        <a href="#architecture">2. Best Practice Architecture</a>
        <a href="#scenarios">3. As-Is vs To-Be 시현 (S1–S5)</a>
        <a href="#benchmarks">4. 2-Tier Token 및 90% Cache 비용</a>
        <a href="#repository">5. Git Repository 및 재현</a>
      </nav>
      <div class="topbar-right">
        <a href="https://github.com/rhkim77/agentic_bi_showcase" target="_blank" rel="noopener" class="gh-link">GitHub Repo</a>
        <div class="lang-switch" aria-label="언어 전환">
          <a href="./index.html">EN</a>
          <a href="./index_ko.html" class="active">한국어</a>
        </div>
        <span class="env-pill" id="live-status-pill">
          <span class="status-dot"></span>
          <span class="mono" id="live-status-text">GCP 실측 Telemetry 로드됨</span>
        </span>
      </div>
    </div>
  </header>

  <main class="container">

    <section id="overview">
      <div class="hero-card">
        <span class="eyebrow">PoC Engineering Verification Blueprint · Google ADK + BigQuery CAA</span>
        <h1>ADK Root ↔ Sub-Agent(BQCA) State·Stateless·Memory·Routing 개선 및 2-Tier Token 최적화 검증</h1>
        <p class="lead">
          전사 NL2SQL Platform 연동 PoC에서 고객이 직면하는 2대 핵심 기술 과제인
          <strong>1) ADK 기반 Root Agent와 Sub-Agent(BQCA) 간 State·Stateless·Memory·Routing 최적 설계</strong>와
          <strong>2) 실제 <span class="mono">Vertex AI usage_metadata</span> 실측치 및 <span class="mono">BQCA Cached Input 90% 할인($0.30/1M)</span>을 반영한 2-Tier Token 절감 Architecture</strong>를
          5대 <span class="mono">As-Is</span> vs <span class="mono">To-Be</span> 직접 대조 Scenario(S1–S5)로 증명합니다.
        </p>

        <div class="meta-strip">
          <span class="meta-chip"><strong>핵심 과제 1:</strong> Root ↔ Sub-Agent State · Stateless 3-Turn Window · 4-Scope Memory · Hybrid Routing</span>
          <span class="meta-chip"><strong>핵심 과제 2:</strong> <span class="mono">Vertex AI usage_metadata</span> 실측 + BQCA <span class="mono">90%</span> Cached Input 실효 비용</span>
          <span class="meta-chip"><strong>실측 시각 (UTC):</strong> <span class="mono" id="bench-ts"></span></span>
        </div>

        <div class="kpi-grid" id="hero-kpi-grid"></div>
      </div>

      <div class="stack-list" style="margin-top:20px;margin-bottom:0;">
        <div class="info-card">
          <span class="tag tag-blue">고객 문제상황 1 · State, Stateless, Memory &amp; Routing</span>
          <h3>기본 ADK Toolset 및 Stateful API 단독 사용 시 한계와 해결책</h3>
          <ul style="font-size:13.8px;padding-left:18px;color:var(--text-secondary);margin-top:6px;">
            <li style="margin-bottom:6px;"><strong>ADK 내장 <span class="mono">ask_data_agent</span> (One-Shot Stateless):</strong> 매 Turn <span class="mono">_get_data_agent_info</span> 탐색을 반복 호출하고 단일 <span class="mono">UserMessage</span> 1건만 전송해 2턴 후속 질문에서 선행 조건이 유실됩니다.</li>
            <li style="margin-bottom:6px;"><strong>관리형 <span class="mono">ConversationReference</span> (Stateful):</strong> <span class="mono">1 Conversation = 1 고정 DataAgent</span>에 종속되어 타 업무 Domain 전환 시 문맥이 끊기며 동시 병렬 호출이 직렬화됩니다.</li>
            <li><strong>제안 Best Practice:</strong> 정적 <span class="mono">enum transfer_to_agent</span> + Sub-Agent 간 직접 Peer 전환 + <span class="mono">ThreadPoolExecutor</span> 병렬 <span class="mono">Chat API</span> + <span class="mono">4-Scope State/Memory</span> + <span class="mono">App(context_cache_config=...)</span> 격리 Cache 적용.</li>
          </ul>
        </div>

        <div class="info-card">
          <span class="tag tag-green">고객 문제상황 2 · 2-Tier Token 절감 및 90% Cache 비용 최적화</span>
          <h3>ADK 계층 + BQCA 계층 5단계 Token Diet Pipeline</h3>
          <ul style="font-size:13.8px;padding-left:18px;color:var(--text-secondary);margin-top:6px;">
            <li style="margin-bottom:6px;"><strong>Stage 1–2 (탐색 제거 및 Schema 분리):</strong> 런타임 Discovery Tool을 제거하고 110K+ 단일 통합 Agent를 최소 권한 Domain Agent(<span class="mono">4 / 3 / 5</span>개 Table)로 분할합니다.</li>
            <li style="margin-bottom:6px;"><strong>Stage 3–4 (양방향 O(1) 상한선 고정):</strong> <span class="mono">THOUGHT</span> 스트림 제거 + 20행 요약 캡(Turn Scope 즉시 소거), 하위 BQCA 3-Turn Sliding Window (6 Messages) 제한, 상위 ADK <span class="mono">before_model_callback</span> 3-Turn 이력 압축을 동시 적용합니다.</li>
            <li><strong>Stage 5 (실효 과금 최소화):</strong> 고정 Prefix 기반 BQCA <span class="mono">90%</span> Cached Input 할인(<span class="mono">$3.00/1M → $0.30/1M</span>)과 <span class="mono">MemoryService</span> 우회(<span class="mono">BQCA 0 tok</span>)를 결합합니다.</li>
          </ul>
        </div>
      </div>
    </section>

    <section id="architecture">
      <h2>2. Best Practice Architecture 및 다각도 Trade-off 비교</h2>
      <p class="section-desc">
        공식 Google Cloud Vector Diagram 4종과 함께, One-Shot Stateless·서버 관리형 Stateful·제안 Hybrid 구조 간의 객관적인 기술 지표를 비교합니다.
      </p>

      <div class="tab-bar" id="diagram-tabs">
        <button class="tab-btn active" data-fig="fig1">Fig 1. 3-Tier 전체 System Architecture</button>
        <button class="tab-btn" data-fig="fig2">Fig 2. Stateless vs Stateful vs 제안 Hybrid</button>
        <button class="tab-btn" data-fig="fig3">Fig 3. 3-Way Hybrid Routing (Path A / B / C)</button>
        <button class="tab-btn" data-fig="fig4">Fig 4. 4-Scope State 및 2-Tier Token Diet</button>
      </div>

      <div class="diagram-frame" style="margin-bottom: 24px;">
        <div class="diagram-header">
          <div>
            <h3 id="fig-title" style="margin-bottom:4px;">Fig 1. End-to-End 3-Tier Enterprise System Architecture</h3>
            <p id="fig-caption" style="font-size:13.5px;color:var(--text-secondary);">
              Tier 1 (ADK Root Orchestrator, ContextCacheConfig 및 4-Scope State/Memory) → Tier 2 (3개 Domain-Scoped Stateless BigQuery CAA) → Tier 3 (BigQuery 및 Hop-1 Glossary).
            </p>
          </div>
          <button class="btn-outline" id="zoom-fig-btn">원본 해상도로 확대 보기</button>
        </div>
        <div class="diagram-canvas">
          <img id="fig-img" src="./diagrams/fig1_3tier_system_architecture.svg" alt="System Architecture Diagram" />
        </div>
      </div>

      <div class="table-wrap">
        <table class="matrix-table">
          <thead>
            <tr>
              <th>설계 비교 항목</th>
              <th>Option 1: ADK 기본 <span class="mono">DataAgentToolset</span> (As-Is One-Shot)</th>
              <th>Option 2: BQCA 관리형 <span class="mono">ConversationReference</span> (Stateful)</th>
              <th>Option 3 (제안 Best Practice): ADK 4-Scope + Stateless Chat API (3-Turn Window) + <span class="mono">ContextCacheConfig</span></th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><strong>Root → Sub-Agent Routing</strong></td>
              <td>매 Turn <span class="mono">list_accessible_data_agents</span> + <span class="mono">get_data_agent_info</span> 탐색 (+4K~8K tok)</td>
              <td>대화 생성 시 단일 <span class="mono">DataAgent</span> 고정 (동적 Routing 불가)</td>
              <td><strong>Path A:</strong> <span class="mono">enum transfer_to_agent</span> | <strong>Path B:</strong> 직접 Peer 전환 | <strong>Path C:</strong> 병렬 <span class="mono">ThreadPoolExecutor</span></td>
            </tr>
            <tr class="highlight-row">
              <td><strong>Multi-Turn 문맥 및 종속성</strong></td>
              <td><span style="color:var(--red);font-weight:600;">단일 UserMessage 1건만 전송 → 2턴 후속 질문 조건 유실</span></td>
              <td>단일 Agent 내 이력 유지(180일 TTL)되나 <strong>타 Domain 전환 시 단절</strong></td>
              <td><strong style="color:var(--green);">3-Turn Sliding Window(최대 6개 요약 문답)로 문맥 100% 유지 + 자유로운 Domain 전환</strong></td>
            </tr>
            <tr>
              <td><strong>상위 ADK 계층 Token 추이</strong></td>
              <td><span class="mono">Session.events</span> 내 원본 JSON + THOUGHT 무한 누적 O(N)</td>
              <td>단독 UI 사용 시 해당 없으나 ADK 래핑 시 동일 누적 발생</td>
              <td><strong><span class="mono">before_model_callback</span> 3-Turn 이력 압축 + 20행 캡으로 O(1) 평탄화</strong></td>
            </tr>
            <tr class="highlight-row">
              <td><strong>하위 BQCA Token 및 90% Cache</strong></td>
              <td>단일 통합 Agent 기준 110,764+ tok 매번 소모</td>
              <td>단일 Agent 내 90% 암시적 Cache 적용되나 이력 선형 증가</td>
              <td><strong style="color:var(--green);">11.4K~13.9K 격리 Schema + 고정 Prefix 구간 <span class="mono">$0.30/1M</span>(90% 할인)</strong></td>
            </tr>
            <tr>
              <td><strong>Session 간 연속성 및 CMEK</strong></td>
              <td><strong>New Session</strong> 생성 시 전면 휘발</td>
              <td>대화방 ID 간 공유 불가; <span class="mono">global</span> Region CMEK 미지원</td>
              <td><strong><strong>User Scope</strong> + <span class="mono">ADK MemoryService</span> (새 Session 첫 Turn 0-BQCA-Token 복원)</strong></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section id="scenarios">
      <h2>3. As-Is 문제 재현 vs To-Be 해결 직접 대조 시현 (Scenario 1 – 5)</h2>
      <p class="section-desc">
        각 Scenario Tab을 클릭하면 실제 GCP에서 채집한 <strong>As-Is 실패/고비용 로그</strong>와 <strong>To-Be 해결 SQL·State Diff</strong>, 그리고 <strong>실제 <span class="mono">Vertex AI usage_metadata</span> 계측치</strong>를 나란히 대조 검증할 수 있습니다.
      </p>

      <div class="tab-bar" id="scenario-tabs"></div>
      <div class="scenario-shell" id="scenario-detail"></div>
    </section>

    <section id="benchmarks">
      <h2>4. 2-Tier Token 평탄화 실측 Chart 및 90% Cached Input 실효 비용 시뮬레이터</h2>
      <p class="section-desc">
        좌측 Chart는 10-Turn 대화 시 통합 2-Tier(ADK + BQCA) Input Token 추이를, 우측 Chart는 <span class="mono">after_model_callback</span>이 실제 계측한 5-Turn 연속 <span class="mono">Vertex AI usage_metadata.prompt_token_count</span>를 보여줍니다. 하단 계산기는 공식 <strong>BQCA Cached Input 90% 할인 단가(<span class="mono">$0.30/1M</span> vs Non-Cached <span class="mono">$3.00/1M</span>)</strong>를 반영해 실효 연간 비용을 산출합니다.
      </p>

      <div class="two-col" style="margin-bottom: 24px;">
        <div class="info-card">
          <h3>10-Turn 통합 2-Tier Input Token 추이 비교 (ADK + BQCA 합산)</h3>
          <p style="font-size:13px;color:var(--text-secondary);margin-bottom:12px;">
            상위 ADK <span class="mono">llm_request.contents</span>(최근 3개 User Turn)와 하위 BQCA 3-Turn Sliding Window (6 Messages)를 동시에 제어하여 4번째 Turn부터 완벽한 O(1) 상한선을 유지합니다.
          </p>
          <div id="svg-turn-chart"></div>
        </div>

        <div class="info-card">
          <h3>5-Turn 연속 <span class="mono">Vertex AI usage_metadata</span> 실제 계측치 (ADK 계층 단독)</h3>
          <p style="font-size:13px;color:var(--text-secondary);margin-bottom:12px;">
            <span class="mono">gemini-2.5-flash</span> <span class="mono">after_model_callback</span> 실측 결과: 원본 JSON/THOUGHT가 계속 쌓이는 As-Is 대비 To-Be 3-Turn 압축의 실제 Prompt Token 절감 효과입니다.
          </p>
          <div id="svg-adk-measured-chart"></div>
        </div>
      </div>

      <div class="info-card">
        <div style="margin-bottom:16px;">
          <span class="tag tag-green">2-Tier + 90% Cached Input 반영 실효 비용 시뮬레이터</span>
          <h3>전사 도입 규모별 연간 실효 과금 비용 비교 (<span class="mono">$3.00/1M</span> Non-Cached vs <span class="mono">$0.30/1M</span> 90% Cached Input)</h3>
        </div>
        <div class="calc-grid">
          <div>
            <div class="slider-group">
              <div class="slider-head">
                <span>일일 전사 NL2SQL 질의 수 (Queries / Day)</span>
                <span class="mono" id="lbl-qpd">10,000 queries / day</span>
              </div>
              <input type="range" id="rng-qpd" min="1000" max="50000" step="1000" value="10000" />
            </div>

            <div class="slider-group">
              <div class="slider-head">
                <span>Session당 평균 연속 Turn 수</span>
                <span class="mono" id="lbl-turns">5 turns</span>
              </div>
              <input type="range" id="rng-turns" min="1" max="10" step="1" value="5" />
            </div>

            <div class="slider-group" style="margin-bottom: 6px;">
              <div class="slider-head">
                <span>BQCA 정적 Prefix Cache 적중 비중 (90% 할인 <span class="mono">$0.30/1M</span> 적용 구간)</span>
                <span class="mono" id="lbl-cache">60% cached prefix</span>
              </div>
              <input type="range" id="rng-cache" min="0" max="85" step="5" value="60" />
              <p style="font-size:12px;color:var(--text-secondary);margin-top:6px;">
                공식 Data Cloud Agent PAYG 과금 기준: 일반 Input <span class="mono">$3.00/1M</span>, Cached Input <span class="mono">$0.30/1M</span>(90% 할인, 일일 Quota 차감 시에도 0.1배 적용), Output <span class="mono">$20.00/1M</span> + 상위 Vertex AI <span class="mono">gemini-2.5-flash</span>(<span class="mono">$0.30/1M</span> Input, <span class="mono">$2.50/1M</span> Output) 합산.
              </p>
            </div>
          </div>

          <div class="tco-result-box">
            <div>
              <div style="font-size:12px;font-weight:700;text-transform:uppercase;color:var(--text-secondary);margin-bottom:4px;">
                연간 실효 과금 순절감액 (동일 Cache 비중 적용 As-Is 대비)
              </div>
              <div class="savings-big" id="tco-annual-savings">$0 / yr</div>
              <div style="font-size:13px;color:var(--text-secondary);margin-bottom:14px;" id="tco-pct-note"></div>
            </div>

            <div class="tco-tier-strip">
              <div>
                <div style="color:var(--text-secondary);">As-Is (Cache 미적용)</div>
                <div class="mono" style="font-weight:700;font-size:15px;color:#5F6368;" id="tco-asis-nocache">$0</div>
                <div class="mono" style="font-size:11px;color:var(--text-secondary);">전액 $3.00/1M 기준</div>
              </div>
              <div>
                <div style="color:var(--text-secondary);">As-Is (동일 Cache 반영)</div>
                <div class="mono" style="font-weight:700;font-size:15px;color:var(--red);" id="tco-asis-cached">$0</div>
                <div class="mono" style="font-size:11px;color:var(--text-secondary);" id="tco-mono-tok"></div>
              </div>
              <div>
                <div style="color:var(--text-secondary);">To-Be (2-Tier Diet + Cache)</div>
                <div class="mono" style="font-weight:700;font-size:15px;color:var(--green);" id="tco-tobe-cached">$0</div>
                <div class="mono" style="font-size:11px;color:var(--text-secondary);" id="tco-scoped-tok"></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section id="repository">
      <h2>5. Git Repository 핵심 구현 위치 및 4단계 PoC 재현 명령어</h2>
      <div class="stack-list">
        <div class="info-card">
          <h3>핵심 구현 File 매핑</h3>
          <pre class="sql-block" style="max-height:none;font-size:12px;">agentic_bi_showcase/  (https://github.com/rhkim77/agentic_bi_showcase)
├── agents/
│   ├── bq_caa_3domain_multi_agent/agent.py      # Root + 3 Sub-Agent + App(ContextCacheConfig)
│   │                                            # + before_model_callback(3-Turn 압축) + after_model_callback(실측)
│   ├── bq_caa_streaming_agent/agent.py          # SequentialAgent + BaseAgent :chat SSE Streamer
│   └── bq_caa_toolset_agent/agent.py            # 내장 DataAgentToolset 대조군
├── scripts/
│   ├── 04_run_scenario_benchmarks.py            # S1-S5 As-Is vs To-Be + Vertex usage_metadata 실측 Script
│   ├── provision_cymbal_caa_agents.py           # 3종 Domain-Scoped BigQuery CAA 자동 생성
│   └── build_outcome_portal.py                  # 영문(index.html) 및 한국어(index_ko.html) Portal 생성
├── benchmarks/scenario_benchmark_results.json   # 실측 SQL, 4-Scope JSON Diff 및 usage_metadata 원본
└── docs/
    ├── ARCHITECTURE_AND_CONFIGURATION_GUIDE.md
    └── SCENARIO_WALKTHROUGH_AND_BENCHMARKS.md</pre>
        </div>

        <div class="info-card">
          <h3>동일 A/B Benchmark 재현 절차</h3>
          <pre class="sql-block" style="max-height:none;font-size:12px;margin-bottom:12px;">gcloud auth application-default login \
  --scopes="https://www.googleapis.com/auth/cloud-platform"
export GOOGLE_GENAI_USE_VERTEXAI=TRUE
export GOOGLE_CLOUD_PROJECT="your-gcp-project-id"

git clone https://github.com/rhkim77/agentic_bi_showcase.git
cd agentic_bi_showcase
uv sync
uv run python scripts/provision_cymbal_caa_agents.py
uv run python scripts/04_run_scenario_benchmarks.py
uv run python scripts/build_outcome_portal.py
uv run adk web agents --port 8000</pre>
          <p style="font-size:12.8px;color:var(--text-secondary);">
            공식 참조 문서: <a href="https://cloud.google.com/gemini/docs/conversational-analytics-api/integration-patterns" target="_blank" style="color:var(--blue);">CAA Integration Patterns</a> ·
            <a href="https://cloud.google.com/gemini/docs/conversational-analytics-api/state-management" target="_blank" style="color:var(--blue);">CAA State Management</a> ·
            <a href="https://cloud.google.com/products/data-agents/pricing" target="_blank" style="color:var(--blue);">Data Agents 과금 정책(90% Cached Input)</a> ·
            <a href="https://google.github.io/adk-docs/sessions/" target="_blank" style="color:var(--blue);">ADK Session &amp; Memory</a>
          </p>
        </div>
      </div>
    </section>

    <footer class="footer">
      <div>Google Cloud Customer Engineering · ADK + BigQuery CAA State·Routing 및 2-Tier Token 최적화 검증 Blueprint</div>
      <div>실측 Telemetry: <span class="mono">Vertex AI usage_metadata</span> + <span class="mono">geminidataanalytics.googleapis.com/v1</span></div>
    </footer>
  </main>

  <div class="modal-backdrop" id="fig-modal">
    <div class="modal-box">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
        <strong id="modal-title">Architecture Diagram</strong>
        <button class="btn-outline" id="close-modal-btn">닫기 (Esc)</button>
      </div>
      <img id="modal-img" src="" alt="Full Resolution Diagram" />
    </div>
  </div>

  <script>
    const BENCHMARK_DATA = __BENCHMARK_JSON_PAYLOAD__;
    const UI_STRINGS = __UI_STRINGS_PAYLOAD__;
    __PORTAL_JS__
  </script>
</body>
</html>
"""


PORTAL_JS = r"""
    let liveApiAvailable = false;
    let activeScenarioIdx = 0;

    function escapeHtml(str) {
      return String(str || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
    }

    function formatInlineText(str) {
      return escapeHtml(str)
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(/`([^`]+)`/g, "<strong>$1</strong>")
        .replace(/&lt;-&gt;/g, "↔")
        .replace(/-&gt;/g, "→");
    }

    function parseMarkdownTableToHtml(md) {
      if (!md || !md.trim()) return "";
      const lines = md.trim().split("\n").filter(l => l.trim().startsWith("|"));
      if (lines.length < 2) return `<pre class="sql-block">${escapeHtml(md)}</pre>`;
      const headers = lines[0].split("|").slice(1, -1).map(c => c.trim());
      const rows = lines.slice(2).map(line => line.split("|").slice(1, -1).map(c => c.trim()));
      let html = `<div class="table-wrap"><table class="data-table"><thead><tr>`;
      headers.forEach(h => { html += `<th class="mono">${escapeHtml(h)}</th>`; });
      html += `</tr></thead><tbody>`;
      rows.forEach(r => {
        html += `<tr>`;
        r.forEach(c => { html += `<td class="mono">${escapeHtml(c)}</td>`; });
        html += `</tr>`;
      });
      html += `</tbody></table></div>`;
      return html;
    }

    function formatAgentAnswer(raw) {
      if (!raw) return "";
      const cleaned = raw.split(/\nAnalyze |\nForecast |\nShow |\nIdentify |\nCompare |\nDetect |\nBreak down /)[0].trim();
      const lines = cleaned.split("\n");
      let out = "";
      let inList = false;
      for (const line of lines) {
        const t = line.trim();
        if (!t) {
          if (inList) { out += "</ul>"; inList = false; }
          continue;
        }
        const bolded = escapeHtml(t).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/`([^`]+)`/g, "<strong>$1</strong>").replace(/&lt;-&gt;/g, "↔").replace(/-&gt;/g, "→");
        if (t.startsWith("### ")) {
          if (inList) { out += "</ul>"; inList = false; }
          out += `<div style="font-weight:700;margin:8px 0 4px;color:var(--text);">${bolded.replace(/^###\s+/, "")}</div>`;
        } else if (t.startsWith("- ") || t.startsWith("* ") || /^\d+\.\s/.test(t)) {
          if (!inList) { out += "<ul>"; inList = true; }
          out += `<li style="margin-bottom:4px;">${bolded.replace(/^([-*]|\d+\.)\s+/, "")}</li>`;
        } else {
          if (inList) { out += "</ul>"; inList = false; }
          out += `<p>${bolded}</p>`;
        }
      }
      if (inList) out += "</ul>";
      return out;
    }

    function renderHeroKpis() {
      const hm = BENCHMARK_DATA.headline_metrics;
      const S = UI_STRINGS.heroKpis;
      document.getElementById("hero-kpi-grid").innerHTML = `
        <div class="kpi-card green">
          <div class="kpi-label">${S.k1Label}</div>
          <div class="kpi-value">-${hm.s1_token_reduction_pct}%</div>
          <div class="kpi-sub"><strong>${hm.s1_tobe_total_input_tokens.toLocaleString()} tok</strong> vs ${hm.s1_asis_total_input_tokens.toLocaleString()} As-Is (ADK <span class="mono">usage_metadata</span>: ${hm.s1_asis_adk_measured_tokens.toLocaleString()} → ${hm.s1_tobe_adk_measured_tokens.toLocaleString()} tok).</div>
        </div>
        <div class="kpi-card green">
          <div class="kpi-label">${S.k2Label}</div>
          <div class="kpi-value">-${hm.s4_turn5_adk_reduction_pct}%</div>
          <div class="kpi-sub">Turn-5 Measured ADK <span class="mono">prompt_token_count</span>: <strong>${hm.s4_turn5_tobe_adk_measured_tokens.toLocaleString()} tok</strong> vs ${hm.s4_turn5_asis_adk_measured_tokens.toLocaleString()} As-Is unbounded.</div>
        </div>
        <div class="kpi-card blue">
          <div class="kpi-label">${S.k3Label}</div>
          <div class="kpi-value">${hm.s3_speedup_x}x ${S.fasterWord}</div>
          <div class="kpi-sub"><strong>${(hm.s3_parallel_wall_ms / 1000).toFixed(2)} s</strong> parallel <span class="mono">Chat API</span> vs ${(hm.s3_sequential_sum_ms / 1000).toFixed(2)} s sequential (-${hm.s3_latency_reduction_pct}%) + direct Peer transfer.</div>
        </div>
        <div class="kpi-card amber">
          <div class="kpi-label">${S.k4Label}</div>
          <div class="kpi-value">0 BQCA Tokens</div>
          <div class="kpi-sub">New <span class="mono">Session-B</span> Turn 1 answered in <strong>${(hm.s5_memory_recall_ms / 1000).toFixed(2)} s</strong> (${hm.s5_memory_adk_measured_tokens.toLocaleString()} ADK tok, 0 BQ bytes scanned).</div>
        </div>
      `;
    }

    function renderScenario(idx) {
      activeScenarioIdx = idx;
      const sc = BENCHMARK_DATA.scenarios[idx];
      const mr = sc.measured_result;
      const st = sc.state_transition;
      const S = UI_STRINGS;

      document.querySelectorAll("#scenario-tabs .tab-btn").forEach((b, i) => {
        b.classList.toggle("active", i === idx);
      });

      const latencyLabel = mr.sequential_sum_ms
        ? `${(mr.latency_ms / 1000).toFixed(2)} s (${S.vsSeq} ${(mr.sequential_sum_ms / 1000).toFixed(2)} s)`
        : `${(mr.latency_ms / 1000).toFixed(2)} s`;

      let evidenceHtml = "";

      if ((sc.code === "S1" || sc.code === "S2") && sc.asis_comparison) {
        const ac = sc.asis_comparison;
        evidenceHtml = `
          <div class="stack-list">
            <div class="sub-box asis-border" style="background:#FFFFFF;">
              <div class="evidence-header">
                <span class="tag tag-red">${formatInlineText(ac.label)}</span>
                <span class="mono" style="font-size:12px;color:var(--red);">${formatInlineText(ac.defect_note)}</span>
              </div>
              <pre class="sql-block">${escapeHtml(ac.generated_sql)}</pre>
            </div>
            <div class="sub-box tobe-border" style="background:#FFFFFF;">
              <div class="evidence-header">
                <span class="tag tag-green">To-Be Best Practice (${mr.scoped_tokens.toLocaleString()} total tok · -${mr.token_reduction_pct}%)</span>
                <span class="mono" style="font-size:12px;color:var(--green);">ADK Measured: ${(mr.adk_measured_prompt_tokens || 0).toLocaleString()} tok</span>
              </div>
              <pre class="sql-block">${escapeHtml(mr.generated_sql)}</pre>
            </div>
            <div>
              <h3 style="font-size:14.5px;margin-bottom:8px;">${S.returnedRows}</h3>
              ${parseMarkdownTableToHtml(mr.rows)}
            </div>
            <div>
              <h3 style="font-size:14.5px;margin-bottom:8px;">${S.caaSummary}</h3>
              <div class="answer-box">${formatAgentAnswer(mr.answer)}</div>
            </div>
          </div>
        `;
      } else if (sc.code === "S3" && mr.sub_results) {
        const peer = sc.peer_routing_proof || {};
        const cards = Object.entries(mr.sub_results).map(([domName, d]) => `
          <div class="sub-box" style="background:#FFFFFF;">
            <div class="evidence-header">
              <strong style="font-size:13.5px;color:var(--blue);">${escapeHtml(S.domainNames[domName] || domName)}</strong>
              <span class="mono" style="font-size:11.5px;background:var(--green-soft);color:var(--green);padding:2px 7px;border-radius:4px;">
                ${(d.latency_ms / 1000).toFixed(2)}s · ${d.scoped_tokens.toLocaleString()} tok
              </span>
            </div>
            <div style="margin-bottom:10px;">${parseMarkdownTableToHtml(d.markdown_table)}</div>
            <details style="margin-bottom:8px;">
              <summary style="cursor:pointer;font-size:12px;font-weight:600;color:var(--text-secondary);">${S.viewDomainSql}</summary>
              <pre class="sql-block" style="margin-top:6px;font-size:11.5px;">${escapeHtml(d.generated_sql)}</pre>
            </details>
            <div style="font-size:12.8px;color:var(--text-secondary);">${formatAgentAnswer(d.summary)}</div>
          </div>
        `).join("");

        evidenceHtml = `
          <div class="sub-box" style="background:#F8FAFD;border-color:#C2D7FA;margin-bottom:16px;">
            <span class="tag tag-blue">Part A · Peer-to-Peer Domain Switch Proof (0 Root Router Bounce)</span>
            <div style="font-size:13.5px;margin-bottom:6px;">
              <strong>Active Agent Handoff Trace:</strong>
              <code class="mono" style="background:#FFFFFF;padding:2px 8px;border-radius:4px;border:1px solid var(--border);">${escapeHtml((peer.agents_hop_trace || []).join(" → "))}</code>
              · Measured ADK <span class="mono">usage_metadata</span>: <strong>${(peer.adk_measured_prompt_tokens || 0).toLocaleString()} tok</strong>
            </div>
          </div>
          <h3 style="font-size:14.5px;margin-bottom:10px;">Part B · ${S.s3ParallelHeading}</h3>
          <div class="stack-list">${cards}</div>
          <div class="answer-box">${S.s3SynthesisHtml}</div>
        `;
      } else if (sc.code === "S4" && mr.measured_5turn_table) {
        const rowsHtml = mr.measured_5turn_table.map(r => {
          const savedPct = ((1 - r.tobe_adk_prompt_tokens_measured / Math.max(1, r.asis_adk_prompt_tokens_measured)) * 100).toFixed(1);
          return `
            <tr>
              <td class="mono"><strong>Turn ${r.turn}</strong></td>
              <td class="mono" style="color:var(--red);">${r.asis_adk_prompt_tokens_measured.toLocaleString()} tok</td>
              <td class="mono" style="color:var(--green);font-weight:700;">${r.tobe_adk_prompt_tokens_measured.toLocaleString()} tok (-${savedPct}%)</td>
              <td class="mono">${r.tobe_compacted_dropped} items evicted</td>
            </tr>
          `;
        }).join("");
        const cc = mr.cost_comparison_turn5 || {};
        evidenceHtml = `
          <div class="stack-list">
            <div>
              <h3 style="font-size:14.5px;margin-bottom:8px;">${S.s4TableHeading}</h3>
              <div class="table-wrap">
                <table class="data-table">
                  <thead>
                    <tr>
                      <th>Turn</th>
                      <th>As-Is Unbounded ADK (<span class="mono">usage_metadata</span>)</th>
                      <th>To-Be Compacted ADK (<span class="mono">usage_metadata</span>)</th>
                      <th><span class="mono">before_model_callback</span></th>
                    </tr>
                  </thead>
                  <tbody>${rowsHtml}</tbody>
                </table>
              </div>
            </div>
            <div>
              <h3 style="font-size:14px;margin-bottom:8px;">${S.s4CostHeading}</h3>
              <div class="answer-box">
                <p><strong>Turn-5 Single Query Effective Cost Breakdown (ADK + BQCA):</strong></p>
                <ul>
                  <li><strong>As-Is Monolithic (0% Cache, $3.00/1M):</strong> <code class="mono">$${Number(cc.asis_no_cache_usd || 0).toFixed(4)} / turn</code></li>
                  <li><strong>As-Is Monolithic (50% Implicit Cache @ $0.30/1M):</strong> <code class="mono">$${Number(cc.asis_with_cache_usd || 0).toFixed(4)} / turn</code></li>
                  <li><strong style="color:var(--green);">To-Be 2-Tier Diet + 65% Cached Prefix (@ $0.30/1M):</strong> <code class="mono" style="color:var(--green);font-weight:700;">$${Number(cc.tobe_with_90pct_cache_usd || 0).toFixed(4)} / turn</code></li>
                </ul>
                <p style="margin-top:8px;font-size:13px;color:var(--text-secondary);">${S.s4CacheExplain}</p>
              </div>
            </div>
          </div>
        `;
      } else {
        const diffJson = sc.state_scope_json_diff ? JSON.stringify(sc.state_scope_json_diff, null, 2) : mr.generated_sql;
        evidenceHtml = `
          <div class="stack-list">
            <div>
              <h3 style="font-size:14.5px;margin-bottom:8px;">${S.s5JsonHeading}</h3>
              <pre class="sql-block">${escapeHtml(diffJson)}</pre>
            </div>
            <div>
              <h3 style="font-size:14px;margin-bottom:8px;">${S.memoryRecallOutput}</h3>
              <div class="answer-box">${formatAgentAnswer(mr.answer)}</div>
            </div>
          </div>
        `;
      }

      const btnLabel = liveApiAvailable
        ? S.btnRunLive.replace("{CODE}", sc.code)
        : S.btnRunDisabled;

      document.getElementById("scenario-detail").innerHTML = `
        <div class="scenario-top">
          <div>
            <span class="tag tag-blue">${escapeHtml(sc.code)} · ${formatInlineText(sc.track || S.scenarioBadge)}</span>
            <h3 style="font-size:19px;margin-bottom:2px;">${formatInlineText(sc.title)}</h3>
            <div class="route-trace mono">Route: ${formatInlineText(sc.routing_path)}</div>
          </div>
          <button class="btn-live" id="run-live-btn" ${liveApiAvailable ? "" : "disabled"}>${btnLabel}</button>
        </div>

        <div class="stack-list">
          <div class="sub-box asis-border">
            <div class="sub-box-title">${S.challengeLabel}</div>
            <div style="font-size:14px;">${formatInlineText(sc.challenge)}</div>
          </div>
          <div class="sub-box tobe-border">
            <div class="sub-box-title">${S.mechanismLabel}</div>
            <div style="font-size:14px;">${formatInlineText(sc.architecture_mechanism)}</div>
          </div>
        </div>

        <div class="prompt-box">
          <span style="font-size:11.5px;font-weight:700;text-transform:uppercase;color:var(--blue);display:block;margin-bottom:3px;">${S.promptLabel}</span>
          "${formatInlineText(sc.prompt)}"
        </div>

        <div class="metric-ribbon">
          <div class="metric-cell">
            <div class="m-k">${S.metricScoped}</div>
            <div class="m-v good mono">${mr.scoped_tokens.toLocaleString()} tok (-${mr.token_reduction_pct}%)</div>
          </div>
          <div class="metric-cell">
            <div class="m-k">Measured ADK <span class="mono">usage_metadata</span></div>
            <div class="m-v mono" style="color:var(--blue);">${(mr.adk_measured_prompt_tokens || 0).toLocaleString()} prompt tok</div>
          </div>
          <div class="metric-cell">
            <div class="m-k">BQCA Tier Input Tokens</div>
            <div class="m-v mono">${(mr.bqca_scoped_tokens !== undefined ? mr.bqca_scoped_tokens : 0).toLocaleString()} tok</div>
          </div>
          <div class="metric-cell">
            <div class="m-k">${S.metricLatency}</div>
            <div class="m-v mono">${latencyLabel}</div>
          </div>
        </div>

        <div class="scope-list">
          <div class="scope-row">
            <div class="scope-key">1. Turn Scope (<span class="mono">temp</span>)</div>
            <div>${formatInlineText(st.temp_scope)}</div>
          </div>
          <div class="scope-row">
            <div class="scope-key">2. Session Scope (<span class="mono">3-Turn Window</span>)</div>
            <div>${formatInlineText(st.session_scope)}</div>
          </div>
          <div class="scope-row">
            <div class="scope-key">3. User Scope &amp; <span class="mono">MemoryService</span></div>
            <div>${formatInlineText(st.user_scope)}</div>
          </div>
        </div>

        ${evidenceHtml}

        <div class="live-output" id="live-verify-box"></div>
      `;

      const runBtn = document.getElementById("run-live-btn");
      if (runBtn && liveApiAvailable) {
        runBtn.addEventListener("click", () => triggerLiveVerification(sc.code));
      }
    }

    async function triggerLiveVerification(scenarioCode) {
      const S = UI_STRINGS;
      const btn = document.getElementById("run-live-btn");
      const box = document.getElementById("live-verify-box");
      btn.disabled = true;
      btn.textContent = S.runningLive.replace("{CODE}", scenarioCode);
      box.className = "live-output visible";
      box.innerHTML = `<div class="mono" style="font-size:13px;color:var(--green);">${S.callingEndpoint} (${BENCHMARK_DATA.environment.gcp_project})...</div>`;
      try {
        const res = await fetch("/api/verify-scenario", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ scenario_code: scenarioCode })
        });
        const data = await res.json();
        box.innerHTML = `
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;flex-wrap:wrap;gap:8px;">
            <strong style="color:var(--green);">${S.liveDone} (${escapeHtml(data.scenario_code)})</strong>
            <span class="mono" style="font-size:12.2px;">Latency: <strong>${(data.live_latency_ms / 1000).toFixed(2)} s</strong> · ADK <span class="mono">usage_metadata</span>: <strong>${Number(data.adk_measured_prompt_tokens || 0).toLocaleString()} tok</strong> · Total: <strong>${Number(data.scoped_tokens).toLocaleString()} tok (-${data.token_reduction_pct}%)</strong></span>
          </div>
          <pre class="sql-block" style="margin-bottom:10px;">${escapeHtml(data.generated_sql)}</pre>
          ${data.markdown_table ? `<div style="margin-bottom:10px;">${parseMarkdownTableToHtml(data.markdown_table)}</div>` : ""}
          <div style="font-size:13.5px;">${formatAgentAnswer(data.answer)}</div>
        `;
      } catch (err) {
        box.innerHTML = `<div style="color:var(--red);font-size:13px;">Live execution error: ${escapeHtml(err.message)}</div>`;
      } finally {
        btn.disabled = false;
        btn.textContent = S.btnRunLive.replace("{CODE}", scenarioCode);
      }
    }

    function renderTurnScalingSvg() {
      const S = UI_STRINGS;
      const pts = BENCHMARK_DATA.turn_scaling_curve;
      const W = 560, H = 260, padL = 58, padR = 20, padT = 20, padB = 38;
      const maxY = Math.max(230000, pts[9].monolithic_unscoped * 1.08);
      const xPos = i => padL + (i / (pts.length - 1)) * (W - padL - padR);
      const yPos = v => padT + (1 - v / maxY) * (H - padT - padB);
      const poly = key => pts.map((p, i) => `${xPos(i).toFixed(1)},${yPos(p[key]).toFixed(1)}`).join(" ");

      let grid = "";
      [0, 50000, 100000, 150000, 200000].forEach(val => {
        const y = yPos(val).toFixed(1);
        grid += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="#E8EAED" stroke-width="1"/>`;
        grid += `<text x="${padL - 8}" y="${Number(y) + 4}" text-anchor="end" font-size="10.5" fill="#5F6368" font-family="Roboto Mono">${val === 0 ? "0" : (val / 1000) + "K"}</text>`;
      });

      let xLabels = "";
      pts.forEach((p, i) => {
        if (i % 2 === 0 || i === 9) {
          xLabels += `<text x="${xPos(i).toFixed(1)}" y="${H - 12}" text-anchor="middle" font-size="10.5" fill="#5F6368">T${i + 1}</text>`;
        }
      });

      const svg = `
        <svg viewBox="0 0 ${W} ${H}" width="100%" height="auto" role="img">
          ${grid}
          ${xLabels}
          <polyline fill="none" stroke="#C5221F" stroke-width="2.5" points="${poly('monolithic_unscoped')}"/>
          <polyline fill="none" stroke="#B06000" stroke-width="2.2" stroke-dasharray="5,4" points="${poly('unbounded_raw_history')}"/>
          <polyline fill="none" stroke="#137333" stroke-width="3" points="${poly('proposed_scoped_sliding_window')}"/>
          ${pts.map((p, i) => `<circle cx="${xPos(i).toFixed(1)}" cy="${yPos(p.proposed_scoped_sliding_window).toFixed(1)}" r="3.5" fill="#137333"/>`).join("")}
          <text x="${W - padR - 4}" y="${yPos(pts[9].monolithic_unscoped) - 7}" text-anchor="end" font-size="10.5" font-weight="600" fill="#C5221F">${S.chartLineMono} (${(pts[9].monolithic_unscoped / 1000).toFixed(1)}K)</text>
          <text x="${W - padR - 4}" y="${yPos(pts[9].unbounded_raw_history) - 7}" text-anchor="end" font-size="10.5" font-weight="600" fill="#B06000">${S.chartLineUnbounded} (${(pts[9].unbounded_raw_history / 1000).toFixed(1)}K)</text>
          <text x="${W - padR - 4}" y="${yPos(pts[9].proposed_scoped_sliding_window) - 8}" text-anchor="end" font-size="11" font-weight="700" fill="#137333">${S.chartLineScoped} (${(pts[9].proposed_scoped_sliding_window / 1000).toFixed(1)}K)</text>
        </svg>
      `;
      document.getElementById("svg-turn-chart").innerHTML = svg;
    }

    function renderAdkMeasuredSvg() {
      const S = UI_STRINGS;
      const items = BENCHMARK_DATA.measured_5turn_adk_experiment || [];
      const W = 560, H = 260, padL = 52, padR = 24, padT = 26, padB = 40;
      const maxT = Math.max(8000, ...items.map(r => r.asis_adk_prompt_tokens_measured)) * 1.15;
      const slotW = (W - padL - padR) / Math.max(1, items.length);
      const yPos = v => padT + (1 - v / maxT) * (H - padT - padB);
      const baseY = H - padB;

      let bars = "";
      items.forEach((it, i) => {
        const cx = padL + slotW * i + slotW / 2;
        const yAsis = yPos(it.asis_adk_prompt_tokens_measured);
        const yTobe = yPos(it.tobe_adk_prompt_tokens_measured);
        bars += `<rect x="${(cx - 24).toFixed(1)}" y="${yAsis.toFixed(1)}" width="21" height="${(baseY - yAsis).toFixed(1)}" rx="3" fill="#FAD2CF"/>`;
        bars += `<text x="${(cx - 13.5).toFixed(1)}" y="${(yAsis - 4).toFixed(1)}" text-anchor="middle" font-size="9.5" fill="#C5221F" font-family="Roboto Mono">${(it.asis_adk_prompt_tokens_measured / 1000).toFixed(1)}K</text>`;
        bars += `<rect x="${(cx + 2).toFixed(1)}" y="${yTobe.toFixed(1)}" width="21" height="${(baseY - yTobe).toFixed(1)}" rx="3" fill="#1A73E8"/>`;
        bars += `<text x="${(cx + 12.5).toFixed(1)}" y="${(yTobe - 4).toFixed(1)}" text-anchor="middle" font-size="9.5" font-weight="700" fill="#137333" font-family="Roboto Mono">${(it.tobe_adk_prompt_tokens_measured / 1000).toFixed(1)}K</text>`;
        bars += `<text x="${cx.toFixed(1)}" y="${H - 14}" text-anchor="middle" font-size="11" font-weight="600" fill="#202124">Turn ${it.turn}</text>`;
      });

      const svg = `
        <svg viewBox="0 0 ${W} ${H}" width="100%" height="auto" role="img">
          <line x1="${padL}" y1="${baseY}" x2="${W - padR}" y2="${baseY}" stroke="#DADCE0" stroke-width="1"/>
          <rect x="${padL}" y="4" width="12" height="10" rx="2" fill="#FAD2CF"/>
          <text x="${padL + 17}" y="13" font-size="11" fill="#5F6368">${S.barLegendMono}</text>
          <rect x="${padL + 205}" y="4" width="12" height="10" rx="2" fill="#1A73E8"/>
          <text x="${padL + 222}" y="13" font-size="11" fill="#5F6368">${S.barLegendScoped}</text>
          ${bars}
        </svg>
      `;
      document.getElementById("svg-adk-measured-chart").innerHTML = svg;
    }

    function updateTcoCalculator() {
      const S = UI_STRINGS;
      const qpd = Number(document.getElementById("rng-qpd").value);
      const turns = Number(document.getElementById("rng-turns").value);
      const cachePct = Number(document.getElementById("rng-cache").value);
      const cacheRatio = cachePct / 100.0;

      document.getElementById("lbl-qpd").textContent = `${qpd.toLocaleString()} queries / day`;
      document.getElementById("lbl-turns").textContent = `${turns} turn${turns > 1 ? "s" : ""}`;
      document.getElementById("lbl-cache").textContent = `${cachePct}% cached prefix ($0.30/1M)`;

      const curve = BENCHMARK_DATA.turn_scaling_curve.slice(0, turns);
      const avgAdkAsis = Math.round(curve.reduce((s, r) => s + r.adk_asis_prompt_tokens, 0) / turns);
      const avgAdkTobe = Math.round(curve.reduce((s, r) => s + r.adk_tobe_prompt_tokens, 0) / turns);
      const avgBqcaMono = Math.round(curve.reduce((s, r) => s + r.bqca_monolithic_tokens, 0) / turns);
      const avgBqcaTobe = Math.round(curve.reduce((s, r) => s + r.bqca_tobe_scoped_tokens, 0) / turns);

      // Official PAYG rates
      const BQ_NON_CACHE = 3.00, BQ_CACHED = 0.30, BQ_OUT = 20.00;
      const VX_IN = 0.30, VX_OUT = 2.50;

      const perTurnAsisNoCache =
        (avgAdkAsis / 1e6) * VX_IN + (900 / 1e6) * VX_OUT +
        (avgBqcaMono / 1e6) * BQ_NON_CACHE + (2200 / 1e6) * BQ_OUT;

      const perTurnAsisCached =
        (avgAdkAsis / 1e6) * VX_IN + (900 / 1e6) * VX_OUT +
        ((avgBqcaMono * (1 - cacheRatio)) / 1e6) * BQ_NON_CACHE +
        ((avgBqcaMono * cacheRatio) / 1e6) * BQ_CACHED +
        (2200 / 1e6) * BQ_OUT;

      const perTurnTobeCached =
        (avgAdkTobe / 1e6) * VX_IN + (450 / 1e6) * VX_OUT +
        ((avgBqcaTobe * (1 - cacheRatio)) / 1e6) * BQ_NON_CACHE +
        ((avgBqcaTobe * cacheRatio) / 1e6) * BQ_CACHED +
        (1050 / 1e6) * BQ_OUT;

      const annualQueries = qpd * 365;
      const yrAsisNoCache = annualQueries * perTurnAsisNoCache;
      const yrAsisCached = annualQueries * perTurnAsisCached;
      const yrTobeCached = annualQueries * perTurnTobeCached;
      const netSavings = yrAsisCached - yrTobeCached;
      const pct = ((1 - yrTobeCached / yrAsisCached) * 100).toFixed(1);

      const fmtUsd = v => "$" + Math.round(v).toLocaleString();
      document.getElementById("tco-annual-savings").textContent = `${fmtUsd(netSavings)} / yr`;
      document.getElementById("tco-pct-note").textContent = S.tcoPctTemplate.replace("{PCT}", pct);
      document.getElementById("tco-asis-nocache").textContent = fmtUsd(yrAsisNoCache);
      document.getElementById("tco-asis-cached").textContent = fmtUsd(yrAsisCached);
      document.getElementById("tco-tobe-cached").textContent = fmtUsd(yrTobeCached);
      document.getElementById("tco-mono-tok").textContent = `${(avgAdkAsis + avgBqcaMono).toLocaleString()} tok/turn`;
      document.getElementById("tco-scoped-tok").textContent = `${(avgAdkTobe + avgBqcaTobe).toLocaleString()} tok/turn`;
    }

    function initPortal() {
      const S = UI_STRINGS;
      document.getElementById("bench-ts").textContent = BENCHMARK_DATA.generated_at_utc;
      renderHeroKpis();

      document.querySelectorAll("#diagram-tabs .tab-btn").forEach(btn => {
        btn.addEventListener("click", () => {
          document.querySelectorAll("#diagram-tabs .tab-btn").forEach(b => b.classList.remove("active"));
          btn.classList.add("active");
          const f = S.figures[btn.dataset.fig];
          document.getElementById("fig-img").src = f.src;
          document.getElementById("fig-title").textContent = f.title;
          document.getElementById("fig-caption").textContent = f.caption;
        });
      });

      const modal = document.getElementById("fig-modal");
      const openModal = () => {
        document.getElementById("modal-img").src = document.getElementById("fig-img").src;
        document.getElementById("modal-title").textContent = document.getElementById("fig-title").textContent;
        modal.classList.add("open");
      };
      document.getElementById("zoom-fig-btn").addEventListener("click", openModal);
      document.getElementById("fig-img").addEventListener("click", openModal);
      document.getElementById("close-modal-btn").addEventListener("click", () => modal.classList.remove("open"));
      modal.addEventListener("click", e => { if (e.target === modal) modal.classList.remove("open"); });
      document.addEventListener("keydown", e => { if (e.key === "Escape") modal.classList.remove("open"); });

      const tabContainer = document.getElementById("scenario-tabs");
      BENCHMARK_DATA.scenarios.forEach((sc, idx) => {
        const b = document.createElement("button");
        b.className = "tab-btn" + (idx === 0 ? " active" : "");
        b.textContent = S.shortTitles[sc.code] || sc.code;
        b.addEventListener("click", () => renderScenario(idx));
        tabContainer.appendChild(b);
      });

      renderScenario(0);
      renderTurnScalingSvg();
      renderAdkMeasuredSvg();
      updateTcoCalculator();

      ["rng-qpd", "rng-turns", "rng-cache"].forEach(id => {
        document.getElementById(id).addEventListener("input", updateTcoCalculator);
      });

      if (window.location.protocol.startsWith("http")) {
        fetch("/api/health").then(r => r.ok ? r.json() : null).then(d => {
          if (d && d.status === "ok") {
            liveApiAvailable = true;
            document.getElementById("live-status-text").textContent = S.liveConnected.replace("{PROJ}", d.project_id);
            renderScenario(activeScenarioIdx);
          }
        }).catch(() => {});
      }
    }

    initPortal();
"""


UI_EN = {
    "heroKpis": {
        "k1Label": "S1 · 2-Tier Input Token Diet",
        "k2Label": "S4 · ADK Upstream Compaction",
        "k3Label": "S3 · Parallel & Peer Routing",
        "k4Label": "S5 · Cross-Session Short-Circuit",
        "fasterWord": "Faster",
    },
    "figures": {
        "fig1": {
            "src": "./diagrams/fig1_3tier_system_architecture.svg",
            "title": "Fig 1. End-to-End 3-Tier Enterprise System Architecture",
            "caption": "Tier 1 (ADK Root Orchestrator, ContextCacheConfig & 4-Scope State/Memory) → Tier 2 (3 Domain-Scoped Stateless BigQuery CAA Agents) → Tier 3 (BigQuery Warehouse & Hop-1 Glossary).",
        },
        "fig2": {
            "src": "./diagrams/fig2_state_architectures_comparison.svg",
            "title": "Fig 2. Stateless One-Shot vs. Stateful ConversationReference vs. Proposed Hybrid",
            "caption": "Contrasts ADK Default DataAgentToolset (Turn-2 amnesia), Managed ConversationReference (single-agent lock-in), and ADK 3-Turn Window Sliding Window over Stateless Chat API.",
        },
        "fig3": {
            "src": "./diagrams/fig3_routing_paths_abc.svg",
            "title": "Fig 3. Root-to-SubAgent 3-Way Hybrid Routing (Paths A, B, C)",
            "caption": "Path A: Static enum transfer_to_agent | Path B: Direct Peer-to-Peer Handoff | Path C: Lock-Free ThreadPoolExecutor Concurrent Chat API Fan-Out.",
        },
        "fig4": {
            "src": "./diagrams/fig4_token_diet_4scope_lifecycle.svg",
            "title": "Fig 4. ADK 4-Scope State Lifecycle & 2-Tier Token Diet",
            "caption": "Combines Turn Scope (temp) auto-eviction, before_model_callback 3-turn ADK compaction, 3-Turn Window BQCA window, and MemoryService short-circuiting.",
        },
    },
    "shortTitles": {
        "S1": "S1 · Routing & Schema Diet (A/B)",
        "S2": "S2 · Stateless 3-Turn Window Multi-Turn (A/B)",
        "S3": "S3 · Peer Switch & Parallel Fan-Out",
        "S4": "S4 · 5-Turn ADK usage_metadata & 90% Cache",
        "S5": "S5 · 4-Scope State & 0-Token Recall",
    },
    "scenarioBadge": "Empirical A/B Verification",
    "challengeLabel": "As-Is PoC Bottleneck",
    "mechanismLabel": "To-Be Best Practice Mechanism",
    "promptLabel": "Verification Input Prompt",
    "metricScoped": "Combined 2-Tier Input Tokens",
    "metricLatency": "Wall-Clock Latency",
    "vsSeq": "vs seq",
    "returnedRows": "Returned BigQuery Result Rows (To-Be)",
    "caaSummary": "Analytical Summary",
    "viewDomainSql": "View Generated Domain SQL",
    "s3ParallelHeading": "3 Concurrent Stateless Chat API Calls (ThreadPoolExecutor(max_workers=3))",
    "s3SynthesisHtml": "<strong>Cross-Domain Synthesis:</strong> Concurrent execution across all 3 isolated CAA agents resolved the root cause in one turn—connecting strong VIP demand (<strong>180 orders / $44,100</strong>) with <strong>Nordic Luxe's 50.0% return spike ($7,200 vs $11,520 profit)</strong> and <strong>Memphis TN (DC #1)'s 6.0-day delivery delay</strong> without ConversationReference lock-in.",
    "s4TableHeading": "Live 5-Turn Measured Vertex AI usage_metadata.prompt_token_count",
    "s4CostHeading": "Effective Per-Turn Cost Including 90% BQCA Cached Input ($0.30/1M)",
    "s4CacheExplain": "Static DataAgent instructions & scoped DDL prefixes hit BQCA's 90% Cached Input rate ($0.30/1M vs $3.00/1M non-cached), while App(context_cache_config=...) isolates per-agent ADK caches across transfers.",
    "s5JsonHeading": "Live 4-Scope Session.state JSON Diff (Session A → Brand-New Session B)",
    "memoryRecallOutput": "Session-B Turn 1 Zero-Scan Recall Output",
    "btnRunLive": "Re-Run {CODE} Live on GCP",
    "btnRunDisabled": "Live Re-Run Available on Cloud Run Deployment",
    "runningLive": "Executing {CODE} Live on GCP...",
    "callingEndpoint": "Calling Vertex AI ADK + geminidataanalytics.googleapis.com/v1 live",
    "liveDone": "Live GCP Verification Complete",
    "liveConnected": "Live GCP Connected ({PROJ})",
    "chartLineMono": "As-Is Monolithic + Unbounded",
    "chartLineUnbounded": "Scoped + Unbounded Raw",
    "chartLineScoped": "To-Be 2-Tier O(1) Ceiling",
    "barLegendMono": "As-Is Unbounded ADK Prompt",
    "barLegendScoped": "To-Be Compacted ADK Prompt",
    "tcoPctTemplate": "{PCT}% net reduction in annual effective PAYG spend (even after 90% cache discount on both!)",
    "domainNames": {
        "Customer CRM & Marketing Funnel": "Customer CRM & Marketing Funnel",
        "Product, Margin & Return Analytics": "Product, Margin & Return Analytics",
        "Supply Chain, Inventory & Fulfillment": "Supply Chain, Inventory & Fulfillment",
    },
}


UI_KO = {
    "heroKpis": {
        "k1Label": "S1 · 2-Tier 통합 Input Token 절감",
        "k2Label": "S4 · 상위 ADK 실측 압축 효과",
        "k3Label": "S3 · Peer 전환 및 병렬 가속",
        "k4Label": "S5 · 신규 Session 0-Token 우회",
        "fasterWord": "단축",
    },
    "figures": {
        "fig1": {
            "src": "./diagrams/fig1_3tier_system_architecture.svg",
            "title": "Fig 1. End-to-End 3-Tier Enterprise System Architecture",
            "caption": "Tier 1 (ADK Root Orchestrator, ContextCacheConfig 및 4-Scope State/Memory) → Tier 2 (3개 Domain-Scoped Stateless BigQuery CAA) → Tier 3 (BigQuery 및 Hop-1 Glossary).",
        },
        "fig2": {
            "src": "./diagrams/fig2_state_architectures_comparison.svg",
            "title": "Fig 2. One-Shot Stateless vs 관리형 ConversationReference vs 제안 Hybrid 비교",
            "caption": "ADK 기본 Toolset(2턴 문맥 유실), 단일 DataAgent 종속형 ConversationReference, 그리고 Stateless Chat API 위 ADK 3-Turn Window Sliding Window의 구조적 차이를 대조합니다.",
        },
        "fig3": {
            "src": "./diagrams/fig3_routing_paths_abc.svg",
            "title": "Fig 3. Root-to-SubAgent 3-Way Hybrid Routing (Path A, B, C)",
            "caption": "Path A: 정적 enum transfer_to_agent | Path B: Sub-Agent 간 직접 Peer 전환(Root 생략) | Path C: 무잠금 ThreadPoolExecutor 동시 병렬 Fan-out.",
        },
        "fig4": {
            "src": "./diagrams/fig4_token_diet_4scope_lifecycle.svg",
            "title": "Fig 4. ADK 4-Scope State 수명주기 및 2-Tier Token Diet 구조",
            "caption": "Turn Scope (temp) 즉시 소거, before_model_callback 3-Turn 이력 압축, 3-Turn Window BQCA Window, MemoryService 우회가 결합되어 전 구간 Token 상한선을 고정합니다.",
        },
    },
    "shortTitles": {
        "S1": "S1 · Routing 경량화 & Schema 분리 (A/B)",
        "S2": "S2 · Stateless 3-Turn Window Multi-Turn 검증 (A/B)",
        "S3": "S3 · Peer 직접 전환 & 병렬 Fan-out",
        "S4": "S4 · 5-Turn ADK 실측 & 90% Cache 비용",
        "S5": "S5 · 4-Scope State 격리 & 0-Token 복원",
    },
    "scenarioBadge": "As-Is vs To-Be 실측 대조",
    "challengeLabel": "고객 As-Is 문제상황 (Bottleneck)",
    "mechanismLabel": "제안 To-Be Best Practice 해결 구조",
    "promptLabel": "실측 검증 입력 Prompt (영문 원본)",
    "metricScoped": "2-Tier 합산 Input Token",
    "metricLatency": "실측 벽시계 Latency",
    "vsSeq": "순차 합계",
    "returnedRows": "To-Be 반환 BigQuery Result Table",
    "caaSummary": "검증 결과 해설",
    "viewDomainSql": "생성된 Domain SQL 펼치기",
    "s3ParallelHeading": "3개 Stateless Chat API 동시 병렬 호출 결과 (ThreadPoolExecutor(max_workers=3))",
    "s3SynthesisHtml": "<strong>복합 원인 병렬 분석 검증:</strong> 단일 대화방 종속(ConversationReference) 없이 3개 격리 CAA Agent를 동시에 병렬 호출하여, 견조한 VIP 수요(<strong>180건 / $44,100</strong>) 속에서도 <strong>Nordic Luxe의 50.0% 반품 급증($7,200 vs $11,520 이익)</strong>이 <strong>Memphis TN(DC #1)의 평균 6.0일 배송 지연</strong>과 직결됨을 단일 Turn 만에 규명했습니다.",
    "s4TableHeading": "5-Turn 연속 Vertex AI usage_metadata.prompt_token_count 실측 대조표",
    "s4CostHeading": "BQCA 90% Cached Input($0.30/1M) 반영 Turn-5 실효 비용 비교",
    "s4CacheExplain": "정적 DataAgent 지침과 최소 권한 Schema Prefix를 고정해 BQCA 90% Cached Input 할인($3.00/1M → $0.30/1M)을 극대화하고, ADK App(context_cache_config=...)으로 Sub-Agent 전환 시에도 개별 Agent Cache를 유지합니다.",
    "s5JsonHeading": "실시간 4-Scope Session.state JSON Diff (Session A → 신규 Session B)",
    "memoryRecallOutput": "신규 Session-B 첫 Turn 무스캔(0-Token BQCA) 응답 결과",
    "btnRunLive": "GCP에서 {CODE} 실시간 재실행 검증",
    "btnRunDisabled": "Cloud Run 배포 URL에서 실시간 재실행 가능",
    "runningLive": "GCP에서 {CODE} 실시간 실행 및 usage_metadata 계측 중...",
    "callingEndpoint": "Vertex AI ADK + geminidataanalytics.googleapis.com/v1 실시간 호출 중",
    "liveDone": "실시간 GCP 재실행 및 계측 완료",
    "liveConnected": "실시간 GCP 연결됨 ({PROJ})",
    "chartLineMono": "As-Is 통합 + 무제한 누적",
    "chartLineUnbounded": "Schema 분리 + 원본 누적",
    "chartLineScoped": "To-Be 2-Tier O(1) 상한선",
    "barLegendMono": "As-Is 무제한 ADK 실측 Prompt",
    "barLegendScoped": "To-Be 3-Turn 압축 ADK 실측 Prompt",
    "tcoPctTemplate": "양측 모두 동일 90% Cache 할인을 적용한 후에도 연간 실효 PAYG 비용 {PCT}% 순절감",
    "domainNames": {
        "Customer CRM & Marketing Funnel": "Domain 1 · 고객 CRM 및 마케팅 Funnel",
        "Product, Margin & Return Analytics": "Domain 2 · 상품 Margin 및 반품 분석",
        "Supply Chain, Inventory & Fulfillment": "Domain 3 · 물류센터(DC) 및 재고·배송",
    },
}


KO_SCENARIO_OVERRIDES = {
    "S1": {
        "track": "과제 1 (Routing 경량화) + 과제 2 (Schema Token Diet)",
        "title": "런타임 Discovery 호출 제거 및 최소 권한 Domain 분리 (As-Is vs To-Be 대조)",
        "challenge": "As-Is 구조에서는 매 Turn Agent 목록·전체 Schema 탐색 Tool을 반복 호출하고 모든 Warehouse Table을 단일 CAA에 묶어 110K+ BQCA Token이 소모되며, VIP 기준도 임의 추측(spend >= 100)합니다.",
        "architecture_mechanism": "불필요한 Discovery Tool을 제거하고 정적 enum transfer_to_agent로 즉시 위임하며, 고객 CRM 4개 Table 격리 + Hop-1 VIP 수식(SUM(sale_price) >= 500 OR orders >= 5)으로 ADK 실측 Token과 BQCA Token을 동시 절감합니다.",
        "asis_label": "As-Is: 런타임 Discovery 호출 + 비분리 통합 CAA",
        "asis_defect": "전체 7개 Table Metadata + THOUGHT 원문 주입 및 spend >= 100 임의 추측",
        "state_transition": {
            "temp_scope": "THOUGHT 스트림 제거 후 상위 20행 요약만 반환, 원본은 Turn Scope (temp) 저장 후 Turn 종료 즉시 소거",
            "session_scope": "compact_routing_digest(1줄 요약) + domain_ca_multiturn_messages 2개 메시지 기록",
            "user_scope": "user:profile 및 선호 KPI Template 변수 주입 유지",
        },
        "answer_ko": "정적 enum transfer_to_agent 위임과 4개 격리 Table + Hop-1 VIP 공식이 적용된 **To-Be Customer CAA** 실행 결과입니다.\n\n### As-Is 대비 핵심 개선 검증\n- **2-Tier Token 동시 절감**: 상위 Vertex AI ADK usage_metadata 실측 Prompt Token이 절반 이하로 줄었고, 하위 BQCA Schema 입력도 110,764 tok에서 11,439 tok 수준으로 대폭 축소되었습니다.\n- **결정론적 SQL 생성**: 좌측 As-Is SQL은 user_total_spend >= 100을 임의 추측했으나, 우측 To-Be SQL은 Hop-1 공식(HAVING SUM(sale_price) >= 500 OR COUNT(DISTINCT order_id) >= 5)을 정확히 강제해 **Search(VIP 24명, $17,640.00, AOV $245.00)** 등 정확한 지표를 산출했습니다.",
    },
    "S2": {
        "track": "과제 1 (Stateless Chat API 위 Multi-Turn 문맥 유지)",
        "title": "내장 ask_data_agent One-Shot 문맥 유실 해결 (1 Message 실패 vs ADK 3-Turn Window 성공 대조)",
        "challenge": "ADK 기본 내장 ask_data_agent는 매 호출 1 UserMessage만 전송하므로, 2턴 후속 질문('이전 결과 Column을 그대로 유지하고 14일 장바구니 이탈률을 결합해줘')에서 1턴 VIP 조건을 완전히 잃어버립니다.",
        "architecture_mechanism": "단일 Agent 종속을 피하기 위해 BQCA 호출은 Stateless(Chat API)로 유지하되, ADK Session.state에서 최근 3턴(3-Turn Window 요약 문답)만 Slicing 주입하여 단 +250 tok 내외로 선행 문맥을 100% 보존합니다.",
        "asis_label": "As-Is: ADK 기본 One-Shot ask_data_agent (1 Message 전송 → 문맥 유실)",
        "asis_defect": "1턴 '30일 VIP 고객수·매출·AOV' 조건이 완전히 누락된 채 events 단독 조회 SQL 생성!",
        "state_transition": {
            "temp_scope": "Turn 1 원본 행 자동 해제 완료, Turn 2 결합 결과 5행 미리보기 Buffering",
            "session_scope": "총 3개 요약 메시지(Turn 1 문답 2개 + Turn 2 질문 1개) 전송, 3-Turn Window 상한선 유지",
            "user_scope": "변경 없음",
        },
        "answer_ko": "좌측 **As-Is One-Shot SQL**과 우측 **To-Be 3-Turn Window Sliding Window SQL**의 극명한 차이를 확인하십시오.\n\n### Multi-Turn 문맥 유지 검증 결과\n- **좌측 As-Is SQL (문맥 유실 재현)**: Turn 2 질문만 단독 수신했기 때문에 직전 Turn의 30일 VIP 고객 수·총매출·AOV Column이 무엇인지 알지 못해 events Table만 단독 집계했습니다.\n- **우측 To-Be SQL (문맥 완벽 승계)**: domain_ca_multiturn_messages (3-Turn Window)로 전달된 Turn 1 문맥을 참조하여 vip_last_30_days CTE와 cart_abandonment_14_days CTE를 FULL OUTER JOIN으로 정확히 결합했습니다.",
    },
    "S3": {
        "track": "과제 1 (Stateful 종속 탈피 Peer 전환 및 무잠금 병렬 Fan-out)",
        "title": "1 Conversation = 1 DataAgent 종속 돌파 (Sub-Agent 간 직접 Peer 전환 + 3-Domain 병렬 실행)",
        "challenge": "관리형 Stateful ConversationReference는 대화방이 단일 DataAgent에 고정되어 마케팅 분석 중 물류 질문으로 전환할 수 없으며, 다중 Domain 질문을 순차 실행하면 대기 시간이 ~35~50초로 지연됩니다.",
        "architecture_mechanism": "Part A에서는 활성 customer_marketing_subagent가 Root 재경유 없이 supply_chain_subagent로 직접 Peer 전환(LLM 1-Hop 절약)하고, Part B에서는 ThreadPoolExecutor(3)로 3개 무상태 Chat API을 동시 병렬 실행합니다.",
        "state_transition": {
            "temp_scope": "3개 병렬 Domain의 20행 요약 Markdown Table을 단일 종합 응답 Turn으로 병합",
            "session_scope": "병렬 실행 전 Snapshot 읽기 후 Main Thread에서 3개 Domain 3-Turn Window 이력을 안전하게 일괄 갱신",
            "user_scope": "핵심 이상 징후(Nordic Luxe 반품률 50.0% ↔ Memphis TN DC #1 배송 6.0일 지연) 자동 고정",
        },
        "sub_summaries_ko": {
            "Customer CRM & Marketing Funnel": "최근 30일 신규 Cohort(order_id >= 9900000) 기준 **고유 VIP 주문 180건**, 총 주문액 **$44,100.00**으로 수요 자체는 견조합니다.",
            "Product, Margin & Return Analytics": "양대 Brand 모두 단위 Margin 비율은 **56.41%**로 동일하나, **Nordic Luxe 반품·취소율이 50.0%**(실현 이익 **$7,200**)로 **TheLook Atelier(20.0%, $11,520)** 대비 급감했습니다.",
            "Supply Chain, Inventory & Fulfillment": "여성 아우터웨어 출고분에서 **Memphis TN(DC #1)** 평균 배송 소요일이 **6.0일**(미판매 재고 **$68,178.28**)로 **Chicago IL(DC #2, 2.0일)** 대비 3배 지연되었습니다.",
        },
    },
    "S4": {
        "track": "과제 2 핵심 (5-Turn 연속 Vertex AI usage_metadata 실측 + 90% Cache 실효 비용)",
        "title": "상위 ADK + 하위 BQCA 양방향 O(1) Token 평탄화 및 90% Cached Input 비용 시현",
        "challenge": "하위 BQCA만 Sliding Window로 줄이더라도, 상위 ADK LlmAgent의 기본 설정(include_contents='default')은 매 Turn 과거 원본 JSON과 THOUGHT 로그 전체를 재전송하여 ADK Prompt Token이 계속 폭증합니다.",
        "architecture_mechanism": "5단계 2-Tier Token Diet(탐색 제거 + Table 격리 + THOUGHT 절삭·20행 캡 + ADK before_model_callback 3-Turn 압축 + BQCA 3-Turn Window 및 90% Cached Input $0.30/1M)를 동시 적용해 전 구간 O(1) 상한선을 달성합니다.",
        "state_transition": {
            "temp_scope": "before_model_callback이 오래된 Content 항목을 자동 절삭하여 상위 ADK 이력 폭증 원천 차단",
            "session_scope": "상위 ADK(3 User Turns) 및 하위 BQCA(6-Message Window) 양방향 모두 평탄한 O(1) 상한선 고정",
            "user_scope": "compact_routing_digest를 최대 3줄(<90 tok)로 유지하여 SQL 중복 주입 누수 완전 제거",
        },
    },
    "S5": {
        "track": "과제 1 (4-Scope State 격리) + 과제 2 (0-Token BQCA Memory 단락 회로)",
        "title": "4-Scope Session.state 수명주기 격리 및 신규 Session 0-Token BQCA 즉시 복원",
        "challenge": "분석가가 'New Session'을 열 때마다 이전 대화 맥락과 직무 선호도가 초기화되면, 어제 이미 규명한 원인을 확인하기 위해 다시 110K~248K Token 규모의 BQCA SQL을 재실행해야 합니다.",
        "architecture_mechanism": "Turn Scope (temp)(단일 Turn 휘발), session(대화방 요약), User Scope (user)(사용자 영속 Profile/인사이트), App Scope (app)(전역 집계) 4단계를 엄격히 분리하고 ADK MemoryService로 색인하여 새 Session 첫 Turn에 BQCA 호출 0회로 즉시 응답합니다.",
        "state_transition": {
            "temp_scope": "Session A 종료 후 Turn Scope (temp) 키 0개 잔류 검증 완료 / Session B BigQuery 스캔 0 Bytes",
            "session_scope": "완전히 새로운 Session ID(session-B, Turn 1)에서 시작",
            "user_scope": "Session A에서 고정한 직무 Role 및 Nordic Luxe 50.0% 반품 ↔ Memphis TN 6.0일 지연 원인 즉시 복원",
        },
        "answer_ko": "완전히 새로운 Session(session-B, Turn 1)에서 **하위 BQCA 호출 0회 / BigQuery 스캔 0 Bytes**만으로 응답한 결과입니다.\n\n### 4-Scope State 격리 및 장기 Memory 단락 회로 검증\n- **Turn Scope (temp) 휘발 검증**: 좌측 JSON Diff에서 확인되듯 session-A의 대용량 임시 행 데이터는 영속 상태에 남지 않고 깔끔히 소거되었습니다.\n- **User Scope (user) & MemoryService 복원**: Principal Supply Chain & Merchandising Analyst 직무 설정과 선행 핵심 원인(**Nordic Luxe 50.0% 반품 급증 ↔ Memphis TN DC #1 6.0일 배송 병목**)을 즉시 인출하여 맞춤형 조치 방안 2가지를 제시했습니다.",
    },
}


def build_ko_benchmark_data(en_data: dict) -> dict:
    ko_data = copy.deepcopy(en_data)
    for sc in ko_data["scenarios"]:
        ov = KO_SCENARIO_OVERRIDES.get(sc["code"])
        if not ov:
            continue
        sc["track"] = ov["track"]
        sc["title"] = ov["title"]
        sc["challenge"] = ov["challenge"]
        sc["architecture_mechanism"] = ov["architecture_mechanism"]
        sc["state_transition"] = ov["state_transition"]
        if "asis_comparison" in sc:
            if "asis_label" in ov:
                sc["asis_comparison"]["label"] = ov["asis_label"]
            if "asis_defect" in ov:
                sc["asis_comparison"]["defect_note"] = ov["asis_defect"]
        if "answer_ko" in ov:
            sc["measured_result"]["answer"] = ov["answer_ko"]
        if "sub_summaries_ko" in ov and "sub_results" in sc["measured_result"]:
            for dom_key, ko_sum in ov["sub_summaries_ko"].items():
                if dom_key in sc["measured_result"]["sub_results"]:
                    sc["measured_result"]["sub_results"][dom_key]["summary"] = ko_sum
    return ko_data


def render_page(template: str, data_obj: dict, ui_obj: dict) -> str:
    return (
        template.replace("__SHARED_CSS__", SHARED_CSS)
        .replace("__BENCHMARK_JSON_PAYLOAD__", json.dumps(data_obj, ensure_ascii=False))
        .replace("__UI_STRINGS_PAYLOAD__", json.dumps(ui_obj, ensure_ascii=False))
        .replace("__PORTAL_JS__", PORTAL_JS)
    )


def main() -> None:
    en_data = json.loads(BENCHMARK_JSON.read_text(encoding="utf-8"))
    ko_data = build_ko_benchmark_data(en_data)

    html_en = render_page(HTML_EN, en_data, UI_EN)
    html_ko = render_page(HTML_KO, ko_data, UI_KO)

    OUT_HTML_EN.write_text(html_en, encoding="utf-8")
    OUT_HTML_KO.write_text(html_ko, encoding="utf-8")
    print(f"[OK] Generated EN portal: {OUT_HTML_EN} ({len(html_en):,} bytes)")
    print(f"[OK] Generated KO portal: {OUT_HTML_KO} ({len(html_ko):,} bytes)")


if __name__ == "__main__":
    main()
