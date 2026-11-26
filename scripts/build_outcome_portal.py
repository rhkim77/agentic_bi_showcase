#!/usr/bin/env python3
"""Generates both:
  1. `docs/index.html`    — English PoC Architecture, 2-Tier Token Diet & Outcome Verification Portal
  2. `docs/index_ko.html` — Korean Verification Portal (all technical nouns in original English)
from `benchmarks/scenario_benchmark_results.json`, featuring:
  - Live `As-Is` vs `To-Be` A/B comparisons across Scenarios S1–S5
  - Real `Vertex AI usage_metadata` (`prompt_token_count`) measurements
  - Token development over the S4 session and a list-price cost calculator, both from measured data
"""

from __future__ import annotations

import copy
import json
import re
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

    /* Progressive S1->S5 Architecture & Live Token Tracker */
    .prog-tracker-card {
      background: var(--surface);
      border: 1px solid #C2D7FA;
      border-top: 4px solid var(--blue);
      border-radius: var(--radius);
      padding: 20px 22px;
      margin-bottom: 18px;
      box-shadow: var(--shadow-sm);
      width: 100%;
      min-width: 0;
    }
    .prog-tracker-head {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
      flex-wrap: wrap;
      margin-bottom: 14px;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--surface-subtle);
    }
    .prog-step-strip {
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 8px;
      margin-bottom: 16px;
    }
    @media (max-width: 960px) { .prog-step-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
    @media (max-width: 560px) { .prog-step-strip { grid-template-columns: minmax(0, 1fr); } }
    .prog-step-pill {
      border: 1px solid var(--border);
      background: var(--bg);
      border-radius: 8px;
      padding: 10px 12px;
      cursor: pointer;
      transition: all 0.15s;
      min-width: 0;
    }
    .prog-step-pill:hover { border-color: var(--blue); }
    .prog-step-pill.active-step {
      border-color: var(--blue);
      background: #F4F8FE;
      box-shadow: 0 1px 4px rgba(26, 115, 232, 0.16);
    }
    .prog-step-pill.live-done {
      border-color: #86EFAC;
      background: #F0FDF4;
    }
    .prog-bar-rows {
      display: flex;
      flex-direction: column;
      gap: 10px;
      width: 100%;
    }
    .prog-bar-row {
      display: grid;
      grid-template-columns: 185px minmax(0, 1fr) 195px;
      gap: 12px;
      align-items: center;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 9px 13px;
      font-size: 12.5px;
    }
    @media (max-width: 860px) {
      .prog-bar-row { grid-template-columns: minmax(0, 1fr); gap: 6px; }
    }
    .dual-bar-track {
      display: flex;
      flex-direction: column;
      gap: 5px;
      width: 100%;
      min-width: 0;
    }
    .bar-line {
      display: flex;
      align-items: center;
      gap: 8px;
      width: 100%;
    }
    .bar-fill-asis {
      height: 8px;
      background: #EA4335;
      border-radius: 4px;
      min-width: 4px;
      transition: width 0.35s ease;
    }
    .bar-fill-tobe {
      height: 8px;
      background: #137333;
      border-radius: 4px;
      min-width: 4px;
      transition: width 0.35s ease;
    }

    /* Interactive Evaluator Prompt Workbench inside Scenario Detail */
    .workbench-box {
      background: #F4F8FE;
      border: 1px solid #AECBFA;
      border-left: 4px solid var(--blue);
      border-radius: 10px;
      padding: 18px 20px;
      margin-bottom: 20px;
      width: 100%;
      min-width: 0;
    }
    .wb-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      margin-bottom: 10px;
    }
    .preset-row {
      display: flex;
      gap: 7px;
      flex-wrap: wrap;
      margin-bottom: 10px;
    }
    .preset-chip {
      appearance: none;
      border: 1px solid #C2D7FA;
      background: #FFFFFF;
      color: #174EA6;
      font-family: inherit;
      font-size: 12px;
      font-weight: 600;
      padding: 5px 10px;
      border-radius: 999px;
      cursor: pointer;
      text-align: left;
    }
    .preset-chip:hover { background: var(--blue); color: #FFFFFF; border-color: var(--blue); }
    .wb-textarea {
      width: 100%;
      min-height: 78px;
      resize: vertical;
      border: 1px solid var(--border-strong);
      border-radius: 8px;
      padding: 11px 13px;
      font-family: inherit;
      font-size: 13.8px;
      line-height: 1.52;
      color: var(--text);
      background: #FFFFFF;
      margin-bottom: 10px;
    }
    .wb-textarea:focus { outline: 2px solid var(--blue); border-color: var(--blue); }
    .wb-actions {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }
    .wb-btn-group {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
    }
    .btn-next-step {
      appearance: none;
      border: 1px solid var(--blue);
      background: #FFFFFF;
      color: var(--blue);
      font-family: inherit;
      font-size: 12.8px;
      font-weight: 600;
      padding: 8px 14px;
      border-radius: 7px;
      cursor: pointer;
    }
    .btn-next-step:hover { background: var(--blue); color: #FFFFFF; }

    /* Live execution flow */
    .flow-box { margin: 14px 0 12px; background: #FFFFFF; border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px; }
    .flow-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; flex-wrap: wrap; margin-bottom: 8px; }
    .flow-title { font-size: 13.5px; font-weight: 700; }
    .flow-desc { font-size: 12.3px; color: var(--text-secondary); margin-top: 2px; max-width: 860px; }
    .flow-svg-wrap { overflow-x: auto; }
    .flow-svg-wrap svg { width: 100%; min-width: 720px; height: auto; display: block; }
    .flow-status { font-size: 12px; margin-top: 6px; overflow-wrap: anywhere; color: var(--text-secondary); }
    .flow-status b { color: var(--text); }
    .flow-legend { display: flex; gap: 14px; flex-wrap: wrap; font-size: 11.6px; color: var(--text-secondary); margin-top: 8px; }
    .flow-chip { display: inline-block; width: 12px; height: 12px; border-radius: 3px; border: 2px solid #BDC1C6; margin-right: 5px; vertical-align: -2px; background: #FFFFFF; }
    .flow-chip.active { border-color: #1A73E8; background: #E8F0FE; }
    .flow-chip.done { border-color: #34A853; background: #F1F9F3; }
    .lf-node.lf-active .lf-box { stroke: #1A73E8; stroke-width: 3.4; fill: #E8F0FE; animation: lfPulse 1.1s ease-in-out infinite; }
    .lf-node.lf-done .lf-box { stroke: #34A853; stroke-width: 2.4; fill: #F1F9F3; }
    .lf-edge.lf-active .lf-line { stroke: #1A73E8; stroke-width: 3.4; stroke-dasharray: 8 6; animation: lfDash 0.7s linear infinite; }
    .lf-edge.lf-active .lf-head { fill: #1A73E8; }
    .lf-edge.lf-done .lf-line { stroke: #34A853; stroke-width: 2.6; }
    .lf-edge.lf-done .lf-head { fill: #34A853; }
    @keyframes lfPulse { 0%, 100% { stroke-opacity: 1; } 50% { stroke-opacity: 0.3; } }
    @keyframes lfDash { to { stroke-dashoffset: -14; } }

    .sse-log-box {
      background: #1E222A;
      color: #E8EAED;
      border-radius: 8px;
      padding: 12px 15px;
      font-size: 12.2px;
      line-height: 1.55;
      margin-top: 14px;
      max-height: 190px;
      overflow-y: auto;
      width: 100%;
    }
    .sse-item { margin-bottom: 4px; overflow-wrap: anywhere; }
    .sse-tag-asis { color: #FCA5A5; font-weight: 700; }
    .sse-tag-tobe { color: #86EFAC; font-weight: 700; }
    .sse-tag-both { color: #93C5FD; font-weight: 700; }
    .live-dual-card {
      margin-top: 14px;
      background: #FFFFFF;
      border: 2px solid #34A853;
      border-radius: 10px;
      padding: 18px 20px;
      width: 100%;
      min-width: 0;
    }
    .ref-divider {
      display: flex;
      align-items: center;
      gap: 10px;
      margin: 22px 0 14px;
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-secondary);
    }
    .ref-divider::after {
      content: "";
      flex: 1;
      height: 1px;
      background: var(--border);
    }

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
        <a href="#benchmarks">4. Tokens over 8 Turns &amp; Cost</a>
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
          Built for two engineering questions that come up when a Google ADK agent is put in front of BigQuery Conversational Analytics (BQCA):
          <strong>(1) how to handle state, memory and routing between a root agent and BQCA data agents</strong>, and
          <strong>(2) how many tokens each design uses in both tiers</strong>.
          Every number on this page was measured on Google Cloud: ADK tokens from <span class="mono">Vertex AI usage_metadata</span>, BQCA tokens from Cloud Trace.
        </p>

        <div class="meta-strip">
          <span class="meta-chip"><strong>Track 1:</strong> Root and Sub-Agent state · 3-turn message window · memory · routing</span>
          <span class="meta-chip"><strong>Track 2:</strong> Measured tokens in the ADK tier and the BQCA tier</span>
          <span class="meta-chip"><strong>Measured (UTC):</strong> <span class="mono" id="bench-ts"></span></span>
        </div>

        <div class="kpi-grid" id="hero-kpi-grid"></div>
      </div>

      <div class="stack-list" style="margin-top:20px;margin-bottom:0;">
        <div class="info-card">
          <span class="tag tag-blue">PoC objective 1 · State, memory and routing</span>
          <h3>What each setup does</h3>
          <ul style="font-size:13.8px;padding-left:18px;color:var(--text-secondary);margin-top:6px;">
            <li style="margin-bottom:6px;"><strong>Built-in <span class="mono">ask_data_agent</span>:</strong> looks up the data agent on every call and sends only the current question to BQCA.</li>
            <li style="margin-bottom:6px;"><strong>Managed conversation (<span class="mono">ConversationReference</span>):</strong> keeps history on the server but is tied to one data agent.</li>
            <li><strong>This repository:</strong> a Root Router with three domain Sub-Agents, direct hand-over between Sub-Agents, parallel fan-out, a 3-turn message window per domain, session state and a memory service.</li>
          </ul>
        </div>

        <div class="info-card">
          <span class="tag tag-green">PoC objective 2 · Token use in both tiers</span>
          <h3>Where the tokens go</h3>
          <ul style="font-size:13.8px;padding-left:18px;color:var(--text-secondary);margin-top:6px;">
            <li style="margin-bottom:6px;"><strong>BQCA tier:</strong> a chat turn usually makes two internal LLM calls, and each call reads the schema and glossary bound to the data agent. Binding fewer documented tables to a data agent is the main lever.</li>
            <li style="margin-bottom:6px;"><strong>ADK tier:</strong> the prompt is the instruction, the tool definitions and the replayed session. The To-Be agents use static instructions, one tool per Sub-Agent, a 3-turn history and reduced tool results.</li>
            <li><strong>Recall:</strong> questions about earlier sessions are answered from memory without a BQCA call.</li>
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
            <tr><th>Dimension</th><th>As-Is: built-in ADK data agent tools</th><th>BQCA managed conversation (stateful)</th><th>To-Be: this repository</th></tr>
          </thead>
          <tbody>
            <tr>
              <td><strong>Routing</strong></td>
              <td>One data agent answers every question</td>
              <td>One data agent per conversation, fixed at creation</td>
              <td><strong>Root Router hands over to one of three Sub-Agents; Sub-Agents hand over to each other; cross-domain questions fan out in parallel</strong></td>
            </tr>
            <tr class="highlight-row">
              <td><strong>Multi-turn context</strong></td>
              <td><span class="mono">ask_data_agent</span> sends only the current question; the root LLM has to restate earlier context</td>
              <td>History is kept on the server for that conversation</td>
              <td><strong>The last 3 turns of the domain are sent with each stateless call</strong></td>
            </tr>
            <tr>
              <td><strong>ADK prompt</strong></td>
              <td>The full session is replayed on every LLM call, including raw tool responses</td>
              <td>Depends on the agent that wraps it</td>
              <td><strong>Last 3 user turns; tool results reduced to the answer and a capped table</strong></td>
            </tr>
            <tr class="highlight-row">
              <td><strong>BQCA context per call</strong></td>
              <td>The whole warehouse schema and every glossary</td>
              <td>Same as the bound data agent</td>
              <td><strong>3 to 5 tables and one domain glossary per data agent (measured in Sections 3 and 4)</strong></td>
            </tr>
            <tr>
              <td><strong>Cross-session memory</strong></td>
              <td>None</td>
              <td>Within one conversation only</td>
              <td><strong>User-scoped state and a memory service; recall without a BQCA call</strong></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section id="scenarios">
      <h2>3. Live As-Is vs. To-Be PoC Scenario Verification &amp; Progressive Workbench (S1 – S5)</h2>
      <p class="section-desc">
        Pre-verified GCP baseline results load immediately below, while the <strong>Interactive Dual A/B Workbench</strong> lets you enter or customize prompts at every step from <strong>S1 to S5</strong> to run both the <strong>As-Is</strong> pipeline (ADK built-in data agent tools on one monolithic data agent) and the <strong>To-Be</strong> pipeline live in parallel on Google Cloud and compare answers, SQL and measured ADK-tier <span class="mono">Vertex AI usage_metadata</span> tokens.
      </p>

      <div class="prog-tracker-card" id="progressive-tracker"></div>
      <div class="tab-bar" id="scenario-tabs"></div>
      <div class="scenario-shell" id="scenario-detail"></div>
    </section>

    <section id="benchmarks">
      <h2>4. Token Development over an 8-Turn Session and Cost at List Prices</h2>
      <p class="section-desc">Measured in the S4 baseline run. Left: total input tokens per turn, that is ADK prompt tokens from <span class="mono">Vertex AI usage_metadata</span> plus BQCA input tokens from Cloud Trace. Right: ADK prompt tokens per turn. Below: yearly cost at list prices, scaled from the measured average cost per turn.</p>

      <div class="two-col" style="margin-bottom: 24px;">
        <div class="info-card">
          <h3>Total Input Tokens per Turn (ADK + BQCA)</h3>
          <div id="svg-turn-chart"></div>
        </div>
        <div class="info-card">
          <h3>ADK Prompt Tokens per Turn</h3>
          <div id="svg-adk-measured-chart"></div>
        </div>
      </div>

      <div class="info-card">
        <div style="margin-bottom:16px;">
          <span class="tag tag-green">Cost at list prices</span>
          <h3>Yearly Cost Scaled from the Measured Average Turn</h3>
        </div>
        <div class="calc-grid">
          <div>
            <div class="slider-group">
              <div class="slider-head">
                <span>Questions per day</span>
                <span class="mono" id="lbl-qpd"></span>
              </div>
              <input type="range" id="rng-qpd" min="1000" max="50000" step="1000" value="10000" />
            </div>
            <p style="font-size:12px;color:var(--text-secondary);margin-top:6px;">Cost per turn = measured ADK tokens and measured BQCA tokens of the S4 session at list prices: BQCA input <span class="mono">$3.00/1M</span>, cached input <span class="mono">$0.30/1M</span>, output <span class="mono">$20.00/1M</span>; <span class="mono">gemini-2.5-flash</span> input <span class="mono">$0.30/1M</span>, cached input <span class="mono">$0.03/1M</span>, output <span class="mono">$2.50/1M</span>. BigQuery query cost is not included. The yearly figure is a linear scaling of that average, not a forecast.</p>
          </div>

          <div class="tco-result-box">
            <div>
              <div style="font-size:12px;font-weight:700;text-transform:uppercase;color:var(--text-secondary);margin-bottom:4px;">Yearly difference (As-Is minus To-Be)</div>
              <div class="savings-big" id="tco-annual-savings">n/a</div>
              <div style="font-size:13px;color:var(--text-secondary);margin-bottom:14px;" id="tco-pct-note"></div>
            </div>
            <div class="tco-tier-strip">
              <div>
                <div style="color:var(--text-secondary);">As-Is per year</div>
                <div class="mono" style="font-weight:700;font-size:15px;color:var(--red);" id="tco-asis"></div>
                <div class="mono" style="font-size:11px;color:var(--text-secondary);" id="tco-asis-turn"></div>
              </div>
              <div>
                <div style="color:var(--text-secondary);">To-Be per year</div>
                <div class="mono" style="font-weight:700;font-size:15px;color:var(--green);" id="tco-tobe"></div>
                <div class="mono" style="font-size:11px;color:var(--text-secondary);" id="tco-tobe-turn"></div>
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
uv run python scripts/provision_enterprise_warehouse.py
uv run python scripts/refresh_demo_seed.py
uv run python scripts/provision_cymbal_caa_agents.py
uv run python scripts/04_run_scenario_benchmarks.py
uv run python scripts/05_measure_bqca_tokens_from_trace.py
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
    const FLOW_MAP = __FLOW_MAP_PAYLOAD__;
    const FLOW_SVG = __FLOW_SVG_PAYLOAD__;
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
        <a href="#benchmarks">4. 8-Turn Token 추이 및 비용</a>
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
          Google ADK Agent를 BigQuery Conversational Analytics(BQCA) 앞에 둘 때 나오는 두 가지 기술 질문을 다룹니다.
          <strong>1) Root Agent와 BQCA Data Agent 사이의 State·Memory·Routing을 어떻게 설계할 것인가</strong>,
          <strong>2) 각 설계가 두 계층에서 Token을 얼마나 쓰는가</strong>.
          이 Page의 모든 수치는 Google Cloud에서 측정했습니다. ADK Token은 <span class="mono">Vertex AI usage_metadata</span>, BQCA Token은 Cloud Trace 기준입니다.
        </p>

        <div class="meta-strip">
          <span class="meta-chip"><strong>과제 1:</strong> Root·Sub-Agent State · 3-Turn Message Window · Memory · Routing</span>
          <span class="meta-chip"><strong>과제 2:</strong> ADK 계층과 BQCA 계층의 Token 실측</span>
          <span class="meta-chip"><strong>측정 시각 (UTC):</strong> <span class="mono" id="bench-ts"></span></span>
        </div>

        <div class="kpi-grid" id="hero-kpi-grid"></div>
      </div>

      <div class="stack-list" style="margin-top:20px;margin-bottom:0;">
        <div class="info-card">
          <span class="tag tag-blue">과제 1 · State, Memory, Routing</span>
          <h3>구성별 동작 방식</h3>
          <ul style="font-size:13.8px;padding-left:18px;color:var(--text-secondary);margin-top:6px;">
            <li style="margin-bottom:6px;"><strong>ADK 내장 <span class="mono">ask_data_agent</span>:</strong> 호출할 때마다 Data Agent 정보를 조회하고, 현재 질문 하나만 BQCA에 보냅니다.</li>
            <li style="margin-bottom:6px;"><strong>관리형 대화 (<span class="mono">ConversationReference</span>):</strong> 이력을 서버에 보관하지만 Data Agent 하나에 묶입니다.</li>
            <li><strong>이 Repository:</strong> Root Router와 Domain별 Sub-Agent 3개, Sub-Agent 간 직접 전환, 병렬 Fan-out, Domain별 3-Turn Message Window, Session State와 Memory Service를 씁니다.</li>
          </ul>
        </div>

        <div class="info-card">
          <span class="tag tag-green">과제 2 · 두 계층의 Token 사용</span>
          <h3>Token이 쓰이는 곳</h3>
          <ul style="font-size:13.8px;padding-left:18px;color:var(--text-secondary);margin-top:6px;">
            <li style="margin-bottom:6px;"><strong>BQCA 계층:</strong> Chat Turn 하나는 보통 내부 LLM 호출 2회로 처리되고, 호출마다 Data Agent에 연결된 Schema와 용어집을 읽습니다. 설명이 붙은 Table을 적게 연결하는 것이 가장 큰 요인입니다.</li>
            <li style="margin-bottom:6px;"><strong>ADK 계층:</strong> Prompt는 Instruction, Tool 정의, 재전송되는 Session으로 이루어집니다. To-Be Agent는 고정 Instruction, Sub-Agent당 Tool 1개, 3-Turn 이력, 축약한 Tool 결과를 씁니다.</li>
            <li><strong>기억 복원:</strong> 이전 Session에 대한 질문은 BQCA 호출 없이 Memory에서 답합니다.</li>
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
            <tr><th>비교 항목</th><th>As-Is: ADK 내장 data agent Tool</th><th>BQCA 관리형 대화 (Stateful)</th><th>To-Be: 이 Repository</th></tr>
          </thead>
          <tbody>
            <tr>
              <td><strong>Routing</strong></td>
              <td>Data Agent 하나가 모든 질문에 답함</td>
              <td>대화 생성 시 정한 Data Agent 하나에 고정</td>
              <td><strong>Root Router가 Sub-Agent 3개 중 하나로 넘기고, Sub-Agent끼리 직접 전환하며, 여러 Domain 질문은 병렬로 호출</strong></td>
            </tr>
            <tr class="highlight-row">
              <td><strong>Multi-Turn 문맥</strong></td>
              <td><span class="mono">ask_data_agent</span>는 현재 질문만 전송하므로 Root LLM이 이전 문맥을 다시 써 줘야 함</td>
              <td>해당 대화의 이력을 서버가 보관</td>
              <td><strong>Stateless 호출마다 해당 Domain의 최근 3 Turn을 함께 전송</strong></td>
            </tr>
            <tr>
              <td><strong>ADK Prompt</strong></td>
              <td>LLM 호출마다 Tool 원본 응답을 포함한 Session 전체를 재전송</td>
              <td>감싸는 Agent 구성에 따름</td>
              <td><strong>최근 3개 User Turn만 유지하고 Tool 결과는 답변과 행 수를 제한한 Table로 축약</strong></td>
            </tr>
            <tr class="highlight-row">
              <td><strong>호출당 BQCA Context</strong></td>
              <td>Warehouse 전체 Schema와 모든 용어집</td>
              <td>연결된 Data Agent와 동일</td>
              <td><strong>Data Agent당 Table 3~5개와 Domain 용어집 하나 (Section 3, 4에서 측정)</strong></td>
            </tr>
            <tr>
              <td><strong>Session 간 Memory</strong></td>
              <td>없음</td>
              <td>한 대화 안에서만 유지</td>
              <td><strong>User Scope State와 Memory Service로 BQCA 호출 없이 복원</strong></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section id="scenarios">
      <h2>3. As-Is 문제 재현 vs To-Be 해결 직접 대조 시현 및 실시간 단계별 Workbench (S1 – S5)</h2>
      <p class="section-desc">
        사전 검증된 기준 실측치(Reference Baseline)가 즉시 표시되며, 각 단계(<strong>S1 → S5</strong>) 입력창에 직접 질문을 수정·입력하여 실행하면 실제 GCP에서 <strong>As-Is</strong>(단일 통합 Data Agent에 ADK 내장 data agent Tool을 그대로 사용)와 <strong>To-Be</strong>가 동시에 실행되며, 답변·SQL과 ADK 계층의 <span class="mono">Vertex AI usage_metadata</span> 실측 Token을 나란히 비교할 수 있습니다.
      </p>

      <div class="prog-tracker-card" id="progressive-tracker"></div>
      <div class="tab-bar" id="scenario-tabs"></div>
      <div class="scenario-shell" id="scenario-detail"></div>
    </section>

    <section id="benchmarks">
      <h2>4. 8-Turn Session의 Token 추이와 공시 단가 기준 비용</h2>
      <p class="section-desc">S4 기준 실행에서 측정한 값입니다. 왼쪽은 Turn별 Input Token 합계로, <span class="mono">Vertex AI usage_metadata</span>의 ADK Prompt Token과 Cloud Trace의 BQCA Input Token을 더한 것입니다. 오른쪽은 Turn별 ADK Prompt Token입니다. 아래는 측정한 Turn당 평균 비용을 공시 단가로 연 단위 환산한 값입니다.</p>

      <div class="two-col" style="margin-bottom: 24px;">
        <div class="info-card">
          <h3>Turn별 Input Token 합계 (ADK + BQCA)</h3>
          <div id="svg-turn-chart"></div>
        </div>
        <div class="info-card">
          <h3>Turn별 ADK Prompt Token</h3>
          <div id="svg-adk-measured-chart"></div>
        </div>
      </div>

      <div class="info-card">
        <div style="margin-bottom:16px;">
          <span class="tag tag-green">공시 단가 기준 비용</span>
          <h3>측정한 평균 Turn 비용의 연간 환산</h3>
        </div>
        <div class="calc-grid">
          <div>
            <div class="slider-group">
              <div class="slider-head">
                <span>하루 질문 수</span>
                <span class="mono" id="lbl-qpd"></span>
              </div>
              <input type="range" id="rng-qpd" min="1000" max="50000" step="1000" value="10000" />
            </div>
            <p style="font-size:12px;color:var(--text-secondary);margin-top:6px;">Turn당 비용은 S4 Session에서 측정한 ADK Token과 BQCA Token에 공시 단가를 곱한 값입니다. BQCA Input <span class="mono">$3.00/1M</span>, Cached Input <span class="mono">$0.30/1M</span>, Output <span class="mono">$20.00/1M</span>, <span class="mono">gemini-2.5-flash</span> Input <span class="mono">$0.30/1M</span>, Cached Input <span class="mono">$0.03/1M</span>, Output <span class="mono">$2.50/1M</span>입니다. BigQuery Query 비용은 포함하지 않았습니다. 연간 값은 평균의 단순 환산이며 예측이 아닙니다.</p>
          </div>

          <div class="tco-result-box">
            <div>
              <div style="font-size:12px;font-weight:700;text-transform:uppercase;color:var(--text-secondary);margin-bottom:4px;">연간 차이 (As-Is - To-Be)</div>
              <div class="savings-big" id="tco-annual-savings">n/a</div>
              <div style="font-size:13px;color:var(--text-secondary);margin-bottom:14px;" id="tco-pct-note"></div>
            </div>
            <div class="tco-tier-strip">
              <div>
                <div style="color:var(--text-secondary);">As-Is 연간</div>
                <div class="mono" style="font-weight:700;font-size:15px;color:var(--red);" id="tco-asis"></div>
                <div class="mono" style="font-size:11px;color:var(--text-secondary);" id="tco-asis-turn"></div>
              </div>
              <div>
                <div style="color:var(--text-secondary);">To-Be 연간</div>
                <div class="mono" style="font-weight:700;font-size:15px;color:var(--green);" id="tco-tobe"></div>
                <div class="mono" style="font-size:11px;color:var(--text-secondary);" id="tco-tobe-turn"></div>
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
uv run python scripts/provision_enterprise_warehouse.py
uv run python scripts/refresh_demo_seed.py
uv run python scripts/provision_cymbal_caa_agents.py
uv run python scripts/04_run_scenario_benchmarks.py
uv run python scripts/05_measure_bqca_tokens_from_trace.py
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
    const FLOW_MAP = __FLOW_MAP_PAYLOAD__;
    const FLOW_SVG = __FLOW_SVG_PAYLOAD__;
    __PORTAL_JS__
  </script>
</body>
</html>
"""



# Ties ADK agent and tool names (as they appear in run events) to element ids of
# docs/diagrams/fig5_live_execution_flow.svg. build_page() checks every id against the SVG.
FLOW_SVG_PATH = REPO_ROOT / "docs" / "diagrams" / "fig5_live_execution_flow.svg"
FLOW_MAP = {
    "tobe": {
        "user": "user",
        "entry": "root",
        "entryEdge": "user--root",
        "agents": {
            "cymbal_enterprise_root_router": "root",
            "customer_marketing_subagent": "sub-customer",
            "product_profitability_subagent": "sub-product",
            "supply_chain_logistics_subagent": "sub-supply",
        },
        "transfers": {
            "root|sub-customer": ["root--sub-customer"],
            "root|sub-product": ["root--sub-product"],
            "root|sub-supply": ["root--sub-supply"],
            "sub-customer|sub-product": ["peer-cp"],
            "sub-product|sub-supply": ["peer-ps"],
            "sub-customer|sub-supply": ["peer-cp", "peer-ps"],
        },
        "tools": {
            "ask_customer_marketing_caa": {"nodes": ["ca-customer", "bq"], "edges": ["sub-customer--ca-customer", "ca-customer--bq"]},
            "ask_product_profitability_caa": {"nodes": ["ca-product", "bq"], "edges": ["sub-product--ca-product", "ca-product--bq"]},
            "ask_supply_chain_logistics_caa": {"nodes": ["ca-supply", "bq"], "edges": ["sub-supply--ca-supply", "ca-supply--bq"]},
            "load_memory": {"nodes": ["mem"], "edges": ["root--mem"]},
            "save_user_preference_and_memory": {"nodes": ["mem"], "edges": ["root--mem"]},
            "inspect_session_and_memory_status": {"nodes": ["mem"], "edges": ["root--mem"]},
        },
        "fanout": {
            "tool": "run_cross_domain_caa_analysis",
            "node": "fan",
            "edge": "root--fan",
            "domains": {
                "customer_marketing": {"nodes": ["ca-customer", "bq"], "edges": ["fan--ca-customer", "ca-customer--bq"]},
                "product_profitability": {"nodes": ["ca-product", "bq"], "edges": ["fan--ca-product", "ca-product--bq"]},
                "supply_chain": {"nodes": ["ca-supply", "bq"], "edges": ["fan--ca-supply", "ca-supply--bq"]},
            },
        },
    },
    "asis": {
        "user": "user",
        "entry": "agent",
        "entryEdge": "user--agent",
        "agents": {"asis_default_data_agent_tools": "agent"},
        "transfers": {},
        "tools": {
            "list_accessible_data_agents": {"nodes": ["tool-list"], "edges": ["agent--tool-list"]},
            "get_data_agent_info": {"nodes": ["tool-info", "ca"], "edges": ["agent--tool-info", "tool-info--ca"]},
            "ask_data_agent": {"nodes": ["tool-ask", "ca", "bq"], "edges": ["agent--tool-ask", "tool-ask--ca", "ca--bq"]},
        },
    },
}


def load_flow_svg() -> str:
    """Returns fig5 as inline SVG markup and checks that every id in FLOW_MAP exists in it."""
    svg = FLOW_SVG_PATH.read_text(encoding="utf-8")
    svg = svg[svg.index("<svg"):]
    head_end = svg.index(">")
    head = re.sub(r'\s(width|height)="[^"]*"', "", svg[:head_end])
    svg = head + ' role="img" aria-label="Live execution flow"' + svg[head_end:]

    def check(side: str, kind: str, ident: str) -> None:
        if f'id="lf-{side}-{kind}-{ident}"' not in svg:
            raise RuntimeError(f"FLOW_MAP refers to missing diagram element lf-{side}-{kind}-{ident}")

    for side, m in FLOW_MAP.items():
        check(side, "n", m["user"])
        check(side, "n", m["entry"])
        check(side, "e", m["entryEdge"])
        for n in m["agents"].values():
            check(side, "n", n)
        groups = list(m["tools"].values()) + list(m.get("fanout", {}).get("domains", {}).values())
        for g in groups:
            for n in g["nodes"]:
                check(side, "n", n)
            for e in g["edges"]:
                check(side, "e", e)
        for es in m["transfers"].values():
            for e in es:
                check(side, "e", e)
        if "fanout" in m:
            check(side, "n", m["fanout"]["node"])
            check(side, "e", m["fanout"]["edge"])
    return svg


PORTAL_JS = r"""
    let liveApiAvailable = false;
    let activeScenarioIdx = 0;
    let workbenchRunning = false;
    const customPromptDrafts = {};
    const liveRunResults = {};

    function getVisitorId() {
      try {
        let vid = sessionStorage.getItem("cymbal_eval_visitor_id");
        if (!vid) {
          vid = "v_" + Math.random().toString(36).slice(2, 10) + "_" + Date.now().toString(36);
          sessionStorage.setItem("cymbal_eval_visitor_id", vid);
        }
        return vid;
      } catch (_) {
        return "v_session_default";
      }
    }

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

    function baselineOf(code) {
      const sc = (BENCHMARK_DATA.scenarios || []).find(x => x.code === code);
      return sc ? sc.result : null;
    }

    function pctDelta(asis, tobe) {
      return (asis && tobe !== null && tobe !== undefined) ? ((tobe - asis) / asis) * 100 : null;
    }

    function renderHeroKpis() {
      const S = UI_STRINGS.heroKpis;
      const s1 = baselineOf("S1") || {};
      const s5 = baselineOf("S5") || {};
      const t1 = (s1.comparison_summary || {}).trace_estimate || {};
      const m5 = (s5.comparison_summary || {}).measured || {};
      const avg = BENCHMARK_DATA.s4_average_per_turn || {};
      const bqDelta = pctDelta(t1.asis_bqca_input_tokens, t1.tobe_bqca_input_tokens);
      const avgDelta = pctDelta(avg.asis_total_input_tokens, avg.tobe_total_input_tokens);
      const card = (label, value, color, sub) => `
        <div class="kpi-card">
          <div class="kpi-label">${label}</div>
          <div class="kpi-value" style="color:${color};">${value}</div>
          <div class="kpi-sub">${sub}</div>
        </div>`;
      document.getElementById("hero-kpi-grid").innerHTML =
        card(S.k1Label, fmtDelta(bqDelta), deltaColor(bqDelta),
          `<strong>${fmtTok(t1.tobe_bqca_input_tokens)}</strong> vs ${fmtTok(t1.asis_bqca_input_tokens)} tok. ${S.k1Sub}`) +
        card(S.k2Label, fmtDelta(t1.total_input_delta_pct), deltaColor(t1.total_input_delta_pct),
          `<strong>${fmtTok(t1.tobe_total_input_tokens)}</strong> vs ${fmtTok(t1.asis_total_input_tokens)} tok. ${S.k2Sub}`) +
        card(S.k3Label, fmtDelta(avgDelta), deltaColor(avgDelta),
          `<strong>${fmtTok(avg.tobe_total_input_tokens)}</strong> vs ${fmtTok(avg.asis_total_input_tokens)} tok, ${fmtTok(avg.turns_measured)} turns. ${S.k3Sub} $${Number(avg.tobe_cost_usd || 0).toFixed(4)} vs $${Number(avg.asis_cost_usd || 0).toFixed(4)}`) +
        card(S.k4Label, `${fmtTok(m5.tobe_bqca_calls)} ${S.k4Unit}`, "var(--blue)",
          `${S.k4Sub} <strong>${(Number(m5.tobe_latency_ms || 0) / 1000).toFixed(1)} s</strong>.`);
    }

    function renderScenario(idx) {
      activeScenarioIdx = idx;
      const sc = BENCHMARK_DATA.scenarios[idx];
      const S = UI_STRINGS;

      document.querySelectorAll("#scenario-tabs .tab-btn").forEach((b, i) => {
        b.classList.toggle("active", i === idx);
      });

      const presets = (S.wbPresets && S.wbPresets[sc.code]) ? S.wbPresets[sc.code] : [];
      const currentDraft = customPromptDrafts[sc.code] !== undefined ? customPromptDrafts[sc.code] : sc.prompt;
      const nextSc = BENCHMARK_DATA.scenarios[idx + 1];
      const savedLive = liveRunResults[sc.code];
      const presetButtonsHtml = presets.map((p, pIdx) => `
        <button type="button" class="preset-chip" data-preset-idx="${pIdx}">${escapeHtml(p.label)}</button>
      `).join("");

      document.getElementById("scenario-detail").innerHTML = `
        <div class="scenario-top">
          <div>
            <span class="tag tag-blue">${escapeHtml(sc.code)} · ${formatInlineText(sc.track || S.scenarioBadge)}</span>
            <h3 style="font-size:19px;margin-bottom:2px;">${formatInlineText(sc.title)}</h3>
            <div class="route-trace mono">Route: ${formatInlineText(sc.routing_path)}</div>
          </div>
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

        <div class="workbench-box" id="wb-console-anchor">
          <div class="wb-header">
            <div>
              <span class="tag tag-blue" style="margin-bottom:4px;">${S.wbBadge} · ${escapeHtml(sc.code)}</span>
              <h3 style="font-size:16px;margin-bottom:2px;">${S.wbTitle} (${escapeHtml(S.layerLabels[sc.code] || sc.code)})</h3>
              <div style="font-size:12.8px;color:var(--text-secondary);">${S.wbSubtitle}</div>
            </div>
            <details style="font-size:12.3px;color:var(--text-secondary);">
              <summary style="cursor:pointer;font-weight:600;color:var(--blue);">${S.wbSchemaSummary}</summary>
              <div style="margin-top:6px;background:#FFFFFF;border:1px solid var(--border);border-radius:6px;padding:9px 12px;max-width:540px;line-height:1.5;">
                ${S.wbSchemaBodyHtml}
              </div>
            </details>
          </div>

          <div style="font-size:11.8px;font-weight:700;color:var(--text-secondary);margin-bottom:5px;">${S.wbPresetLabel}</div>
          <div class="preset-row" id="wb-preset-row">${presetButtonsHtml}</div>

          <textarea class="wb-textarea" id="wb-prompt-input" maxlength="600" placeholder="${escapeHtml(S.wbPlaceholder)}">${escapeHtml(currentDraft)}</textarea>
          ${sc.code === "S4" ? `<div style="font-size:12.3px;color:var(--text-secondary);margin-bottom:10px;">${S.wbS4Hint}</div>` : ""}

          <div class="wb-actions">
            <div class="wb-btn-group">
              <button type="button" class="btn-live" id="wb-run-dual-btn" ${(liveApiAvailable && !workbenchRunning) ? "" : "disabled"}>
                ${liveApiAvailable ? S.wbBtnRunDual.replace("{CODE}", sc.code) : S.btnRunDisabled}
              </button>
              ${(sc.code === "S4" && savedLive) ? `<button type="button" class="btn-outline" id="wb-append-turn-btn" ${workbenchRunning ? "disabled" : ""}>${S.wbBtnAppendTurn}</button>` : ""}
            </div>
            <div class="wb-btn-group">
              ${nextSc ? `<button type="button" class="btn-next-step" id="wb-next-step-btn">${S.wbBtnNextStep.replace("{NEXT}", nextSc.code)}</button>` : ""}
            </div>
          </div>

          ${flowBoxHtml(sc.code)}
          <div id="wb-sse-stream-container"></div>
          <div id="wb-live-dual-card-container">${savedLive ? buildDualComparisonCardHtml(savedLive) : ""}</div>
        </div>

        <div class="ref-divider">${S.refBaselineHeading} (${escapeHtml(sc.code)})</div>
        <div class="sub-box" style="margin-bottom:14px;font-size:12.8px;">${S.baselineDisclosureHtml}</div>
        ${sc.result ? buildDualComparisonCardHtml(sc.result, true) : ""}
        ${sc.fanout ? `<div class="ref-divider">${S.fanoutHeading}</div>${buildDualComparisonCardHtml(sc.fanout, true)}` : ""}
      `;

      renderProgressiveTracker();
      flowBind(sc.code);

      const ta = document.getElementById("wb-prompt-input");
      if (ta) {
        ta.addEventListener("input", () => {
          customPromptDrafts[sc.code] = ta.value;
        });
      }

      document.querySelectorAll("#wb-preset-row .preset-chip").forEach(chip => {
        chip.addEventListener("click", () => {
          const pIdx = Number(chip.dataset.presetIdx);
          if (presets[pIdx] && ta) {
            ta.value = presets[pIdx].prompt;
            customPromptDrafts[sc.code] = presets[pIdx].prompt;
          }
        });
      });

      const dualBtn = document.getElementById("wb-run-dual-btn");
      if (dualBtn && liveApiAvailable) {
        dualBtn.addEventListener("click", () => triggerWorkbenchDualStream(sc.code, "burst"));
      }

      const appendBtn = document.getElementById("wb-append-turn-btn");
      if (appendBtn && liveApiAvailable) {
        appendBtn.addEventListener("click", () => triggerWorkbenchDualStream("S4", "append"));
      }

      const nextBtn = document.getElementById("wb-next-step-btn");
      if (nextBtn && nextSc) {
        nextBtn.addEventListener("click", () => {
          renderScenario(idx + 1);
          const anchor = document.getElementById("progressive-tracker");
          if (anchor) anchor.scrollIntoView({ behavior: "smooth", block: "start" });
        });
      }
    }

    function fmtTok(v) {
      return (v === null || v === undefined) ? "n/a" : Number(v).toLocaleString();
    }

    function fmtDelta(pct) {
      if (pct === null || pct === undefined || isNaN(Number(pct))) return "n/a";
      const v = Number(pct);
      return (v > 0 ? "+" : "") + v.toFixed(1) + "%";
    }

    function deltaColor(pct) {
      if (pct === null || pct === undefined || isNaN(Number(pct))) return "var(--text-secondary)";
      return Number(pct) <= 0 ? "var(--green)" : "var(--red)";
    }

    // Input tokens for one step: the evaluator's live run if present, else the measured pre-run baseline.
    function getStepBaselineOrLiveSummary(sc) {
      const live = liveRunResults[sc.code];
      const res = live || sc.result || {};
      const cs = res.comparison_summary || {};
      const m = cs.measured || {};
      const tr = cs.trace_estimate;
      let asis = tr ? tr.asis_total_input_tokens : m.asis_adk_prompt_tokens;
      let tobe = tr ? tr.tobe_total_input_tokens : m.tobe_adk_prompt_tokens;
      // S4 is about the whole session, so its baseline row shows the average over all measured turns.
      const avg = BENCHMARK_DATA.s4_average_per_turn;
      const isAverage = !live && sc.code === "S4" && !!(avg && avg.asis_total_input_tokens);
      if (isAverage) {
        asis = avg.asis_total_input_tokens;
        tobe = avg.tobe_total_input_tokens;
      }
      return {
        isLive: !!live,
        isAverage: isAverage,
        hasTotal: !!tr,
        asis: asis,
        tobe: tobe,
        deltaPct: pctDelta(asis, tobe),
        adkAsis: m.asis_adk_prompt_tokens,
        adkTobe: m.tobe_adk_prompt_tokens,
        callsAsis: m.asis_bqca_calls,
        callsTobe: m.tobe_bqca_calls,
      };
    }

    function renderProgressiveTracker() {
      const el = document.getElementById("progressive-tracker");
      if (!el) return;
      const S = UI_STRINGS;
      const scenarios = BENCHMARK_DATA.scenarios || [];
      const summaries = scenarios.map(sc => ({ sc, sum: getStepBaselineOrLiveSummary(sc) }));
      const maxTok = Math.max(1, ...summaries.map(x => Math.max(x.sum.asis || 0, x.sum.tobe || 0)));
      const liveCount = summaries.filter(x => x.sum.isLive).length;
      const barWidth = v => (v === null || v === undefined) ? "0" : Math.max(2, Math.min(100, (v / maxTok) * 100)).toFixed(1);

      const pillsHtml = summaries.map(({ sc, sum }, idx) => {
        const cls = [
          "prog-step-pill",
          idx === activeScenarioIdx ? "active-step" : "",
          sum.isLive ? "live-done" : "",
        ].filter(Boolean).join(" ");
        const statusBadge = sum.isLive
          ? `<span class="mono" style="font-size:10.5px;font-weight:700;color:var(--green);background:var(--green-soft);padding:1px 6px;border-radius:4px;">${S.trackerLiveTag}</span>`
          : `<span class="mono" style="font-size:10.5px;color:var(--text-secondary);">${S.trackerBaseTag}</span>`;
        return `
          <div class="${cls}" data-step-idx="${idx}">
            <div style="display:flex;justify-content:space-between;align-items:center;gap:4px;margin-bottom:4px;">
              <strong class="mono" style="font-size:12.5px;color:var(--blue);">${escapeHtml(sc.code)}</strong>
              ${statusBadge}
            </div>
            <div style="font-size:12px;font-weight:600;line-height:1.35;color:var(--text);margin-bottom:4px;">${escapeHtml(S.layerLabels[sc.code] || sc.code)}</div>
            <div class="mono" style="font-size:11.5px;font-weight:700;color:${deltaColor(sum.deltaPct)};">${fmtDelta(sum.deltaPct)}</div>
          </div>
        `;
      }).join("");

      const barsHtml = summaries.map(({ sc, sum }) => `
          <div class="prog-bar-row">
            <div>
              <strong class="mono" style="color:var(--text);">${escapeHtml(sc.code)}</strong>
              <span style="color:var(--text-secondary);font-size:11.8px;"> · ${escapeHtml(S.layerShort[sc.code] || "")}</span>
              <span class="mono" style="display:inline-block;margin-left:4px;font-size:10px;font-weight:700;color:${sum.isLive ? "var(--green)" : "var(--text-secondary)"};">[${sum.isLive ? S.trackerLiveTag : S.trackerBaseTag}${sum.hasTotal ? "" : " · " + S.trackerAdkOnly}${sum.isAverage ? " · " + S.trackerAvgTag : ""}]</span>
            </div>
            <div class="dual-bar-track">
              <div class="bar-line">
                <span class="mono" style="font-size:10.5px;width:42px;color:var(--red);flex-shrink:0;">As-Is</span>
                <div style="flex:1;background:#F1F3F4;border-radius:4px;overflow:hidden;">
                  <div class="bar-fill-asis" style="width:${barWidth(sum.asis)}%;${sum.asis ? "" : "min-width:0;"}"></div>
                </div>
                <span class="mono" style="font-size:11px;width:82px;text-align:right;color:var(--text-secondary);flex-shrink:0;">${fmtTok(sum.asis)}</span>
              </div>
              <div class="bar-line">
                <span class="mono" style="font-size:10.5px;width:42px;color:var(--green);font-weight:700;flex-shrink:0;">To-Be</span>
                <div style="flex:1;background:#F1F3F4;border-radius:4px;overflow:hidden;">
                  <div class="bar-fill-tobe" style="width:${barWidth(sum.tobe)}%;${sum.tobe ? "" : "min-width:0;"}"></div>
                </div>
                <span class="mono" style="font-size:11px;width:82px;text-align:right;color:var(--green);font-weight:700;flex-shrink:0;">${fmtTok(sum.tobe)}</span>
              </div>
            </div>
            <div class="mono" style="text-align:right;font-size:11.8px;">
              <strong style="color:${deltaColor(sum.deltaPct)};">${fmtDelta(sum.deltaPct)}</strong>
              ${sum.isAverage ? "" : `<span style="color:var(--text-secondary);"> · ADK ${fmtTok(sum.adkTobe)} vs ${fmtTok(sum.adkAsis)} · BQCA calls ${fmtTok(sum.callsTobe)} vs ${fmtTok(sum.callsAsis)}</span>`}
            </div>
          </div>
        `).join("");

      el.innerHTML = `
        <div class="prog-tracker-head">
          <div style="flex:1 1 520px;min-width:0;">
            <span class="tag tag-green" style="margin-bottom:4px;">${S.trackerEyebrow} (${liveCount}/5 ${S.trackerLiveCountLabel})</span>
            <h3 style="font-size:16.5px;margin-bottom:2px;">${S.trackerTitle}</h3>
            <p style="font-size:13px;color:var(--text-secondary);">${S.trackerDesc}</p>
          </div>
          <button type="button" class="btn-outline" id="wb-reset-session-btn" ${(!liveApiAvailable || workbenchRunning) ? "disabled" : ""}>${S.wbBtnReset}</button>
        </div>
        <div class="prog-step-strip">${pillsHtml}</div>
        <div class="prog-bar-rows">${barsHtml}</div>
      `;

      el.querySelectorAll(".prog-step-pill").forEach(pill => {
        pill.addEventListener("click", () => {
          renderScenario(Number(pill.dataset.stepIdx));
        });
      });

      const resetBtn = document.getElementById("wb-reset-session-btn");
      if (resetBtn && liveApiAvailable) {
        resetBtn.addEventListener("click", resetWorkbenchSession);
      }
    }

    function buildDualComparisonCardHtml(res, isBaseline) {
      const S = UI_STRINGS;
      const cs = res.comparison_summary || {};
      const m = cs.measured || {};
      const tr = cs.trace_estimate;
      const asis = res.asis || {};
      const tobe = res.tobe || {};
      const asisAdk = asis.adk_usage || {};
      const tobeAdk = tobe.adk_usage || {};
      const cal = res.calibration || {};
      const measuredBqca = res.bqca_basis === "measured";
      const secs = ms => (Number(ms || 0) / 1000).toFixed(1) + "s";

      const sideErrors = side => (side.errors && side.errors.length)
        ? `<div style="font-size:12.8px;color:var(--red);font-weight:600;margin-bottom:8px;">${S.wbErrorLabel}: ${escapeHtml(side.errors.join(" | "))}</div>`
        : "";

      let prereqHtml = "";
      if (res.prerequisite) {
        const p = res.prerequisite;
        prereqHtml = `
          <div class="sub-box" style="margin-bottom:14px;font-size:12.8px;">
            ${S.wbPrereqNote} <span class="mono">"${escapeHtml(p.prompt)}"</span>
            <span class="mono">(ADK prompt tokens: To-Be ${fmtTok(p.tobe_adk_prompt_tokens)} / As-Is ${fmtTok(p.asis_adk_prompt_tokens)})</span>
          </div>
        `;
      }

      let turnCurveHtml = "";
      if (Array.isArray(res.turn_curve) && res.turn_curve.length > 0) {
        const rows = res.turn_curve.map(r => {
          const pct = r.asis_adk_prompt_tokens ? ((r.tobe_adk_prompt_tokens - r.asis_adk_prompt_tokens) / r.asis_adk_prompt_tokens) * 100 : null;
          return `
            <tr>
              <td class="mono"><strong>Turn ${r.turn}</strong></td>
              <td>${escapeHtml(r.prompt || "")}</td>
              <td class="mono" style="color:var(--red);">${fmtTok(r.asis_adk_prompt_tokens)} tok</td>
              <td class="mono" style="color:var(--green);font-weight:700;">${fmtTok(r.tobe_adk_prompt_tokens)} tok (${fmtDelta(pct)})</td>
              <td class="mono">${Number(r.tobe_compacted_dropped || 0)}</td>
            </tr>
          `;
        }).join("");
        turnCurveHtml = `
          <div style="margin-bottom:16px;">
            <div style="font-size:13px;font-weight:700;margin-bottom:6px;">${S.wbLiveS4TableTitle}</div>
            <div class="table-wrap">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>Turn</th>
                    <th>Prompt</th>
                    <th>As-Is ADK prompt</th>
                    <th>To-Be ADK prompt</th>
                    <th>To-Be items evicted</th>
                  </tr>
                </thead>
                <tbody>${rows}</tbody>
              </table>
            </div>
          </div>
        `;
      }

      let stateHtml = "";
      if (res.state_summary) {
        const st = res.state_summary;
        stateHtml = `
          <div class="sub-box" style="margin-bottom:14px;font-size:12.8px;">
            <strong>${S.wbStateTitle}</strong>
            <span class="mono"> ${escapeHtml(st.new_session_id || "")} · user profile: ${escapeHtml(JSON.stringify(st.rehydrated_user_profile || null))} · pinned insights: ${Number(st.rehydrated_pinned_insights || 0)}</span>
          </div>
        `;
      }

      const maxBar = Math.max(1, m.asis_adk_prompt_tokens || 0, m.tobe_adk_prompt_tokens || 0);
      const w = v => Math.max(2, Math.min(100, ((v || 0) / maxBar) * 100)).toFixed(1);

      const traceHtml = tr ? `
          <div class="sub-box" style="margin-bottom:16px;">
            <span class="tag ${measuredBqca ? "tag-green" : "tag-amber"}">${measuredBqca ? S.wbTraceTitleMeasured : S.wbTraceTitle}</span>
            <div class="mono" style="font-size:12.5px;line-height:1.7;">
              BQCA input tokens: To-Be ${fmtTok(tr.tobe_bqca_input_tokens)} vs As-Is ${fmtTok(tr.asis_bqca_input_tokens)}<br/>
              Total input (ADK + BQCA): To-Be ${fmtTok(tr.tobe_total_input_tokens)} vs As-Is ${fmtTok(tr.asis_total_input_tokens)} (${fmtDelta(tr.total_input_delta_pct)})<br/>
              Cost estimate per turn: To-Be $${Number(tr.tobe_cost_usd || 0).toFixed(4)} vs As-Is $${Number(tr.asis_cost_usd || 0).toFixed(4)} (${fmtDelta(tr.cost_delta_pct)})
            </div>
            <div style="font-size:12.3px;color:var(--text-secondary);margin-top:6px;">${measuredBqca ? S.wbTraceNoteMeasured : S.wbTraceNote + " <span class=\"mono\">" + escapeHtml(cal.measured_at_utc || "") + "</span>"}</div>
          </div>
        ` : `<div class="sub-box" style="margin-bottom:16px;font-size:12.8px;color:var(--text-secondary);">${S.wbTraceUnavailable}</div>`;

      return `
        <div class="live-dual-card">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px;flex-wrap:wrap;margin-bottom:12px;padding-bottom:10px;border-bottom:1px solid var(--border);">
            <div>
              <span class="tag ${res.status === "SUCCESS" ? "tag-green" : "tag-red"}" style="margin-bottom:4px;">${isBaseline ? S.baselineCardBadge : S.wbLiveCardBadge} · ${escapeHtml(res.scenario_code)} · ${escapeHtml(res.status || "")}</span>
              <div style="font-size:13.5px;font-weight:600;color:var(--text);">${S.wbExecutedPromptLabel}: "${escapeHtml(res.prompt_executed)}"</div>
            </div>
            <div class="mono" style="font-size:12px;color:var(--text-secondary);">
              Wall-Clock: <strong>${secs(res.wall_clock_ms)}</strong> · google-adk ${escapeHtml(res.adk_version || "")}
            </div>
          </div>

          ${prereqHtml}

          <div class="metric-ribbon" style="margin-bottom:14px;">
            <div class="metric-cell">
              <div class="m-k">${S.wbMetricAdk}</div>
              <div class="m-v mono" style="color:${deltaColor(m.adk_prompt_delta_pct)};">${fmtTok(m.tobe_adk_prompt_tokens)} vs ${fmtTok(m.asis_adk_prompt_tokens)} (${fmtDelta(m.adk_prompt_delta_pct)})</div>
            </div>
            <div class="metric-cell">
              <div class="m-k">${S.wbMetricCalls}</div>
              <div class="m-v mono">${fmtTok(m.tobe_bqca_calls)} vs ${fmtTok(m.asis_bqca_calls)}</div>
            </div>
            <div class="metric-cell">
              <div class="m-k">${S.wbMetricLatency}</div>
              <div class="m-v mono">${secs(m.tobe_latency_ms)} vs ${secs(m.asis_latency_ms)}</div>
            </div>
            <div class="metric-cell">
              <div class="m-k">${S.wbMetricLlmCalls}</div>
              <div class="m-v mono">${fmtTok(m.tobe_llm_calls)} vs ${fmtTok(m.asis_llm_calls)}</div>
            </div>
          </div>

          <div style="background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:10px 14px;margin-bottom:16px;">
            <div style="font-size:11.5px;font-weight:700;color:var(--text-secondary);margin-bottom:6px;">${S.wbBarTitle}</div>
            <div class="dual-bar-track">
              <div class="bar-line">
                <span class="mono" style="font-size:11px;width:52px;color:var(--red);font-weight:700;">As-Is</span>
                <div style="flex:1;background:#E8EAED;border-radius:4px;overflow:hidden;"><div class="bar-fill-asis" style="width:${w(m.asis_adk_prompt_tokens)}%;"></div></div>
                <span class="mono" style="font-size:11.5px;width:110px;text-align:right;">${fmtTok(m.asis_adk_prompt_tokens)} tok</span>
              </div>
              <div class="bar-line">
                <span class="mono" style="font-size:11px;width:52px;color:var(--green);font-weight:700;">To-Be</span>
                <div style="flex:1;background:#E8EAED;border-radius:4px;overflow:hidden;"><div class="bar-fill-tobe" style="width:${w(m.tobe_adk_prompt_tokens)}%;"></div></div>
                <span class="mono" style="font-size:11.5px;width:110px;text-align:right;color:var(--green);font-weight:700;">${fmtTok(m.tobe_adk_prompt_tokens)} tok</span>
              </div>
            </div>
          </div>

          ${traceHtml}
          ${turnCurveHtml}
          ${stateHtml}

          <div class="stack-list" style="margin-bottom:0;">
            <div class="sub-box asis-border" style="background:#FFFBFB;">
              <div class="evidence-header">
                <span class="tag tag-red">${escapeHtml(asis.label || "As-Is")}</span>
                <span class="mono" style="font-size:11.8px;color:var(--red);">ADK prompt ${fmtTok(asisAdk.prompt_tokens)} tok · cached ${fmtTok(asisAdk.cached_tokens)} · ${secs(asis.latency_ms)}</span>
              </div>
              <div class="mono" style="font-size:11.8px;color:var(--text-secondary);margin-bottom:8px;">
                Tools called: ${escapeHtml((asis.tool_calls || []).join(", ") || "none")} · ${S.wbMsgsPerCall}: ${escapeHtml(JSON.stringify(asis.bqca_messages_sent || []))} · ${S.wbToolResp}: ${fmtTok(asis.tool_response_chars)} chars
              </div>
              ${sideErrors(asis)}
              ${asis.generated_sql ? `<pre class="sql-block" style="margin-bottom:10px;">${escapeHtml(asis.generated_sql)}</pre>` : ""}
              <div class="answer-box" style="border-left-color:var(--red);">${formatAgentAnswer(asis.answer)}</div>
            </div>

            <div class="sub-box tobe-border" style="background:#F8FDF9;">
              <div class="evidence-header">
                <span class="tag tag-green">${escapeHtml(tobe.label || "To-Be")}</span>
                <span class="mono" style="font-size:11.8px;color:var(--green);font-weight:700;">ADK prompt ${fmtTok(tobeAdk.prompt_tokens)} tok · cached ${fmtTok(tobeAdk.cached_tokens)} · ${secs(tobe.latency_ms)}</span>
              </div>
              <div class="mono" style="font-size:11.8px;color:var(--text-secondary);margin-bottom:8px;">
                Agents: ${escapeHtml((tobeAdk.agents_invoked || []).join(" > ") || "none")} · BQCA agents: ${escapeHtml((tobe.bqca_agents || []).join(", ") || "none")} · ${S.wbMsgsPerCall}: ${escapeHtml(JSON.stringify(tobe.bqca_messages_sent || []))}
              </div>
              ${sideErrors(tobe)}
              ${tobe.generated_sql ? `<pre class="sql-block" style="margin-bottom:10px;">${escapeHtml(tobe.generated_sql)}</pre>` : ""}
              ${tobe.markdown_table ? `<div style="margin-bottom:10px;">${parseMarkdownTableToHtml(tobe.markdown_table)}</div>` : ""}
              <div class="answer-box">${formatAgentAnswer(tobe.answer)}</div>
            </div>
          </div>
        </div>
      `;
    }


    // ------------------------------------------------------------------------------------------
    // Live execution flow. The backend streams each ADK event of the run as a `step`
    // (agent, tool call, tool response). FLOW_MAP ties ADK names to diagram elements; a name
    // that is not in the map lights nothing and is only named in the status line.
    // ------------------------------------------------------------------------------------------
    const FLOW_MIN_STEP_MS = 350;
    const flowRecorded = {};
    const flowState = {};
    const flowQueues = { tobe: { items: [], timer: null }, asis: { items: [], timer: null } };
    let flowRunningCode = null;

    function flowBoxHtml(code) {
      const S = UI_STRINGS;
      const hasRun = (flowRecorded[code] || []).length > 0;
      return `
        <div class="flow-box" id="wb-flow-box">
          <div class="flow-head">
            <div>
              <div class="flow-title">${S.flowTitle}</div>
              <div class="flow-desc">${S.flowDesc}</div>
            </div>
            <button type="button" class="btn-outline" id="flow-replay-btn" style="${hasRun ? "" : "display:none;"}">${S.flowReplay}</button>
          </div>
          <div class="flow-svg-wrap">${FLOW_SVG}</div>
          <div class="flow-status mono" id="flow-status-tobe"><b>[To-Be]</b> ${S.flowIdle}</div>
          <div class="flow-status mono" id="flow-status-asis"><b>[As-Is]</b> ${S.flowIdle}</div>
          <div class="flow-legend">
            <span><span class="flow-chip active"></span>${S.flowLegendActive}</span>
            <span><span class="flow-chip done"></span>${S.flowLegendDone}</span>
            <span><span class="flow-chip"></span>${S.flowLegendIdle}</span>
          </div>
          <div class="flow-desc" style="margin-top:6px;">${S.flowNote}</div>
        </div>`;
    }

    function flowRenderStatus(side) {
      const el = document.getElementById("flow-status-" + side);
      const st = flowState[side];
      if (!el) return;
      const tag = side === "tobe" ? "[To-Be]" : "[As-Is]";
      if (!st || !st.text) { el.innerHTML = `<b>${tag}</b> ${UI_STRINGS.flowIdle}`; return; }
      const secs = st.running ? " · " + ((Date.now() - st.stepAt) / 1000).toFixed(1) + "s" : "";
      el.innerHTML = `<b>${tag}</b> ${escapeHtml(st.text)}${secs}`;
    }

    function flowTick() { flowRenderStatus("tobe"); flowRenderStatus("asis"); }

    function flowReset(side) {
      document.querySelectorAll(`[id^="lf-${side}-"]`).forEach(el => el.classList.remove("lf-active", "lf-done"));
      flowState[side] = { entered: false, text: "", stepAt: Date.now(), running: false };
    }

    function flowSettle(side) {
      document.querySelectorAll(`[id^="lf-${side}-"].lf-active`).forEach(el => {
        el.classList.remove("lf-active");
        el.classList.add("lf-done");
      });
    }

    function flowMark(side, nodes, edges) {
      (nodes || []).forEach(id => {
        const el = document.getElementById(`lf-${side}-n-${id}`);
        if (el) { el.classList.remove("lf-done"); el.classList.add("lf-active"); }
      });
      (edges || []).forEach(id => {
        const el = document.getElementById(`lf-${side}-e-${id}`);
        if (el) {
          el.classList.remove("lf-done");
          el.classList.add("lf-active");
          el.parentNode.appendChild(el);   // edges share segments: draw the lit one on top
        }
      });
    }

    function flowApply(side, st) {
      const M = FLOW_MAP[side];
      const S = UI_STRINGS;
      if (!M) return;
      if (st.kind === "start") {
        flowReset(side);
        flowMark(side, [M.user], []);
        Object.assign(flowState[side], { text: S.flowStepStart + " " + (st.prompt || ""), stepAt: Date.now(), running: true });
        flowRenderStatus(side);
        return;
      }
      const state = flowState[side] || (flowState[side] = { entered: false, text: "", stepAt: Date.now(), running: true });
      const a = M.agents[st.agent];
      let note = "";
      if (!state.entered && a) {
        state.entered = true;
        flowSettle(side);
        flowMark(side, [a], a === M.entry ? [M.entryEdge] : []);
        if (a !== M.entry) note = " (" + S.flowNoRootHop + ")";
      }
      let text = state.text;
      if (st.kind === "call") {
        flowSettle(side);
        const nodes = a ? [a] : [];
        const edges = [];
        let known = true;
        if (st.name === "transfer_to_agent") {
          const t = M.agents[st.target];
          if (a && t) {
            nodes.push(t);
            (M.transfers[a + "|" + t] || M.transfers[t + "|" + a] || []).forEach(e => edges.push(e));
          } else { known = false; }
        } else if (M.fanout && st.name === M.fanout.tool) {
          nodes.push(M.fanout.node);
          edges.push(M.fanout.edge);
          (st.domains || []).forEach(d => {
            const x = M.fanout.domains[d];
            if (x) { x.nodes.forEach(n => nodes.push(n)); x.edges.forEach(e => edges.push(e)); }
          });
        } else if (M.tools[st.name]) {
          M.tools[st.name].nodes.forEach(n => nodes.push(n));
          M.tools[st.name].edges.forEach(e => edges.push(e));
        } else { known = false; }
        flowMark(side, nodes, edges);
        const arg = st.target ? "(" + st.target + ")" : ((st.domains || []).length ? "(" + st.domains.join(", ") + ")" : "");
        const fanCalls = (M.fanout && st.name === M.fanout.tool && (st.domains || []).length) ? " · " + S.flowFanCalls.replace("{N}", st.domains.length) : "";
        text = st.agent + " → " + st.name + arg + fanCalls + (known ? "" : " " + S.flowNotOnDiagram) + note;
      } else if (st.kind === "response") {
        if (st.name !== "transfer_to_agent") {
          flowSettle(side);
          if (a) flowMark(side, [a], []);
          text = st.name + " → " + st.agent + " (" + S.flowReturned + ")";
        }
      } else if (st.kind === "final") {
        flowSettle(side);
        flowMark(side, [M.user], []);
        text = st.agent + ": " + S.flowFinal + note;
      } else if (st.kind === "end") {
        flowSettle(side);
        text = S.flowDone + " " + ((st.t_ms || 0) / 1000).toFixed(1) + "s";
      }
      state.text = text;
      state.stepAt = Date.now();
      state.running = st.kind !== "end";
      flowRenderStatus(side);
    }

    function flowDrain(side) {
      const q = flowQueues[side];
      const item = q.items.shift();
      if (!item) { q.timer = null; return; }
      flowApply(side, item);
      q.timer = setTimeout(() => flowDrain(side), FLOW_MIN_STEP_MS);
    }

    function flowEnqueue(side, st) {
      const q = flowQueues[side];
      if (!q) return;
      q.items.push(st);
      if (!q.timer) flowDrain(side);
    }

    function flowClearQueues() {
      Object.values(flowQueues).forEach(q => { q.items = []; if (q.timer) clearTimeout(q.timer); q.timer = null; });
    }

    function flowOnStep(code, evt) {
      (flowRecorded[code] = flowRecorded[code] || []).push(evt);
      const shown = BENCHMARK_DATA.scenarios[activeScenarioIdx];
      if (shown && shown.code === code) flowEnqueue(evt.side, evt);
    }

    // Re-applies the recorded steps of a scenario: at once after a re-render, or step by step for a replay.
    function flowRestore(code, animate) {
      flowClearQueues();
      const steps = flowRecorded[code] || [];
      if (!steps.length) return;
      if (animate) { flowReset("tobe"); flowReset("asis"); steps.forEach(s => flowEnqueue(s.side, s)); }
      else { steps.forEach(s => flowApply(s.side, s)); }
    }

    function flowBind(code) {
      const btn = document.getElementById("flow-replay-btn");
      if (btn) btn.addEventListener("click", () => { if (flowRunningCode !== code) flowRestore(code, true); });
      flowRestore(code, false);
    }

    async function triggerWorkbenchDualStream(scenarioCode, s4Mode) {
      if (workbenchRunning) return;
      const S = UI_STRINGS;
      const ta = document.getElementById("wb-prompt-input");
      const promptText = (ta ? ta.value : "").trim();
      if (!promptText) return;

      customPromptDrafts[scenarioCode] = promptText;
      workbenchRunning = true;

      const dualBtn = document.getElementById("wb-run-dual-btn");
      const appendBtn = document.getElementById("wb-append-turn-btn");
      const sseContainer = document.getElementById("wb-sse-stream-container");
      const cardContainer = document.getElementById("wb-live-dual-card-container");

      if (dualBtn) {
        dualBtn.disabled = true;
        dualBtn.textContent = S.wbRunningDual.replace("{CODE}", scenarioCode);
      }
      if (appendBtn) appendBtn.disabled = true;

      const startMs = Date.now();
      const logs = [];
      flowClearQueues();
      flowRecorded[scenarioCode] = [];
      flowRunningCode = scenarioCode;
      flowReset("tobe");
      flowReset("asis");
      flowTick();
      const renderLogs = () => {
        if (!sseContainer) return;
        const elapsed = ((Date.now() - startMs) / 1000).toFixed(1);
        const itemsHtml = logs.map(item => {
          const cls = item.side === "asis" ? "sse-tag-asis" : (item.side === "tobe" ? "sse-tag-tobe" : "sse-tag-both");
          const tag = item.side === "asis" ? "[As-Is]" : (item.side === "tobe" ? "[To-Be]" : "[Dual Engine]");
          return `<div class="sse-item mono"><span class="${cls}">${tag}</span> ${escapeHtml(item.detail)}</div>`;
        }).join("");
        sseContainer.innerHTML = `
          <div class="sse-log-box">
            <div class="mono" style="display:flex;justify-content:space-between;color:#93C5FD;font-weight:700;margin-bottom:6px;border-bottom:1px solid #374151;padding-bottom:4px;">
              <span>${S.wbSseHeader} (${escapeHtml(scenarioCode)})</span>
              <span>${elapsed}s</span>
            </div>
            ${itemsHtml}
          </div>
        `;
        const box = sseContainer.querySelector(".sse-log-box");
        if (box) box.scrollTop = box.scrollHeight;
      };

      logs.push({ side: "both", detail: S.callingEndpoint + " (" + BENCHMARK_DATA.environment.gcp_project + ")..." });
      renderLogs();
      const timerId = setInterval(() => { renderLogs(); flowTick(); }, 400);

      try {
        const resp = await fetch("/api/workbench/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            visitor_id: getVisitorId(),
            scenario_code: scenarioCode,
            prompt: promptText,
            s4_mode: s4Mode || "burst",
          }),
        });

        if (!resp.ok || !resp.body) {
          throw new Error("HTTP " + resp.status);
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buf = "";

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const parts = buf.split("\n\n");
          buf = parts.pop() || "";

          for (const chunk of parts) {
            const line = chunk.trim();
            if (!line.startsWith("data:")) continue;
            const jsonStr = line.slice(5).trim();
            if (!jsonStr) continue;
            let evt = null;
            try { evt = JSON.parse(jsonStr); } catch (_) { continue; }
            if (!evt) continue;

            if (evt.type === "progress") {
              logs.push({ side: evt.side || "both", detail: evt.detail || "" });
              renderLogs();
            } else if (evt.type === "step") {
              flowOnStep(scenarioCode, evt);
            } else if (evt.type === "complete" && evt.payload) {
              clearInterval(timerId);
              liveRunResults[scenarioCode] = evt.payload;
              if (cardContainer) {
                cardContainer.innerHTML = buildDualComparisonCardHtml(evt.payload);
              }
              renderProgressiveTracker();
              if (scenarioCode === "S4") {
                renderScenario(activeScenarioIdx);
              }
            } else if (evt.type === "error") {
              logs.push({ side: "asis", detail: "Error: " + (evt.message || "Unknown error") });
              renderLogs();
            }
          }
        }
      } catch (err) {
        logs.push({ side: "asis", detail: "Stream error: " + err.message });
        renderLogs();
      } finally {
        clearInterval(timerId);
        workbenchRunning = false;
        flowRunningCode = null;
        const replayBtn = document.getElementById("flow-replay-btn");
        if (replayBtn && (flowRecorded[scenarioCode] || []).length) replayBtn.style.display = "";
        if (dualBtn) {
          dualBtn.disabled = false;
          dualBtn.textContent = S.wbBtnRunDual.replace("{CODE}", scenarioCode);
        }
        if (appendBtn) appendBtn.disabled = false;
        renderProgressiveTracker();
      }
    }

    async function resetWorkbenchSession() {
      if (!liveApiAvailable || workbenchRunning) return;
      try {
        await fetch("/api/workbench/reset", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ visitor_id: getVisitorId() }),
        });
      } catch (_) {}
      Object.keys(liveRunResults).forEach(k => delete liveRunResults[k]);
      Object.keys(customPromptDrafts).forEach(k => delete customPromptDrafts[k]);
      renderScenario(activeScenarioIdx);
    }

    function s4MeasuredRows() {
      return (BENCHMARK_DATA.s4_turn_curve || []).filter(r => r.bqca_basis === "measured");
    }

    // Total input tokens per turn (measured ADK prompt + measured BQCA input) over the S4 session.
    function renderTurnScalingSvg() {
      const S = UI_STRINGS;
      const el = document.getElementById("svg-turn-chart");
      if (!el) return;
      const pts = s4MeasuredRows();
      if (pts.length < 2) {
        el.innerHTML = `<div style="font-size:13px;color:var(--text-secondary);">${S.chartNoData}</div>`;
        return;
      }
      const W = 560, H = 260, padL = 58, padR = 20, padT = 22, padB = 38;
      const maxY = Math.max(...pts.map(p => Math.max(p.asis_total_input_tokens, p.tobe_total_input_tokens))) * 1.15;
      const xPos = i => padL + (i / (pts.length - 1)) * (W - padL - padR);
      const yPos = v => padT + (1 - v / maxY) * (H - padT - padB);
      const poly = key => pts.map((p, i) => `${xPos(i).toFixed(1)},${yPos(p[key]).toFixed(1)}`).join(" ");
      let grid = "";
      for (let g = 0; g <= 4; g++) {
        const val = (maxY / 4) * g;
        const y = yPos(val).toFixed(1);
        grid += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="#E8EAED" stroke-width="1"/>`;
        grid += `<text x="${padL - 8}" y="${Number(y) + 4}" text-anchor="end" font-size="10.5" fill="#5F6368" font-family="Roboto Mono">${Math.round(val / 1000)}K</text>`;
      }
      const xLabels = pts.map((p, i) => `<text x="${xPos(i).toFixed(1)}" y="${H - 12}" text-anchor="middle" font-size="10.5" fill="#5F6368">T${p.turn}</text>`).join("");
      const dots = (key, color) => pts.map((p, i) => `<circle cx="${xPos(i).toFixed(1)}" cy="${yPos(p[key]).toFixed(1)}" r="3.2" fill="${color}"/>`).join("");
      el.innerHTML = `
        <svg viewBox="0 0 ${W} ${H}" width="100%" height="auto" role="img">
          ${grid}
          ${xLabels}
          <polyline fill="none" stroke="#C5221F" stroke-width="2.5" points="${poly("asis_total_input_tokens")}"/>
          <polyline fill="none" stroke="#137333" stroke-width="2.8" points="${poly("tobe_total_input_tokens")}"/>
          ${dots("asis_total_input_tokens", "#C5221F")}
          ${dots("tobe_total_input_tokens", "#137333")}
          <rect x="${padL}" y="4" width="12" height="10" rx="2" fill="#C5221F"/>
          <text x="${padL + 17}" y="13" font-size="11" fill="#5F6368">As-Is</text>
          <rect x="${padL + 70}" y="4" width="12" height="10" rx="2" fill="#137333"/>
          <text x="${padL + 87}" y="13" font-size="11" fill="#5F6368">To-Be</text>
        </svg>
      `;
    }

    // ADK prompt tokens per turn (Vertex AI usage_metadata) over the S4 session.
    function renderAdkMeasuredSvg() {
      const el = document.getElementById("svg-adk-measured-chart");
      if (!el) return;
      const items = BENCHMARK_DATA.s4_turn_curve || [];
      const W = 560, H = 260, padL = 52, padR = 24, padT = 26, padB = 40;
      const maxT = Math.max(1000, ...items.map(r => Math.max(r.asis_adk_prompt_tokens, r.tobe_adk_prompt_tokens))) * 1.18;
      const slotW = (W - padL - padR) / Math.max(1, items.length);
      const yPos = v => padT + (1 - v / maxT) * (H - padT - padB);
      const baseY = H - padB;
      let bars = "";
      items.forEach((it, i) => {
        const cx = padL + slotW * i + slotW / 2;
        const yAsis = yPos(it.asis_adk_prompt_tokens);
        const yTobe = yPos(it.tobe_adk_prompt_tokens);
        bars += `<rect x="${(cx - 20).toFixed(1)}" y="${yAsis.toFixed(1)}" width="18" height="${(baseY - yAsis).toFixed(1)}" rx="3" fill="#EA4335"/>`;
        bars += `<text x="${(cx - 11).toFixed(1)}" y="${(yAsis - 4).toFixed(1)}" text-anchor="middle" font-size="9" fill="#C5221F" font-family="Roboto Mono">${(it.asis_adk_prompt_tokens / 1000).toFixed(1)}K</text>`;
        bars += `<rect x="${(cx + 2).toFixed(1)}" y="${yTobe.toFixed(1)}" width="18" height="${(baseY - yTobe).toFixed(1)}" rx="3" fill="#137333"/>`;
        bars += `<text x="${(cx + 11).toFixed(1)}" y="${(yTobe - 4).toFixed(1)}" text-anchor="middle" font-size="9" font-weight="700" fill="#137333" font-family="Roboto Mono">${(it.tobe_adk_prompt_tokens / 1000).toFixed(1)}K</text>`;
        bars += `<text x="${cx.toFixed(1)}" y="${H - 14}" text-anchor="middle" font-size="10.5" font-weight="600" fill="#202124">T${it.turn}</text>`;
      });
      el.innerHTML = `
        <svg viewBox="0 0 ${W} ${H}" width="100%" height="auto" role="img">
          <line x1="${padL}" y1="${baseY}" x2="${W - padR}" y2="${baseY}" stroke="#DADCE0" stroke-width="1"/>
          <rect x="${padL}" y="4" width="12" height="10" rx="2" fill="#EA4335"/>
          <text x="${padL + 17}" y="13" font-size="11" fill="#5F6368">As-Is</text>
          <rect x="${padL + 70}" y="4" width="12" height="10" rx="2" fill="#137333"/>
          <text x="${padL + 87}" y="13" font-size="11" fill="#5F6368">To-Be</text>
          ${bars}
        </svg>
      `;
    }

    // Yearly cost at list prices, scaled linearly from the measured average cost per turn of the S4 session.
    function updateTcoCalculator() {
      const S = UI_STRINGS;
      const avg = BENCHMARK_DATA.s4_average_per_turn || {};
      const qpd = Number(document.getElementById("rng-qpd").value);
      document.getElementById("lbl-qpd").textContent = `${qpd.toLocaleString()} / day`;
      const fmtUsd = v => "$" + Math.round(v).toLocaleString();
      if (!avg.asis_cost_usd || avg.tobe_cost_usd === null || avg.tobe_cost_usd === undefined) {
        document.getElementById("tco-annual-savings").textContent = "n/a";
        return;
      }
      const yrAsis = qpd * 365 * avg.asis_cost_usd;
      const yrTobe = qpd * 365 * avg.tobe_cost_usd;
      const pct = pctDelta(yrAsis, yrTobe);
      document.getElementById("tco-annual-savings").textContent = `${fmtUsd(yrAsis - yrTobe)} / yr`;
      document.getElementById("tco-annual-savings").style.color = deltaColor(pct);
      document.getElementById("tco-pct-note").textContent = S.tcoPctTemplate.replace("{PCT}", fmtDelta(pct));
      document.getElementById("tco-asis").textContent = fmtUsd(yrAsis);
      document.getElementById("tco-tobe").textContent = fmtUsd(yrTobe);
      document.getElementById("tco-asis-turn").textContent = `$${Number(avg.asis_cost_usd).toFixed(4)} / turn · ${fmtTok(avg.asis_total_input_tokens)} input tok`;
      document.getElementById("tco-tobe-turn").textContent = `$${Number(avg.tobe_cost_usd).toFixed(4)} / turn · ${fmtTok(avg.tobe_total_input_tokens)} input tok`;
    }

    function initPortal() {
      const S = UI_STRINGS;
      document.getElementById("bench-ts").textContent = BENCHMARK_DATA.generated_at_utc;
      renderHeroKpis();

      const disclosureHtml = `<div class="sub-box" style="margin:14px 0;font-size:12.8px;">${S.baselineDisclosureHtml}</div>`;
      const heroGrid = document.getElementById("hero-kpi-grid");
      if (heroGrid) heroGrid.insertAdjacentHTML("afterend", disclosureHtml);
      const benchDesc = document.querySelector("#benchmarks .section-desc");
      if (benchDesc) benchDesc.insertAdjacentHTML("afterend", disclosureHtml);

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

      document.getElementById("rng-qpd").addEventListener("input", updateTcoCalculator);

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
        "k1Label": "S1 · BQCA input tokens per turn",
        "k1Sub": "To-Be vs As-Is, from Cloud Trace.",
        "k2Label": "S1 · Total input tokens (ADK + BQCA)",
        "k2Sub": "To-Be vs As-Is for the same question.",
        "k3Label": "S4 · Average total input per turn",
        "k3Sub": "Cost per turn at list prices:",
        "k4Label": "S5 · Recall in a new session",
        "k4Unit": "BQCA calls",
        "k4Sub": "To-Be answered from memory in",
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
        "S1": "S1 · Routing & Schema Scoping",
        "S2": "S2 · Follow-Up Context",
        "S3": "S3 · Domain Switch & Fan-Out",
        "S4": "S4 · 8-Turn Token Development",
        "S5": "S5 · New Session Recall",
    },
    "scenarioBadge": "Empirical A/B Verification",
    "challengeLabel": "As-Is PoC Bottleneck",
    "mechanismLabel": "To-Be Best Practice Mechanism",
    "btnRunDisabled": "Live Re-Run Available on Cloud Run Deployment",
    "callingEndpoint": "Calling Vertex AI ADK + geminidataanalytics.googleapis.com/v1 live",
    "liveConnected": "Live GCP Connected ({PROJ})",
    "tcoPctTemplate": "{PCT} yearly cost, To-Be relative to As-Is",
    "trackerEyebrow": "S1 to S5 Tracker · Input Tokens",
    "trackerLiveCountLabel": "steps run live",
    "trackerTitle": "Total Input Tokens per Step: As-Is vs To-Be",
    "trackerDesc": "Bars show ADK prompt tokens plus BQCA input tokens. Baseline rows were measured in the pre-run, with BQCA tokens taken from the Cloud Trace spans of that run. When you run a step, its row switches to your run: ADK tokens are measured and BQCA tokens use the Cloud Trace median per data agent.",
    "trackerLiveTag": "LIVE RUN",
    "trackerBaseTag": "Baseline · measured",
    "layerLabels": {
        "S1": "Router + Scoped Data Agents",
        "S2": "3-Turn Message Window",
        "S3": "Peer Switch & Parallel Calls",
        "S4": "Bounded ADK History",
        "S5": "Session State & Memory",
    },
    "layerShort": {
        "S1": "Schema scoping",
        "S2": "Follow-up context",
        "S3": "Domain switch",
        "S4": "8-turn session",
        "S5": "New session recall",
    },
    "wbBadge": "Interactive Full Live Dual A/B Workbench",
    "wbTitle": "Test Custom Evaluator Prompt Live on GCP",
    "wbSubtitle": "Runs your prompt on both pipelines at once on Google Cloud. As-Is is a plain ADK agent using the built-in data agent tools on one data agent bound to all 32 tables. To-Be is the Root Router with three domain Sub-Agents, each with a data agent bound to 3 to 5 tables.",
    "wbSchemaSummary": "View Available Dataset Schema & Business KPIs",
    "wbSchemaBodyHtml": "<strong>Dataset:</strong> <span class='mono'>cymbal_enterprise_dw</span>, 32 tables with table and column descriptions: thelook e-commerce (<span class='mono'>users, events, orders, order_items, products, inventory_items, distribution_centers</span>) and TPC-DS retail (<span class='mono'>store_sales, web_sales, catalog_sales, returns, inventory, item, customer, promotion</span> and more).<br/><strong>Scenario data:</strong> VIP customer (<span class='mono'>&gt;= $500</span> or <span class='mono'>&gt;= 5 orders</span>), channels (<span class='mono'>Search, Organic, Email, Display</span>), brands (<span class='mono'>Nordic Luxe, TheLook Atelier</span>), distribution centers (<span class='mono'>Memphis TN, Chicago IL</span>). The To-Be data agents cover the thelook tables.",
    "wbPresetLabel": "Quick Evaluator Prompt Variations (Click to Load or Type Any Question Below):",
    "wbPlaceholder": "Enter any analytical question to execute live against both As-Is and To-Be pipelines...",
    "wbBtnRunDual": "Run Full Live Dual A/B on GCP ({CODE}: As-Is vs To-Be)",
    "wbRunningDual": "Streaming Parallel As-Is & To-Be on GCP ({CODE})...",
    "wbBtnAppendTurn": "+ Run this prompt as the next turn of the live S4 session",
    "wbBtnNextStep": "Continue to Next Layer ({NEXT} →)",
    "wbBtnReset": "Reset Live Session & Tracker",
    "wbSseHeader": "Live GCP Parallel SSE Execution Stream",
    "flowTitle": "Live execution flow",
    "flowDesc": "Each ADK event of your run (agent, tool call, tool response) lights the matching element as it arrives, for both pipelines at once.",
    "flowIdle": "Run a step to see the path.",
    "flowReplay": "Replay recorded path",
    "flowLegendActive": "Running now",
    "flowLegendDone": "Used in this turn",
    "flowLegendIdle": "Not used",
    "flowNote": "Each step stays on screen for at least 0.35 s, so the display can trail the run slightly. Steps inside a BQCA chat call (SQL generation, BigQuery execution) are not streamed: the data agent and BigQuery stay lit for the whole call. Session state and callbacks emit no events and are not shown. A replay uses the recorded order, not the recorded timing.",
    "flowStepStart": "Prompt received:",
    "flowNotOnDiagram": "(not on the diagram)",
    "flowReturned": "result returned",
    "flowFanCalls": "{N} BQCA chat calls in parallel",
    "flowFinal": "final answer",
    "flowDone": "Turn finished in",
    "flowNoRootHop": "turn resumed at this sub-agent, no Root Router call",
    "wbLiveCardBadge": "Live Dual A/B Execution Result",
    "wbExecutedPromptLabel": "Custom Prompt Executed",
    "wbLiveS4TableTitle": "Measured ADK prompt tokens per turn in this live session",
    "refBaselineHeading": "Measured Pre-Run Baseline",
    "wbTraceTitleMeasured": "BQCA tier: measured from the Cloud Trace spans of this run",
    "wbTraceNoteMeasured": "BQCA writes its internal LLM calls to Cloud Trace. These figures sum the token usage of the chat calls made in this run. Cost uses list prices.",
    "baselineCardBadge": "Measured baseline run",
    "fanoutHeading": "Measured baseline: one question across three domains",
    "trackerAdkOnly": "ADK only",
    "trackerAvgTag": "8-turn average",
    "chartNoData": "Not enough measured turns to draw this chart.",
    "wbMetricAdk": "ADK prompt tokens, measured (To-Be vs As-Is)",
    "wbMetricCalls": "BQCA chat calls, measured (To-Be vs As-Is)",
    "wbMetricLatency": "Latency, measured (To-Be vs As-Is)",
    "wbMetricLlmCalls": "ADK LLM calls, measured (To-Be vs As-Is)",
    "wbBarTitle": "ADK-tier prompt tokens for this run (Vertex AI usage_metadata)",
    "wbTraceTitle": "BQCA tier: Cloud Trace medians, not measured for this run",
    "wbTraceNote": "The chat API returns no token usage. These figures use the median per chat turn for each data agent called, measured from Cloud Trace. A median covers many runs, so it can differ from the baseline rows, which use the spans of that one pre-run. Cost uses list prices. Calibration time (UTC):",
    "wbTraceUnavailable": "No Cloud Trace calibration exists for one of the data agents called, so BQCA-tier tokens are not shown.",
    "wbPrereqNote": "Turn 1 ran first because this session had no earlier turn:",
    "wbErrorLabel": "Error",
    "wbMsgsPerCall": "messages per BQCA call",
    "wbToolResp": "tool response returned to the root LLM",
    "wbStateTitle": "New session state after this turn:",
    "wbS4Hint": "The first S4 run executes three real warm-up turns on both pipelines before your prompt and takes one to two minutes.",
    "wbPresets": {
        "S1": [
            {"label": "Default: 30-Day VIP Revenue & AOV by Channel", "prompt": "Show VIP customer count, total gross revenue, and average order value (AOV) by acquisition traffic source over the last 30 days."},
            {"label": "Product Margin: Outerwear Return Rate & Profit by Brand", "prompt": "For Women's Outerwear & Coats (order_id >= 9900000), compare gross margin %, return and cancellation rate %, and realized gross profit by brand."},
            {"label": "Supply Chain: Delivery Lead Time & Unsold Inventory by DC", "prompt": "Compare average delivery lead time in days and unsold inventory holding cost ($) across distribution centers for recent orders (order_id >= 9900000)."},
        ],
        "S2": [
            {"label": "Default Follow-Up: Join 14-Day Cart Abandonment to Turn 1", "prompt": "Keep those exact columns from the previous result and join our 14-day cart session count and cart abandonment rate (%) for each traffic_source."},
            {"label": "Follow-Up 2: Filter Previous Channels to Top 3 by AOV", "prompt": "From those exact acquisition channels in our previous query, rank the top 3 channels by average order value (AOV) and show their VIP share."},
            {"label": "Follow-Up 3: Add 90-Day Dormant Customer Count", "prompt": "Using the same traffic_source breakdown from our previous result, add the count of dormant customers with zero orders in the last 90 days."},
        ],
        "S3": [
            {"label": "3-Domain Parallel Root-Cause Fan-Out (Outerwear Profit Drop)", "prompt": "Why is Women's Outerwear & Coats realized profit dropping despite strong VIP sales? Run a parallel cross-domain analysis across: (1) last 30-day VIP orders & gross demand where order_id >= 9900000, (2) Women's 'Outerwear & Coats' unit margin %, return rate %, and realized profit by brand (order_id >= 9900000), and (3) recent Women's Outerwear average delivery lead time in days and unsold holding cost by distribution center (order_id >= 9900000)."},
            {"label": "Peer Switch (0 Root Bounce): Pivot Directly to Supply Chain DC", "prompt": "Now pivot to Supply Chain: compare average delivery lead time in days and unsold inventory holding cost ($) across all distribution centers."},
            {"label": "2-Domain Parallel Check: Brand Returns vs DC Lead Time", "prompt": "Run a parallel cross-domain check comparing Women's Outerwear return rate % by brand (order_id >= 9900000) alongside average delivery lead time by distribution center (order_id >= 9900000)."},
        ],
        "S4": [
            {"label": "Turn 5 Custom Query: DC Delivery Delay & Unsold Holding Cost", "prompt": "Compare average delivery lead time in days and unsold inventory holding cost ($) by distribution center for Women's Outerwear (order_id >= 9900000)."},
            {"label": "Turn 5 Custom Query: VIP Revenue & Order Count by Channel", "prompt": "Show VIP customer count and total gross revenue by traffic_source over the last 30 days."},
            {"label": "Turn 5 Custom Query: Brand Return Rate vs Realized Profit", "prompt": "Compare return and cancellation rate % and realized gross profit ($) between Nordic Luxe and TheLook Atelier (order_id >= 9900000)."},
        ],
        "S5": [
            {"label": "Default Session-B Recall: Summarize Root Cause (0 BQCA Scan)", "prompt": "Without running any BigQuery SQL, inspect my rehydrated profile and long-term memory, summarize the pinned Nordic Luxe and Memphis TN DC #1 root-cause anomaly, and give 2 concrete remediation steps."},
            {"label": "Executive Briefing Recall: Preferred KPIs & Action Plan", "prompt": "Based strictly on my saved analyst profile, preferred KPIs, and long-term memory from Session A, draft a 3-bullet executive action plan without querying BigQuery."},
            {"label": "Audit 4-Scope State & Pinned Insights Status", "prompt": "Inspect my current session and memory status without running SQL, and list my rehydrated analyst role, preferred KPIs, and pinned cross-session insights."},
        ],
    },
}


UI_KO = {
    "heroKpis": {
        "k1Label": "S1 · Turn당 BQCA Input Token",
        "k1Sub": "To-Be vs As-Is, Cloud Trace 기준.",
        "k2Label": "S1 · Input Token 합계 (ADK + BQCA)",
        "k2Sub": "같은 질문에 대한 To-Be vs As-Is.",
        "k3Label": "S4 · Turn당 평균 Input Token 합계",
        "k3Sub": "공시 단가 기준 Turn당 비용:",
        "k4Label": "S5 · 신규 Session 기억 복원",
        "k4Unit": "BQCA 호출",
        "k4Sub": "To-Be가 Memory로 답한 시간:",
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
        "S1": "S1 · Routing과 Schema 분리",
        "S2": "S2 · 후속 질문 문맥",
        "S3": "S3 · Domain 전환과 Fan-out",
        "S4": "S4 · 8-Turn Token 추이",
        "S5": "S5 · 신규 Session 기억 복원",
    },
    "scenarioBadge": "As-Is vs To-Be 실측 대조",
    "challengeLabel": "고객 As-Is 문제상황 (Bottleneck)",
    "mechanismLabel": "제안 To-Be Best Practice 해결 구조",
    "btnRunDisabled": "Cloud Run 배포 URL에서 실시간 재실행 가능",
    "callingEndpoint": "Vertex AI ADK + geminidataanalytics.googleapis.com/v1 실시간 호출 중",
    "liveConnected": "실시간 GCP 연결됨 ({PROJ})",
    "tcoPctTemplate": "To-Be의 연간 비용, As-Is 대비 {PCT}",
    "trackerEyebrow": "S1 ~ S5 Tracker · Input Token",
    "trackerLiveCountLabel": "단계 실시간 실행",
    "trackerTitle": "단계별 Input Token 합계: As-Is vs To-Be",
    "trackerDesc": "막대는 ADK Prompt Token과 BQCA Input Token의 합입니다. 기준치 행은 사전 실행에서 측정했고, BQCA Token은 그 실행의 Cloud Trace Span에서 읽었습니다. 단계를 직접 실행하면 그 행이 실행 결과로 바뀌며, 이때 ADK Token은 실측이고 BQCA Token은 Data Agent별 Cloud Trace 중앙값입니다.",
    "trackerLiveTag": "실시간 실행",
    "trackerBaseTag": "기준치 · 실측",
    "layerLabels": {
        "S1": "Router + Domain별 Data Agent",
        "S2": "3-Turn Message Window",
        "S3": "Peer 전환과 병렬 호출",
        "S4": "ADK 이력 제한",
        "S5": "Session State와 Memory",
    },
    "layerShort": {
        "S1": "Schema 분리",
        "S2": "후속 질문 문맥",
        "S3": "Domain 전환",
        "S4": "8-Turn Session",
        "S5": "신규 Session 복원",
    },
    "wbBadge": "심사자 직접 입력 · Full Live Dual A/B Workbench",
    "wbTitle": "커스텀 Prompt 실시간 GCP 병렬 비교 실행",
    "wbSubtitle": "입력한 질문을 두 구성에서 동시에 실행합니다. As-Is는 32개 Table 전체가 연결된 Data Agent 하나에 ADK 내장 data agent Tool을 그대로 쓰는 Agent입니다. To-Be는 Root Router와 Domain별 Sub-Agent 3개이고, 각 Sub-Agent의 Data Agent에는 Table 3~5개가 연결됩니다.",
    "wbSchemaSummary": "질문 가능한 Dataset Table 및 핵심 KPI 가이드 펼치기",
    "wbSchemaBodyHtml": "<strong>대상 Dataset:</strong> <span class='mono'>cymbal_enterprise_dw</span>, Table과 Column 설명이 붙은 32개 Table입니다. thelook e-commerce(<span class='mono'>users, events, orders, order_items, products, inventory_items, distribution_centers</span>)와 TPC-DS 소매 Table(<span class='mono'>store_sales, web_sales, catalog_sales, returns, inventory, item, customer, promotion</span> 등)로 구성됩니다.<br/><strong>Scenario 데이터:</strong> VIP 고객(<span class='mono'>$500 이상</span> 또는 <span class='mono'>5회 이상 주문</span>), 유입 채널(<span class='mono'>Search, Organic, Email, Display</span>), Brand(<span class='mono'>Nordic Luxe, TheLook Atelier</span>), 물류센터(<span class='mono'>Memphis TN, Chicago IL</span>). To-Be Data Agent는 thelook Table을 다룹니다.",
    "wbPresetLabel": "단계별 추천 실험 Prompt (클릭하여 불러오거나 아래 입력창에 자유롭게 수정·입력하세요):",
    "wbPlaceholder": "검증하고 싶은 분석 질문을 영문 또는 한국어로 자유롭게 입력하세요...",
    "wbBtnRunDual": "GCP 실시간 Dual A/B 병렬 실행 ({CODE}: As-Is vs To-Be 동시 비교)",
    "wbRunningDual": "GCP에서 {CODE} As-Is 및 To-Be 동시 병렬 실행 및 계측 중...",
    "wbBtnAppendTurn": "+ 이 질문을 현재 S4 Session의 다음 Turn으로 실행",
    "wbBtnNextStep": "다음 개선 단계({NEXT} →)로 이어서 진행",
    "wbBtnReset": "실시간 Session 및 그래프 초기화",
    "wbSseHeader": "실시간 GCP Dual A/B 병렬 SSE 실행 타임라인",
    "flowTitle": "실시간 실행 흐름",
    "flowDesc": "실행 중 발생하는 ADK Event(Agent, Tool 호출, Tool 응답)가 도착하는 순서대로 해당 요소를 켭니다. 두 Pipeline을 동시에 표시합니다.",
    "flowIdle": "단계를 실행하면 경로가 표시됩니다.",
    "flowReplay": "기록된 경로 다시 보기",
    "flowLegendActive": "현재 실행 중",
    "flowLegendDone": "이번 Turn에서 사용됨",
    "flowLegendIdle": "사용 안 됨",
    "flowNote": "각 단계는 최소 0.35초 동안 표시되므로 화면이 실제 실행보다 조금 늦을 수 있습니다. BQCA Chat 호출 내부 단계(SQL 생성, BigQuery 실행)는 Stream되지 않아, 호출이 끝날 때까지 Data Agent와 BigQuery가 켜진 상태로 유지됩니다. Session State와 Callback은 Event를 내지 않으므로 표시하지 않습니다. 다시 보기는 기록된 순서를 따르며 실제 소요 시간은 반영하지 않습니다.",
    "flowStepStart": "Prompt 수신:",
    "flowNotOnDiagram": "(Diagram에 없는 항목)",
    "flowReturned": "결과 반환",
    "flowFanCalls": "BQCA Chat 호출 {N}건 병렬 실행",
    "flowFinal": "최종 답변",
    "flowDone": "Turn 완료, 소요 시간",
    "flowNoRootHop": "이 Sub-Agent에서 Turn 재개, Root Router 호출 없음",
    "wbLiveCardBadge": "심사자 입력 실시간 Dual A/B 실행 결과",
    "wbExecutedPromptLabel": "실행된 입력 Prompt",
    "wbLiveS4TableTitle": "이번 실시간 Session의 Turn별 ADK Prompt Token 실측치",
    "refBaselineHeading": "사전 실행 실측 기준치",
    "wbTraceTitleMeasured": "BQCA 계층: 이 실행의 Cloud Trace Span에서 측정",
    "wbTraceNoteMeasured": "BQCA는 내부 LLM 호출을 Cloud Trace에 기록합니다. 이 실행에서 발생한 Chat 호출의 Token 사용량을 합산했고, 비용은 공시 단가 기준입니다.",
    "baselineCardBadge": "실측 기준 실행",
    "fanoutHeading": "실측 기준치: 세 Domain에 걸친 질문",
    "trackerAdkOnly": "ADK만",
    "trackerAvgTag": "8-Turn 평균",
    "chartNoData": "Chart를 그릴 만큼 측정된 Turn이 없습니다.",
    "wbMetricAdk": "ADK Prompt Token 실측 (To-Be vs As-Is)",
    "wbMetricCalls": "BQCA Chat 호출 수 실측 (To-Be vs As-Is)",
    "wbMetricLatency": "Latency 실측 (To-Be vs As-Is)",
    "wbMetricLlmCalls": "ADK LLM 호출 수 실측 (To-Be vs As-Is)",
    "wbBarTitle": "이번 실행의 ADK 계층 Prompt Token (Vertex AI usage_metadata)",
    "wbTraceTitle": "BQCA 계층: Cloud Trace 중앙값이며 이번 실행의 측정값이 아님",
    "wbTraceNote": "Chat API는 Token 사용량을 반환하지 않습니다. 호출된 Data Agent별로 Cloud Trace에서 측정한 Chat Turn당 중앙값을 사용했고, 비용은 공시 단가 기준입니다. 중앙값은 여러 실행을 합친 값이라, 사전 실행 한 번의 Span을 그대로 쓴 기준치 행과 다를 수 있습니다. 측정 시각(UTC):",
    "wbTraceUnavailable": "호출된 Data Agent 중 Cloud Trace 측정값이 없는 것이 있어 BQCA 계층 Token은 표시하지 않습니다.",
    "wbPrereqNote": "이 Session에 선행 Turn이 없어 Turn 1을 먼저 실행했습니다:",
    "wbErrorLabel": "오류",
    "wbMsgsPerCall": "BQCA 호출당 Message 수",
    "wbToolResp": "Root LLM에 반환된 Tool 응답",
    "wbStateTitle": "이번 Turn 이후 신규 Session State:",
    "wbS4Hint": "S4 첫 실행은 입력한 질문 앞에 실제 Turn 3개를 두 구성 모두에서 먼저 실행하므로 1~2분이 걸립니다.",
    "wbPresets": {
        "S1": [
            {"label": "기본 검증: 최근 30일 유입 채널별 VIP 고객수·매출·AOV", "prompt": "Show VIP customer count, total gross revenue, and average order value (AOV) by acquisition traffic source over the last 30 days."},
            {"label": "상품 Margin 변형: 여성 아우터 Brand별 반품률 및 실현 이익 비교", "prompt": "For Women's Outerwear & Coats (order_id >= 9900000), compare gross margin %, return and cancellation rate %, and realized gross profit by brand."},
            {"label": "물류 DC 변형: 물류센터별 평균 배송 소요일 및 미판매 재고 원가", "prompt": "Compare average delivery lead time in days and unsold inventory holding cost ($) across distribution centers for recent orders (order_id >= 9900000)."},
        ],
        "S2": [
            {"label": "기본 후속 질문: 직전 결과 채널 유지 + 14일 장바구니 이탈률 결합", "prompt": "Keep those exact columns from the previous result and join our 14-day cart session count and cart abandonment rate (%) for each traffic_source."},
            {"label": "후속 변형 2: 직전 조회 채널 중 AOV 상위 3개 채널 추출", "prompt": "From those exact acquisition channels in our previous query, rank the top 3 channels by average order value (AOV) and show their VIP share."},
            {"label": "후속 변형 3: 동일 유입 채널 기준 90일 휴면 고객 수 추가 결합", "prompt": "Using the same traffic_source breakdown from our previous result, add the count of dormant customers with zero orders in the last 90 days."},
        ],
        "S3": [
            {"label": "3-Domain 병렬 원인 규명: VIP 호조 속 아우터 수익 급감 원인", "prompt": "Why is Women's Outerwear & Coats realized profit dropping despite strong VIP sales? Run a parallel cross-domain analysis across: (1) last 30-day VIP orders & gross demand where order_id >= 9900000, (2) Women's 'Outerwear & Coats' unit margin %, return rate %, and realized profit by brand (order_id >= 9900000), and (3) recent Women's Outerwear average delivery lead time in days and unsold holding cost by distribution center (order_id >= 9900000)."},
            {"label": "Peer 직접 전환(Root 생략): 마케팅에서 물류 DC 배송 지연으로 즉시 전환", "prompt": "Now pivot to Supply Chain: compare average delivery lead time in days and unsold inventory holding cost ($) across all distribution centers."},
            {"label": "2-Domain 병렬 비교: Brand별 반품률 vs 물류센터별 배송 소요일", "prompt": "Run a parallel cross-domain check comparing Women's Outerwear return rate % by brand (order_id >= 9900000) alongside average delivery lead time by distribution center (order_id >= 9900000)."},
        ],
        "S4": [
            {"label": "Turn 5 커스텀 검증: 물류센터별 평균 배송 소요일 및 미판매 재고 비용", "prompt": "Compare average delivery lead time in days and unsold inventory holding cost ($) by distribution center for Women's Outerwear (order_id >= 9900000)."},
            {"label": "Turn 5 커스텀 검증: 최근 30일 채널별 VIP 고객 수 및 총매출", "prompt": "Show VIP customer count and total gross revenue by traffic_source over the last 30 days."},
            {"label": "Turn 5 커스텀 검증: Nordic Luxe vs TheLook Atelier 반품률·실현이익", "prompt": "Compare return and cancellation rate % and realized gross profit ($) between Nordic Luxe and TheLook Atelier (order_id >= 9900000)."},
        ],
        "S5": [
            {"label": "기본 신규 Session-B 복원: BigQuery 재실행 없이 핵심 원인 및 대책 요약", "prompt": "Without running any BigQuery SQL, inspect my rehydrated profile and long-term memory, summarize the pinned Nordic Luxe and Memphis TN DC #1 root-cause anomaly, and give 2 concrete remediation steps."},
            {"label": "임원 보고 요약: 저장된 선호 KPI 및 직무 기반 3줄 실행 계획 도출", "prompt": "Based strictly on my saved analyst profile, preferred KPIs, and long-term memory from Session A, draft a 3-bullet executive action plan without querying BigQuery."},
            {"label": "4-Scope State 및 영속 Memory 저장 상태 즉시 점검", "prompt": "Inspect my current session and memory status without running SQL, and list my rehydrated analyst role, preferred KPIs, and pinned cross-session insights."},
        ],
    },
}


KO_SCENARIO_OVERRIDES = {
    "S1": {
        "track": "Routing과 Schema 분리",
        "title": "통합 Data Agent 하나 vs Router와 Domain별 Data Agent",
        "challenge": "As-Is Agent는 모든 질문을 Warehouse 전체(설명이 붙은 32개 Table)와 모든 Domain 용어집이 연결된 Data Agent 하나로 보냅니다. BQCA는 내부 LLM 호출마다 그 Schema를 다시 읽습니다.",
        "architecture_mechanism": "Root Router가 질문을 Sub-Agent 3개 중 하나로 넘깁니다. 각 Sub-Agent는 Table 3~5개와 자기 Domain 용어집만 연결된 Data Agent를 호출하므로, BQCA가 호출마다 읽는 Context가 작습니다.",
    },
    "S2": {
        "track": "Stateless Chat API에서의 Multi-Turn 문맥",
        "title": "후속 질문: 호출당 Message 1개 vs 3-Turn Message Window",
        "challenge": "ADK 내장 ask_data_agent Tool은 현재 질문만 BQCA에 보냅니다. 이전 결과를 가리키는 후속 질문에서는 Root LLM이 문맥을 직접 다시 써 주지 않으면 Data Agent가 이전 내용을 알 수 없습니다.",
        "architecture_mechanism": "Sub-Agent가 Domain별로 최근 3개 문답을 ADK Session State에 보관하고 새 질문과 함께 보냅니다. 서버 측 대화 없이도 BQCA가 이전 Turn을 봅니다.",
    },
    "S3": {
        "track": "Domain 전환과 병렬 Fan-out",
        "title": "Session 도중 Domain 전환, 그리고 세 Domain 동시 질문",
        "challenge": "Data Agent가 하나면 Domain 전환도 같은 큰 Context에 던지는 또 하나의 질문일 뿐이고, 여러 Domain에 걸친 질문은 긴 호출 하나로 처리됩니다.",
        "architecture_mechanism": "Sub-Agent가 다른 Domain의 Sub-Agent로 직접 넘길 수 있습니다. 여러 Domain에 걸친 질문은 Root Router가 Domain별 Data Agent를 동시에 호출한 뒤 하나로 정리합니다.",
    },
    "S4": {
        "track": "긴 Session의 Token 증가",
        "title": "연속 8 Turn: ADK와 BQCA Input Token의 변화",
        "challenge": "As-Is Agent는 LLM 호출마다 ask_data_agent 원본 응답을 포함한 Session 전체를 재전송하므로, Turn이 늘수록 ADK Prompt가 커집니다.",
        "architecture_mechanism": "To-Be Agent는 최근 3개 User Turn만 Prompt에 유지하고, Data 호출 결과는 답변과 행 수를 제한한 Table만 보관하며, 단일 Domain Turn은 요약용 LLM 호출 없이 Tool 결과로 끝냅니다.",
    },
    "S5": {
        "track": "Session State와 Session 간 Memory",
        "title": "새 Session에서 이전 작업을 묻는 질문",
        "challenge": "As-Is Agent에는 Session 간 Memory가 없습니다. 새 Session에서는 이전 결과를 참조할 수 없어 분석을 다시 요청해야 합니다.",
        "architecture_mechanism": "To-Be Root Router는 사용자 Profile과 고정한 Insight를 User Scope State와 Memory Service에 보관하고, 기억을 묻는 질문에는 BQCA 호출 없이 답합니다.",
    },
}


def build_ko_benchmark_data(en_data: dict) -> dict:
    ko_data = copy.deepcopy(en_data)
    for sc in ko_data["scenarios"]:
        sc.update(KO_SCENARIO_OVERRIDES.get(sc["code"], {}))
    return ko_data


CALIBRATION_JSON = BENCHMARK_JSON.parent / "bqca_trace_token_calibration.json"


def build_disclosure_html(lang: str, data: dict) -> str:
    """States how the baseline numbers were produced and what the live workbench measures."""
    day = str(data.get("generated_at_utc", ""))[:10]
    env = data.get("environment", {})
    adk = env.get("adk_version", "")
    if lang == "ko":
        return (
            f"<strong>수치 산출 방법.</strong> 두 구성 모두 {day}에 Google Cloud에서 실제로 실행했습니다(<span class='mono'>google-adk {adk}</span>). "
            "ADK 계층 Token은 Vertex AI usage_metadata, BQCA 계층 Token은 각 실행에서 발생한 Chat 호출의 Cloud Trace Span에서 읽었고, 가정으로 계산한 값은 없습니다. "
            "Warehouse는 기업 규모 Schema를 재현한 합성 구성입니다. thelook 7개와 TPC-DS 25개, 모두 32개 Table에 규칙으로 생성한 Table·Column 설명을 붙였습니다. "
            "As-Is는 32개 Table 전체와 모든 Domain 용어집을 Data Agent 하나에 연결하고, To-Be는 Domain별 Data Agent에 Table 3~5개를 연결합니다. "
            "실시간 Workbench 실행에서는 ADK 계층을 직접 측정하고, Chat API가 Token 사용량을 반환하지 않으므로 BQCA 계층은 Data Agent별 Cloud Trace 중앙값을 표시합니다."
        )
    return (
        f"<strong>How these numbers were produced.</strong> Both pipelines ran on Google Cloud on {day} (<span class='mono'>google-adk {adk}</span>). "
        "ADK-tier tokens come from Vertex AI usage_metadata. BQCA-tier tokens come from the Cloud Trace spans of the chat calls made in each run. Nothing is modeled. "
        "The warehouse is a synthetic reproduction of an enterprise-scale schema: 32 tables (thelook 7 and TPC-DS 25) with table and column descriptions generated by rule. "
        "As-Is binds all 32 tables and every domain glossary to one data agent. To-Be binds 3 to 5 tables to each domain data agent. "
        "Live workbench runs measure the ADK tier directly and show the Cloud Trace median per data agent for the BQCA tier, because the chat API returns no token usage."
    )


def render_page(template: str, data_obj: dict, ui_obj: dict) -> str:
    return (
        template.replace("__SHARED_CSS__", SHARED_CSS)
        .replace("__BENCHMARK_JSON_PAYLOAD__", json.dumps(data_obj, ensure_ascii=False))
        .replace("__UI_STRINGS_PAYLOAD__", json.dumps(ui_obj, ensure_ascii=False))
        .replace("__FLOW_MAP_PAYLOAD__", json.dumps(FLOW_MAP))
        .replace("__FLOW_SVG_PAYLOAD__", json.dumps(load_flow_svg(), ensure_ascii=False).replace("</", "<\\/"))
        .replace("__PORTAL_JS__", PORTAL_JS)
    )


def main() -> None:
    en_data = json.loads(BENCHMARK_JSON.read_text(encoding="utf-8"))
    ko_data = build_ko_benchmark_data(en_data)

    UI_EN["baselineDisclosureHtml"] = build_disclosure_html("en", en_data)
    UI_KO["baselineDisclosureHtml"] = build_disclosure_html("ko", en_data)

    html_en = render_page(HTML_EN, en_data, UI_EN)
    html_ko = render_page(HTML_KO, ko_data, UI_KO)

    OUT_HTML_EN.write_text(html_en, encoding="utf-8")
    OUT_HTML_KO.write_text(html_ko, encoding="utf-8")
    print(f"[OK] Generated EN portal: {OUT_HTML_EN} ({len(html_en):,} bytes)")
    print(f"[OK] Generated KO portal: {OUT_HTML_KO} ({len(html_ko):,} bytes)")


if __name__ == "__main__":
    main()
