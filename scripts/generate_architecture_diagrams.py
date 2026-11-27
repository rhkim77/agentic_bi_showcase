#!/usr/bin/env python3
"""Generates the 4 architecture diagrams (SVG + 3x PNG) in `docs/diagrams/`.

Icons come from `scripts/assets/diagram_icons.svg`. Every token figure printed on a diagram is read
from `benchmarks/scenario_benchmark_results.json` and `benchmarks/bqca_trace_token_calibration.json`,
so re-run this script after re-running the benchmarks. Requires PyGObject (Rsvg) and pycairo."""

from __future__ import annotations

import html
import json
from pathlib import Path
import re
import gi

gi.require_version("Rsvg", "2.0")
from gi.repository import Rsvg  # noqa: E402
import cairo  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "docs" / "diagrams"
OUT_DIR.mkdir(parents=True, exist_ok=True)

ICONS_SVG = Path(__file__).resolve().parent / "assets" / "diagram_icons.svg"
BENCH_JSON = REPO_ROOT / "benchmarks" / "scenario_benchmark_results.json"
CALIB_JSON = REPO_ROOT / "benchmarks" / "bqca_trace_token_calibration.json"


def _load_numbers() -> dict:
    """Reads every number printed on the diagrams from the measured benchmark files."""
    bench = json.loads(BENCH_JSON.read_text(encoding="utf-8"))
    calib = json.loads(CALIB_JSON.read_text(encoding="utf-8"))["per_data_agent"]
    sc = {s["code"]: s for s in bench["scenarios"]}

    def est(code: str, key: str = "result") -> dict:
        return sc[code][key]["comparison_summary"]["trace_estimate"]

    def pct(v: float) -> str:
        return f"{v:+.1f}%".replace("+-", "-")

    curve = bench["s4_turn_curve"]
    avg = bench["s4_average_per_turn"]
    asis_adk = [t["asis_adk_prompt_tokens"] for t in curve]
    tobe_adk = [t["tobe_adk_prompt_tokens"] for t in curve]
    s1, s3, fan, s4 = est("S1"), est("S3"), est("S3", "fanout"), est("S4")
    return {
        "s1_tobe": s1["tobe_total_input_tokens"], "s1_asis": s1["asis_total_input_tokens"],
        "s1_pct": pct(s1["total_input_delta_pct"]),
        "s3_pct": pct(s3["total_input_delta_pct"]),
        "fan_tobe": fan["tobe_total_input_tokens"], "fan_asis": fan["asis_total_input_tokens"],
        "fan_pct": pct(fan["total_input_delta_pct"]),
        "fan_calls_tobe": sc["S3"]["fanout"]["comparison_summary"]["measured"]["tobe_bqca_calls"],
        "fan_calls_asis": sc["S3"]["fanout"]["comparison_summary"]["measured"]["asis_bqca_calls"],
        "t8_asis": s4["asis_total_input_tokens"], "t8_pct": pct(s4["total_input_delta_pct"]),
        "s4_avg_pct": pct((avg["tobe_total_input_tokens"] / avg["asis_total_input_tokens"] - 1) * 100),
        "asis_adk_first": asis_adk[0], "asis_adk_last": asis_adk[-1],
        "tobe_adk_min": min(tobe_adk), "tobe_adk_max": max(tobe_adk),
        "med_customer": calib["cymbal_customer_marketing_ca"]["median_input_tokens_per_turn"],
        "med_product": calib["cymbal_product_profitability_ca"]["median_input_tokens_per_turn"],
        "med_supply": calib["cymbal_supply_chain_ca"]["median_input_tokens_per_turn"],
        "med_mono": calib["cymbal_enterprise_monolithic_ca"]["median_input_tokens_per_turn"],
    }


N = _load_numbers()

FONT_STACK = "Roboto, Arial, 'Liberation Sans', sans-serif"

BLUE = "#1A73E8"
BLUE_DARK = "#174EA6"
BLUE_LIGHT = "#E8F0FE"
BLUE_TINT = "#F4F8FE"

GREEN_DARK = "#137333"
GREEN_BORDER = "#34A853"
GREEN_LIGHT = "#E6F4EA"
GREEN_TINT = "#F6FBF7"

AMBER_DARK = "#C56200"
YELLOW_BORDER = "#F9AB00"
YELLOW_FILL = "#FFFDF5"
YELLOW_LIGHT = "#FEF7E0"

RED_DARK = "#C5221F"
RED_BORDER = "#EA4335"
RED_LIGHT = "#FCE8E6"

GREY = "#5F6368"
GREY_BORDER = "#80868B"
GREY_LIGHT = "#E8EAED"
GREY_TINT = "#F8F9FA"

TEXT_MAIN = "#202124"
TEXT_SUB = "#3C4043"
TEXT_MUTED = "#80868B"
DIVIDER = "#E8EAED"


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def approx_w(text: str, fs: float) -> float:
    w = 0.0
    for ch in text:
        if ch in "ilI.,:;|!·' ":
            w += 0.30 * fs
        elif ch in "mwMW@%&":
            w += 0.82 * fs
        elif ch.isupper() or ch.isdigit():
            w += 0.62 * fs
        else:
            w += 0.54 * fs
    return w


SYMBOLS = "\n    ".join(
    re.findall(r"<symbol .*?</symbol>", ICONS_SVG.read_text(encoding="utf-8"), re.S)
)


def marker_def(mid: str, color: str, reverse: bool = False) -> str:
    if reverse:
        path = f'<path d="M 9 1 L 1 5 L 9 9 z" fill="{color}"/>'
        ref_x = "2"
    else:
        path = f'<path d="M 1 1 L 9 5 L 1 9 z" fill="{color}"/>'
        ref_x = "8"
    return (
        f'    <marker id="{mid}" viewBox="0 0 10 10" refX="{ref_x}" refY="5" '
        f'markerUnits="userSpaceOnUse" markerWidth="10" markerHeight="10" orient="auto">'
        f"{path}</marker>"
    )


MARKERS = "\n".join([
    marker_def("arrow-green", GREEN_BORDER),
    marker_def("arrow-blue", BLUE),
    marker_def("arrow-grey", GREY),
    marker_def("arrow-amber", AMBER_DARK),
    marker_def("arrow-amber-start", AMBER_DARK, reverse=True),
    marker_def("arrow-red", RED_BORDER),
])


def wrap_and_render(stem: str, w: int, h: int, body_parts: list[str]) -> None:
    svg_txt = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" font-family="{FONT_STACK}">
  <defs>
    <filter id="card-shadow" x="-4%" y="-4%" width="108%" height="110%">
      <feDropShadow dx="0" dy="1.5" stdDeviation="2" flood-color="#202124" flood-opacity="0.06"/>
    </filter>
{MARKERS}
    {SYMBOLS}
  </defs>
  <rect x="0" y="0" width="{w}" height="{h}" fill="#FFFFFF"/>
{chr(10).join(body_parts)}
</svg>
"""
    svg_path = OUT_DIR / f"{stem}.svg"
    png_path = OUT_DIR / f"{stem}.png"
    svg_path.write_text(svg_txt, encoding="utf-8")

    scale = 3
    handle = Rsvg.Handle.new_from_file(str(svg_path))
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w * scale, h * scale)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(1.0, 1.0, 1.0)
    ctx.paint()
    ctx.scale(scale, scale)
    vp = Rsvg.Rectangle()
    vp.x, vp.y, vp.width, vp.height = 0, 0, w, h
    handle.render_document(ctx, vp)
    surface.write_to_png(str(png_path))
    print(f"[OK] {stem}.svg & {stem}.png ({w * scale}x{h * scale})")


def draw_lane(parts: list[str], x: int, y: int, w: int, h: int, border: str, fill: str, tcolor: str,
              title: str, badge: str, bbg: str, bfg: str) -> None:
    parts.append(f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" ry="12" fill="{fill}" stroke="{border}" stroke-width="2"/>')
    parts.append(f'  <line x1="{x + 20}" y1="{y + 46}" x2="{x + w - 20}" y2="{y + 46}" stroke="#DADCE0" stroke-width="1"/>')
    parts.append(f'  <text x="{x + 20}" y="{y + 30}" font-size="15.5" font-weight="700" fill="{tcolor}">{esc(title)}</text>')
    bw = int(approx_w(badge, 11.5) + 28)
    bx, by = x + w - 20 - bw, y + 11
    parts.append(f'  <rect x="{bx}" y="{by}" width="{bw}" height="24" rx="12" ry="12" fill="{bbg}"/>')
    parts.append(f'  <text x="{bx + bw / 2:.1f}" y="{by + 16}" text-anchor="middle" font-size="11.5" font-weight="700" fill="{bfg}">{esc(badge)}</text>')


def draw_card(parts: list[str], x: int, y: int, w: int, h: int, border: str, icon: str, title: str,
              bullets: list[str], fill: str = "#FFFFFF") -> None:
    parts.append(f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" ry="10" fill="{fill}" stroke="{border}" stroke-width="2" filter="url(#card-shadow)"/>')
    parts.append(f'  <use href="#{icon}" x="{x + 14}" y="{y + 11}" width="32" height="32"/>')
    parts.append(f'  <text x="{x + 54}" y="{y + 32}" font-size="13.2" font-weight="700" fill="{TEXT_MAIN}">{esc(title)}</text>')
    parts.append(f'  <line x1="{x + 14}" y1="{y + 52}" x2="{x + w - 14}" y2="{y + 52}" stroke="{DIVIDER}" stroke-width="1"/>')
    for j, bl in enumerate(bullets):
        parts.append(f'  <text x="{x + 16}" y="{y + 74 + j * 21}" font-size="11.4" font-weight="400" fill="{TEXT_SUB}">{esc(bl)}</text>')


def draw_h_arrow(parts: list[str], x1: int, y: int, x2: int, color: str, mend: str, labels: list[str],
                 mstart: str = "", dashed: bool = False) -> None:
    dash = ' stroke-dasharray="7 5"' if dashed else ""
    ms = f' marker-start="url(#{mstart})"' if mstart else ""
    sx = x1 + (10 if mstart else 3)
    ex = x2 - 10
    parts.append(f'  <line x1="{sx}" y1="{y}" x2="{ex}" y2="{y}" stroke="{color}" stroke-width="2.2"{dash}{ms} marker-end="url(#{mend})"/>')
    if labels:
        mx = (x1 + x2) / 2.0
        lw = max(76, int(max(approx_w(s, 11.0) for s in labels) + 20))
        lh = 15 * len(labels) + 10
        ly = y - lh - 9
        parts.append(f'  <rect x="{mx - lw / 2:.1f}" y="{ly:.1f}" width="{lw}" height="{lh}" rx="6" ry="6" fill="#FFFFFF" stroke="#DADCE0" stroke-width="1"/>')
        for idx, ll in enumerate(labels):
            fw = "700" if idx == 0 else "500"
            fc = TEXT_MAIN if idx == 0 else TEXT_SUB
            parts.append(f'  <text x="{mx:.1f}" y="{ly + 14.5 + idx * 15:.1f}" text-anchor="middle" font-size="10.8" font-weight="{fw}" fill="{fc}">{esc(ll)}</text>')


def draw_v_arrow(parts: list[str], x: int, y1: int, y2: int, color: str, mend: str, label: str = "",
                 mstart: str = "") -> None:
    ms = f' marker-start="url(#{mstart})"' if mstart else ""
    sy = y1 + (10 if mstart else 3)
    ey = y2 - 10
    parts.append(f'  <line x1="{x}" y1="{sy}" x2="{x}" y2="{ey}" stroke="{color}" stroke-width="2.2"{ms} marker-end="url(#{mend})"/>')
    if label:
        my = (y1 + y2) / 2.0
        lw = int(approx_w(label, 11.0) + 22)
        parts.append(f'  <rect x="{x - lw / 2:.1f}" y="{my - 11:.1f}" width="{lw}" height="22" rx="6" ry="6" fill="#FFFFFF" stroke="#DADCE0" stroke-width="1"/>')
        parts.append(f'  <text x="{x}" y="{my + 4:.1f}" text-anchor="middle" font-size="10.8" font-weight="700" fill="{TEXT_MAIN}">{esc(label)}</text>')


# ==============================================================================
# FIGURE 1: 3-Tier End-to-End System Architecture (1400 x 804)
# ==============================================================================
def build_fig1() -> None:
    p: list[str] = []
    # Tier 1 (Top): Orchestration & State Layer
    draw_lane(
        p, 20, 16, 1360, 232, BLUE, BLUE_TINT, BLUE_DARK,
        "Tier 1 — Google ADK Multi-Agent Orchestration & 4-Scope State Layer (Vertex AI Gemini 2.5 Flash)",
        "Flat ADK Prompt per Turn + Cross-Session Memory", BLUE_LIGHT, BLUE_DARK
    )
    draw_card(p, 44, 76, 260, 154, BLUE, "icon-mdi-person", "Enterprise Analyst / API", [
        "• Single & Multi-Domain Queries",
        "• Follow-up Pronoun Chaining",
        "• Cross-Session KPI Continuity",
    ])
    draw_card(p, 414, 76, 316, 154, GREEN_BORDER, "icon-vertex-ai", "ADK Root Router & Sub-Agents", [
        "• LlmAgent + transfer_to_agent",
        "• Peer-to-Peer Sub-Agent Handoff",
        "• ThreadPoolExecutor Parallel Fan-out",
        "• Static Agent ID Tool Binding",
    ])
    draw_card(p, 844, 76, 512, 154, YELLOW_BORDER, "icon-cloud-sql", "ADK 4-Scope Session.state & MemoryService Bank", [
        "• temp:* : Raw SQL & 20-row preview buffer (auto-evicted post-turn)",
        "• session : Per-domain [-6:] (3-turn) sliding window & query history",
        "• user:* & app:* : Persistent role/KPI profile & execution telemetry",
        "• MemoryService : after_agent_callback indexing + load_memory recall",
    ], fill=YELLOW_FILL)
    draw_h_arrow(p, 304, 153, 414, BLUE, "arrow-blue", ["NL Query"])
    draw_h_arrow(p, 730, 153, 844, AMBER_DARK, "arrow-amber", ["4-Scope R/W"], mstart="arrow-amber-start")

    # Vertical Fan-out Connectors Tier 1 -> Tier 2
    draw_v_arrow(p, 236, 248, 296, GREEN_BORDER, "arrow-green", "Domain 1 :chat (Stateless)")
    draw_v_arrow(p, 700, 248, 296, GREEN_BORDER, "arrow-green", "Domain 2 :chat (Stateless)")
    draw_v_arrow(p, 1164, 248, 296, GREEN_BORDER, "arrow-green", "Domain 3 :chat (Stateless)")

    # Tier 2 (Middle): 3 Domain-Scoped BigQuery CAA Data Agents
    draw_lane(
        p, 20, 296, 1360, 236, GREEN_BORDER, GREEN_TINT, GREEN_DARK,
        "Tier 2 — Domain-Scoped BigQuery Conversational Analytics (CAA) Layer (geminidataanalytics.googleapis.com)",
        f"S1 Total Input: {N['s1_tobe']:,} vs {N['s1_asis']:,} Tokens ({N['s1_pct']})", GREEN_LIGHT, GREEN_DARK
    )
    draw_card(p, 44, 358, 384, 156, GREEN_BORDER, "icon-bigquery", "Domain 1: Customer & Funnel CAA", [
        "• ID : cymbal_customer_marketing_ca",
        "• Scoped Tables (4) : users, events, orders, order_items",
        "• Glossary : VIP (>= $500 / >= 5 orders), Churn, AOV, Cart%",
        f"• BQCA Input / Turn (Uncached Median) : {N['med_customer']:,}",
    ])
    draw_card(p, 508, 358, 384, 156, GREEN_BORDER, "icon-bigquery", "Domain 2: Product & Margin CAA", [
        "• ID : cymbal_product_profitability_ca",
        "• Scoped Tables (3) : products, order_items, orders",
        "• Glossary : Gross Margin %, Net Rev, Realized Profit, Return%",
        f"• BQCA Input / Turn (Uncached Median) : {N['med_product']:,}",
    ])
    draw_card(p, 972, 358, 384, 156, GREEN_BORDER, "icon-bigquery", "Domain 3: Supply Chain & DC CAA", [
        "• ID : cymbal_supply_chain_ca",
        "• Scoped Tables (5) : distribution_centers, inventory_items + 3",
        "• Glossary : Avg Delivery Lead Time, Unsold Inventory Cost",
        f"• BQCA Input / Turn (Uncached Median) : {N['med_supply']:,}",
    ])

    # Vertical Connectors Tier 2 -> Tier 3
    draw_v_arrow(p, 236, 532, 580, BLUE, "arrow-blue", "Governed SQL")
    draw_v_arrow(p, 700, 532, 580, BLUE, "arrow-blue", "Governed SQL")
    draw_v_arrow(p, 1164, 532, 580, BLUE, "arrow-blue", "Governed SQL")

    # Tier 3 (Bottom): BigQuery Data & Scoped Business Glossary Layer
    draw_lane(
        p, 20, 580, 1360, 208, GREY_BORDER, GREY_TINT, TEXT_MAIN,
        "Tier 3 — BigQuery Enterprise Data Warehouse & Scoped Business Glossary",
        "Synthetic Demo Schema Built from Public Datasets", GREY_LIGHT, TEXT_SUB
    )
    draw_card(p, 44, 640, 620, 132, BLUE, "icon-bigquery", "BigQuery Dataset cymbal_enterprise_dw (32 Documented Tables · 504 Columns)", [
        "• Copied from bigquery-public-data: thelook_ecommerce (7 tables) + tpc_ds_1g (25 tables)",
        "• Table and column descriptions on every table; demo seed rows anchored to the current date",
        f"• As-Is: one monolithic data agent on all 32 tables (uncached median {N['med_mono']:,} / turn)",
    ])
    draw_card(p, 736, 640, 620, 132, YELLOW_BORDER, "icon-data-analytics", "Business Glossary & Table / Column Descriptions", [
        "• Each domain data agent carries only its own tables and glossary terms",
        "• Glossary formulas for VIP, Cart Abandonment %, Gross Margin %, Delivery Lead Time",
        "• Sub-agents bind static data agent IDs: no list / get discovery calls at runtime",
    ], fill=YELLOW_FILL)

    wrap_and_render("fig1_3tier_system_architecture", 1400, 804, p)


# ==============================================================================
# FIGURE 2: 3-Lane x 4-Column State Architecture Comparison (1440 x 804)
# ==============================================================================
def build_fig2() -> None:
    # Canvas & Strict Grid Constants
    W, H = 1440, 804

    LANE_X, LANE_W, LANE_H = 20, 1400, 244
    LANE_YS = [16, 280, 544]  # 16 + 244 = 260 (+20) -> 280 + 244 = 524 (+20) -> 544 + 244 = 788 (+16 = 804)

    # 4 Strict Column Coordinates (inner x: 40 .. 1400, total inner width = 1360):
    # Col1: 40..250 (w=210) | Gap1: 112 | Col2: 362..608 (w=246) | Gap2: 156 | Col3: 764..1010 (w=246) | Gap3: 144 | Col4: 1154..1400 (w=246)
    COL_X = [40, 362, 764, 1154]
    COL_W = [210, 246, 246, 246]
    CARD_OFFSET_Y = 62
    CARD_H = 164

    # Google Cloud Brand Palette
    BLUE = "#1A73E8"
    BLUE_DARK = "#174EA6"
    BLUE_LIGHT = "#E8F0FE"
    BLUE_TINT = "#F4F8FE"

    GREEN_DARK = "#137333"
    GREEN_BORDER = "#34A853"
    GREEN_LIGHT = "#E6F4EA"
    GREEN_TINT = "#F6FBF7"

    AMBER_DARK = "#C56200"
    YELLOW_BORDER = "#F9AB00"
    YELLOW_FILL = "#FFFDF5"

    GREY = "#5F6368"
    GREY_BORDER = "#80868B"
    GREY_LIGHT = "#E8EAED"
    GREY_TINT = "#F8F9FA"

    TEXT_MAIN = "#202124"
    TEXT_SUB = "#3C4043"
    TEXT_MUTED = "#80868B"
    DIVIDER = "#E8EAED"

    parts: list[str] = []


    def esc(s: str) -> str:
        return html.escape(s, quote=True)


    def approx_text_width(text: str, font_size: float) -> float:
        w = 0.0
        for ch in text:
            if ch in "ilI.,:;|!·' ":
                w += 0.30 * font_size
            elif ch in "mwMW@%&":
                w += 0.82 * font_size
            elif ch.isupper() or ch.isdigit():
                w += 0.62 * font_size
            else:
                w += 0.54 * font_size
        return w


    def add_lane(
        y: int,
        border_color: str,
        fill_color: str,
        title_color: str,
        title: str,
        badge_text: str,
        badge_bg: str,
        badge_fg: str,
    ):
        parts.append(
            f'  <rect x="{LANE_X}" y="{y}" width="{LANE_W}" height="{LANE_H}" rx="12" ry="12" '
            f'fill="{fill_color}" stroke="{border_color}" stroke-width="2"/>'
        )
        parts.append(
            f'  <line x1="{LANE_X + 20}" y1="{y + 46}" x2="{LANE_X + LANE_W - 20}" y2="{y + 46}" '
            f'stroke="#DADCE0" stroke-width="1"/>'
        )
        parts.append(
            f'  <text x="{LANE_X + 20}" y="{y + 30}" font-size="15.5" font-weight="700" '
            f'fill="{title_color}">{esc(title)}</text>'
        )
        bw = int(approx_text_width(badge_text, 11.5) + 28)
        bx = LANE_X + LANE_W - 20 - bw
        by = y + 11
        parts.append(
            f'  <rect x="{bx}" y="{by}" width="{bw}" height="24" rx="12" ry="12" '
            f'fill="{badge_bg}"/>'
        )
        parts.append(
            f'  <text x="{bx + bw / 2:.1f}" y="{by + 16}" text-anchor="middle" '
            f'font-size="11.5" font-weight="700" fill="{badge_fg}">{esc(badge_text)}</text>'
        )


    def add_card(
        col_idx: int,
        lane_y: int,
        border_color: str,
        icon_id: str,
        title: str,
        bullets: list[str],
        fill: str = "#FFFFFF",
    ):
        x = COL_X[col_idx]
        w = COL_W[col_idx]
        y = lane_y + CARD_OFFSET_Y
        h = CARD_H

        parts.append(
            f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" ry="10" '
            f'fill="{fill}" stroke="{border_color}" stroke-width="2" filter="url(#card-shadow)"/>'
        )
        # Icon + 1-line Header
        parts.append(
            f'  <use href="#{icon_id}" x="{x + 14}" y="{y + 11}" width="32" height="32"/>'
        )
        parts.append(
            f'  <text x="{x + 54}" y="{y + 32}" font-size="13.2" font-weight="700" '
            f'fill="{TEXT_MAIN}">{esc(title)}</text>'
        )
        # Consistent horizontal card header divider
        parts.append(
            f'  <line x1="{x + 14}" y1="{y + 52}" x2="{x + w - 14}" y2="{y + 52}" '
            f'stroke="{DIVIDER}" stroke-width="1"/>'
        )
        # Full-width aligned bullet list
        for j, bline in enumerate(bullets):
            by = y + 74 + j * 21
            parts.append(
                f'  <text x="{x + 16}" y="{by}" font-size="11.5" font-weight="400" '
                f'fill="{TEXT_SUB}">{esc(bline)}</text>'
            )


    def add_ghost_stateless_slot(col_idx: int, lane_y: int):
        """Renders the Column 3 dashed Stateless Bypass slot in Lane 2, keeping exact 4-column symmetry."""
        x = COL_X[col_idx]
        w = COL_W[col_idx]
        y = lane_y + CARD_OFFSET_Y
        h = CARD_H
        cx = x + w / 2.0

        parts.append(
            f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" ry="10" '
            f'fill="#FFFFFF" fill-opacity="0.75" stroke="#BDC1C6" stroke-width="1.6" stroke-dasharray="6 4"/>'
        )
        # Small circle-slash icon at header left to mirror standard cards
        parts.append(
            f'  <circle cx="{x + 30}" cy="{y + 27}" r="11" fill="none" stroke="#9AA0A6" stroke-width="1.8"/>'
        )
        parts.append(
            f'  <line x1="{x + 22.5}" y1="{y + 34.5}" x2="{x + 37.5}" y2="{y + 19.5}" stroke="#9AA0A6" stroke-width="1.8"/>'
        )
        parts.append(
            f'  <text x="{x + 50}" y="{y + 32}" font-size="12.8" font-weight="700" '
            f'fill="{TEXT_MUTED}">No Session / State Store</text>'
        )
        parts.append(
            f'  <line x1="{x + 14}" y1="{y + 52}" x2="{x + w - 14}" y2="{y + 52}" '
            f'stroke="#E8EAED" stroke-width="1" stroke-dasharray="4 3"/>'
        )
        parts.append(
            f'  <text x="{cx:.1f}" y="{y + 146}" text-anchor="middle" font-size="11" '
            f'font-weight="500" fill="#9AA0A6">Stateless Pass-Through (Zero DB)</text>'
        )


    def add_arrow(
        x1: int,
        y: int,
        x2: int,
        color: str,
        marker_end: str,
        label_lines: list[str],
        marker_start: str = "",
        dashed: bool = False,
        label_cx: float | None = None,
        label_on_line: bool = False,
    ):
        dash = ' stroke-dasharray="7 5"' if dashed else ""
        ms = f' marker-start="url(#{marker_start})"' if marker_start else ""
        sx = x1 + (10 if marker_start else 3)
        ex = x2 - 10
        parts.append(
            f'  <line x1="{sx}" y1="{y}" x2="{ex}" y2="{y}" stroke="{color}" '
            f'stroke-width="2.2"{dash}{ms} marker-end="url(#{marker_end})"/>'
        )
        if label_lines:
            mx = label_cx if label_cx is not None else (x1 + x2) / 2.0
            max_w = max(approx_text_width(s, 11.0) for s in label_lines)
            lw = max(76, int(max_w + 20))
            lh = 15 * len(label_lines) + 10
            ly = (y - lh / 2.0) if label_on_line else (y - lh - 9)
            parts.append(
                f'  <rect x="{mx - lw / 2:.1f}" y="{ly:.1f}" width="{lw}" height="{lh}" '
                f'rx="6" ry="6" fill="#FFFFFF" stroke="#DADCE0" stroke-width="1"/>'
            )
            for idx, ll in enumerate(label_lines):
                fw = "700" if idx == 0 else "500"
                fc = TEXT_MAIN if idx == 0 else TEXT_SUB
                parts.append(
                    f'  <text x="{mx:.1f}" y="{ly + 14.5 + idx * 15:.1f}" text-anchor="middle" '
                    f'font-size="10.8" font-weight="{fw}" fill="{fc}">{esc(ll)}</text>'
                )


    # ==============================================================================
    # LANE 1: Architecture 1 — ADK Session + Memory Object (Multi-Agent Standard)
    # ==============================================================================
    L1 = LANE_YS[0]
    CY1 = L1 + CARD_OFFSET_Y + 96

    add_lane(
        L1,
        GREEN_BORDER,
        GREEN_TINT,
        GREEN_DARK,
        "1. Architecture 1 — ADK Session Object + Memory Object (Multi-Agent Enterprise Standard)",
        "Recommended for Multi-Domain BI",
        GREEN_LIGHT,
        GREEN_DARK,
    )

    add_card(
        0, L1, BLUE, "icon-mdi-person", "Enterprise User",
        [
            "• Multi-Domain Analyst",
            "• Cross-Domain Drill-Down",
            "• Executive KPI Queries",
            "• Persistent User Profile",
        ],
    )
    add_card(
        1, L1, GREEN_BORDER, "icon-vertex-ai", "ADK Root & Sub-Agents",
        [
            "• Root & 3 Domain LlmAgents",
            "• Peer & Root transfer_to_agent",
            "• Parallel 3-Domain Fan-out",
            "• Slim 20-Row Token Diet",
        ],
    )
    add_card(
        2, L1, YELLOW_BORDER, "icon-cloud-sql", "ADK Session & Memory",
        [
            "• temp:* : Single-Turn GC",
            "• session : [-6:] (3-Turn Win)",
            "• user:* & app:* : 4-Scope State",
            "• MemoryService : Long-Term",
        ],
        fill=YELLOW_FILL,
    )
    add_card(
        3, L1, GREEN_BORDER, "icon-bigquery", "Scoped Domain BQ CAAs",
        [
            "• Sales / Profit / Supply Chain",
            "• Parallel Fan-out on Demand",
            "• IAM : dataAgentUser",
            "• Scoped Schema per Domain",
        ],
    )

    add_arrow(COL_X[0] + COL_W[0], CY1, COL_X[1], GREEN_BORDER, "arrow-green", ["User Turn"])
    add_arrow(
        COL_X[1] + COL_W[1], CY1, COL_X[2], AMBER_DARK, "arrow-amber",
        ["Read / Write", "4-Scope State"], marker_start="arrow-amber-start"
    )
    add_arrow(
        COL_X[2] + COL_W[2], CY1, COL_X[3], GREEN_BORDER, "arrow-green",
        ["DataAgentContext", "+ Curated 3-Turn Msgs"]
    )

    # ==============================================================================
    # LANE 2: Architecture 2 — Default One-Shot Stateless Mode (Pure DataAgentContext)
    # ==============================================================================
    L2 = LANE_YS[1]
    CY2 = L2 + CARD_OFFSET_Y + 96

    add_lane(
        L2,
        GREY_BORDER,
        GREY_TINT,
        TEXT_MAIN,
        "2. Architecture 2 — Default One-Shot Stateless Mode (Pure DataAgentContext / InlineContext)",
        "Best for One-Shot Widgets & Batch",
        GREY_LIGHT,
        TEXT_SUB,
    )

    add_card(
        0, L2, GREY_BORDER, "icon-mdi-widgets", "User or BI Widget",
        [
            "• Dashboard Summary Button",
            "• Daily Scheduled Batch",
            "• Isolated Single Question",
            "• Stateless API Caller",
        ],
    )
    add_card(
        1, L2, BLUE, "icon-cloud-run", "Client App / Default ADK",
        [
            "• Direct SDK / REST Caller",
            "• Built-in ask_data_agent",
            "• Zero Custom Session DB",
            "• No History Chaining",
        ],
    )
    add_ghost_stateless_slot(2, L2)
    add_card(
        3, L2, GREY_BORDER, "icon-bigquery", "BQ CAA Service (:chat)",
        [
            "• Zero Server History Log",
            "• Intra-Turn Cache Only",
            "• No Multi-Turn Context",
            "• IAM : dataAgentUser",
        ],
    )

    add_arrow(COL_X[0] + COL_W[0], CY2, COL_X[1], GREY, "arrow-grey", ["Single Prompt"])
    add_arrow(
        COL_X[1] + COL_W[1],
        CY2,
        COL_X[3],
        GREY,
        "arrow-grey",
        ["DataAgentContext (Stateless)", "1 UserMessage Only · No History"],
        dashed=True,
        label_cx=COL_X[2] + COL_W[2] / 2.0,
        label_on_line=True,
    )

    # ==============================================================================
    # LANE 3: Architecture 3 — Managed Conversation API Stateful Mode
    # ==============================================================================
    L3 = LANE_YS[2]
    CY3 = L3 + CARD_OFFSET_Y + 96

    add_lane(
        L3,
        BLUE,
        BLUE_TINT,
        BLUE_DARK,
        "3. Architecture 3 — Managed Conversation API Stateful Mode (ConversationReference)",
        "Best for Single-Domain No-DB Chatbot",
        BLUE_LIGHT,
        BLUE_DARK,
    )

    add_card(
        0, L3, BLUE, "icon-mdi-forum", "Department Analyst",
        [
            "• Single-Domain User",
            "• Interactive Follow-up Chat",
            "• Ad-hoc SQL Exploration",
            "•BQ Studio / Thin Web UI".replace("•BQ", "• BQ"),
        ],
    )
    add_card(
        1, L3, BLUE, "icon-mdi-laptop", "Thin Client / BQ Studio",
        [
            "• Zero Custom History DB",
            "• Sends conversation_id",
            "• 6-Turn / 15m Rotation",
            "• Guardrail Recommended",
        ],
    )
    add_card(
        2, L3, BLUE, "icon-bigquery", "BQ CAA Service (:chat)",
        [
            "• Bound to 1 Fixed DataAgent",
            "• Cross-Turn Cache (90% Off)",
            "• Serialized Per-Conv Write",
            "• Domain Switch Loses State",
        ],
    )
    add_card(
        3, L3, YELLOW_BORDER, "icon-cloud-storage", "Google Managed Store",
        [
            "• Auto-Injects Server History",
            "• 180d Idle Auto-Expiration",
            "• Regional CMEK (No global)",
            "• Visible in BQ Studio UI",
        ],
        fill=YELLOW_FILL,
    )

    add_arrow(COL_X[0] + COL_W[0], CY3, COL_X[1], BLUE, "arrow-blue", ["Follow-up"])
    add_arrow(
        COL_X[1] + COL_W[1], CY3, COL_X[2], BLUE, "arrow-blue",
        ["ConversationReference", "+ 1 New UserMessage"]
    )
    add_arrow(
        COL_X[2] + COL_W[2], CY3, COL_X[3], AMBER_DARK, "arrow-amber",
        ["Auto Load", "& Append"], marker_start="arrow-amber-start"
    )

    wrap_and_render("fig2_state_architectures_comparison", W, H, parts)


# ==============================================================================
# FIGURE 3: Root-to-SubAgent 3-Way Routing Mechanics (Paths A, B, C) (1400 x 780)
# ==============================================================================
def build_fig3() -> None:
    p: list[str] = []
    # Path A Lane
    draw_lane(
        p, 20, 16, 1360, 232, BLUE, BLUE_TINT, BLUE_DARK,
        "Path A — Single-Domain Delegation via Built-in ADK transfer_to_agent",
        "S1 · S2", BLUE_LIGHT, BLUE_DARK
    )
    draw_card(p, 40, 76, 230, 154, BLUE, "icon-mdi-person", "Single-Domain Query", [
        "• '30d VIP count & AOV'",
        "• Matches Customer CRM",
        "• 1 Domain Required",
    ])
    draw_card(p, 388, 76, 276, 154, BLUE, "icon-vertex-ai", "ADK Root Router", [
        "• Selects target Sub-Agent",
        "• Emits transfer_to_agent",
        "• Zero SQL generation here",
    ])
    draw_card(p, 782, 76, 266, 154, GREEN_BORDER, "icon-agents", "Customer Sub-Agent", [
        "• Hard-bound to Customer CAA",
        "• Restates filters in query",
        "• Attaches [-6:] msg window",
    ])
    draw_card(p, 1146, 76, 214, 154, GREEN_BORDER, "icon-bigquery", "Customer BQ CAA", [
        "• 4 Tables Only",
        f"• S1 Input {N['s1_pct']}",
        "• vs 32-Table Mono",
    ])
    draw_h_arrow(p, 270, 153, 388, BLUE, "arrow-blue", ["Turn 1"])
    draw_h_arrow(p, 664, 153, 782, GREEN_BORDER, "arrow-green", ["Agent Transfer", "(Same Turn)"])
    draw_h_arrow(p, 1048, 153, 1146, GREEN_BORDER, "arrow-green", [":chat API"])

    # Path B Lane
    draw_lane(
        p, 20, 268, 1360, 232, AMBER_DARK, YELLOW_FILL, AMBER_DARK,
        "Path B — Direct Peer-to-Peer Sub-Agent Handoff on Domain Switch (Skips Extra Root Router LLM Hop)",
        "S3 · Domain Switch", YELLOW_LIGHT, AMBER_DARK
    )
    draw_card(p, 40, 328, 230, 154, BLUE, "icon-mdi-forum", "Domain-Pivot Follow-up", [
        "• 'Now check DC lead time'",
        "• Active = Customer Agent",
        "• Target = Supply Chain",
    ])
    draw_card(p, 388, 328, 276, 154, GREEN_BORDER, "icon-agents", "Active Customer Agent", [
        "• Detects Supply Chain KPI",
        "• Calls Peer transfer_to_agent",
        "• Bypasses Root Router hop!",
    ])
    draw_card(p, 782, 328, 266, 154, YELLOW_BORDER, "icon-agents", "Supply Chain Sub-Agent", [
        "• Reads 3-turn ADK history",
        "• Sends standalone query",
        "• Scoped [-6:] BQCA window",
    ])
    draw_card(p, 1146, 328, 214, 154, GREEN_BORDER, "icon-bigquery", "Supply Chain CAA", [
        "• 5 Tables Scoped",
        f"• S3 Input {N['s3_pct']}",
        "• No Conv Lock-in",
    ])
    draw_h_arrow(p, 270, 405, 388, AMBER_DARK, "arrow-amber", ["Turn N+1"])
    draw_h_arrow(p, 664, 405, 782, AMBER_DARK, "arrow-amber", ["Peer Handoff", "(No Root Hop)"])
    draw_h_arrow(p, 1048, 405, 1146, GREEN_BORDER, "arrow-green", [":chat API"])

    # Path C Lane
    draw_lane(
        p, 20, 520, 1360, 244, GREEN_BORDER, GREEN_TINT, GREEN_DARK,
        "Path C — Concurrent Multi-Domain Fan-out via ThreadPoolExecutor (One BQCA Call per Domain)",
        "S3 · Three-Domain Fan-out", GREEN_LIGHT, GREEN_DARK
    )
    draw_card(p, 40, 582, 230, 162, BLUE, "icon-mdi-person", "Composite Exec Query", [
        "• 'Why did Outerwear",
        "  net profit drop?'",
        "• Spans All 3 Domains",
    ])
    draw_card(p, 388, 582, 276, 162, GREEN_BORDER, "icon-vertex-ai", "run_cross_domain_caa", [
        "• Decomposes into 3 queries",
        "• Snapshots [-6:] windows",
        "• Spawns 3 worker threads",
        "• Synthesizes 1 unified brief",
    ])
    draw_card(p, 782, 582, 266, 162, GREEN_BORDER, "icon-bigquery", "3 Scoped CAAs in Parallel", [
        "• Customer : VIP orders",
        "• Product : returns, margin",
        "• Supply : DC lead time",
        "• One :chat call per domain",
    ])
    draw_card(p, 1146, 582, 214, 162, YELLOW_BORDER, "icon-cloud-sql", "Unified Synthesis", [
        f"• {N['fan_tobe']:,} Input Tok",
        f"• vs {N['fan_asis']:,} Mono",
        f"• {N['fan_pct']} Tokens",
        f"• BQCA Calls {N['fan_calls_tobe']} vs {N['fan_calls_asis']}",
    ], fill=YELLOW_FILL)
    draw_h_arrow(p, 270, 663, 388, GREEN_BORDER, "arrow-green", ["1 Turn"])
    draw_h_arrow(p, 664, 663, 782, GREEN_BORDER, "arrow-green", ["3x Parallel", "ThreadPool"])
    draw_h_arrow(p, 1048, 663, 1146, AMBER_DARK, "arrow-amber", ["20-Row Slim", "Results"])

    wrap_and_render("fig3_routing_paths_abc", 1400, 780, p)


# ==============================================================================
# FIGURE 4: ADK 4-Scope State & Token Diet Pipeline (1400 x 560)
# ==============================================================================
def build_fig4() -> None:
    p: list[str] = []
    draw_lane(
        p, 20, 16, 1360, 248, RED_BORDER, "#FFF8F7", RED_DARK,
        "Before (As-Is) — One ADK Agent with Built-in Data Agent Tools on One Monolithic Data Agent",
        f"{N['s1_asis']:,} Input Tokens / Turn (S1), {N['t8_asis']:,} at Turn 8", RED_LIGHT, RED_DARK
    )
    draw_card(p, 44, 78, 396, 166, RED_BORDER, "icon-bigquery", "1. Schema & Glossary Bloat", [
        "• All 32 tables / 504 columns bound to 1 agent",
        "• Schema and descriptions sent on every turn",
        f"• Uncached median {N['med_mono']:,} BQCA input / turn",
        "• list / get_data_agent_info calls at runtime",
    ])
    draw_card(p, 502, 78, 396, 166, RED_BORDER, "icon-cloud-storage", "2. Unbounded ADK Prompt Growth", [
        "• Full tool results stay in the ADK history",
        "• No cap on result rows returned to the LLM",
        f"• ADK prompt {N['asis_adk_first']:,} to {N['asis_adk_last']:,} over 8 turns",
        "• Prompt keeps growing with every turn",
    ])
    draw_card(p, 960, 78, 396, 166, RED_BORDER, "icon-mdi-widgets", "3. No Cross-Session Memory", [
        "• ask_data_agent sends 1 user message per call",
        "• Context comes only from ADK history replay",
        "• New session: no profile, no earlier findings",
        "• S5: cannot recall an insight from a past session",
    ])

    draw_lane(
        p, 20, 288, 1360, 256, GREEN_BORDER, GREEN_TINT, GREEN_DARK,
        "After — Proposed 4-Layer Token Diet + ADK 4-Scope Session.state & MemoryService Architecture",
        f"Total Input: S1 {N['s1_pct']} · S4 Avg {N['s4_avg_pct']} · Turn 8 {N['t8_pct']}", GREEN_LIGHT, GREEN_DARK
    )
    draw_card(p, 40, 352, 306, 172, GREEN_BORDER, "icon-bigquery", "1. temp:* Scope (Turn GC)", [
        "• Strips THOUGHT & PROGRESS",
        "• Caps LLM table to top 20 rows",
        "• Stores raw rows in temp:* only",
        "• Auto-evicted at end of turn",
    ])
    draw_card(p, 378, 352, 306, 172, BLUE, "icon-vertex-ai", "2. session Scope ([-6:] Cap)", [
        "• Per-agent [-6:] (3-turn) window",
        f"• ADK prompt {N['tobe_adk_min']:,}–{N['tobe_adk_max']:,} over 8 turns",
        "• before_model_callback keeps",
        "  last 3 user turns in ADK",
    ])
    draw_card(p, 716, 352, 306, 172, YELLOW_BORDER, "icon-mdi-person", "3. user:* & app:* Scopes", [
        "• user:profile & preferred_kpis",
        "• user:pinned_insights anomalies",
        "• app:total_caa_queries counter",
        "• Survives + New Session clicks",
    ], fill=YELLOW_FILL)
    draw_card(p, 1054, 352, 306, 172, GREEN_BORDER, "icon-cloud-sql", "4. ADK MemoryService Bank", [
        "• after_agent_callback indexes",
        "  completed sessions automatically",
        "• load_memory recalls insights",
        "  in a new session (S5)",
    ])

    wrap_and_render("fig4_token_diet_4scope_lifecycle", 1400, 560, p)


# ==============================================================================
# FIGURE 5: Live Execution Flow (1400 x 694). Every node and edge carries an id
# (`lf-<side>-n-<node>` / `lf-<side>-e-<from>--<to>`); the portal inlines this SVG
# and lights the elements from the ADK events of a live run.
# ==============================================================================
def build_fig5() -> None:
    w, h = 1400, 724
    idle = "#BDC1C6"
    lanes: list[str] = []
    edges: list[str] = []
    nodes: list[str] = []

    def node(side: str, nid: str, x: int, y: int, bw: int, bh: int, title: str, sub: str = "", icon: str = "") -> None:
        g = [
            f'  <g id="lf-{side}-n-{nid}" class="lf-node">',
            f'    <rect class="lf-box" x="{x}" y="{y}" width="{bw}" height="{bh}" rx="9" ry="9" fill="#FFFFFF" stroke="{idle}" stroke-width="2"/>',
        ]
        tx = x + 13
        if icon:
            g.append(f'    <use href="#{icon}" x="{x + 10}" y="{y + (bh - 26) / 2:.1f}" width="26" height="26"/>')
            tx = x + 45
        cy = y + bh / 2
        if sub:
            g.append(f'    <text x="{tx}" y="{cy - 3:.1f}" font-size="12.3" font-weight="700" fill="{TEXT_MAIN}">{esc(title)}</text>')
            g.append(f'    <text x="{tx}" y="{cy + 12.5:.1f}" font-size="10" font-weight="400" fill="{TEXT_SUB}">{esc(sub)}</text>')
        else:
            g.append(f'    <text x="{tx}" y="{cy + 4.3:.1f}" font-size="11.6" font-weight="600" fill="{TEXT_MAIN}">{esc(title)}</text>')
        g.append("  </g>")
        nodes.append("\n".join(g))

    def bq_node(side: str, x: int, y: int, bw: int, bh: int) -> None:
        cy = y + bh / 2
        nodes.append("\n".join([
            f'  <g id="lf-{side}-n-bq" class="lf-node">',
            f'    <rect class="lf-box" x="{x}" y="{y}" width="{bw}" height="{bh}" rx="9" ry="9" fill="#FFFFFF" stroke="{idle}" stroke-width="2"/>',
            f'    <use href="#icon-bigquery" x="{x + 10}" y="{cy - 26:.1f}" width="24" height="24"/>',
            f'    <text x="{x + 40}" y="{cy - 9:.1f}" font-size="12.3" font-weight="700" fill="{TEXT_MAIN}">BigQuery</text>',
            f'    <text x="{x + 12}" y="{cy + 13:.1f}" font-size="10" font-weight="400" fill="{TEXT_SUB}">cymbal_enterprise_dw</text>',
            "  </g>",
        ]))

    def edge(side: str, eid: str, pts: list[tuple[int, int]], head: bool = True) -> None:
        (x1, y1), (x2, y2) = pts[-2], pts[-1]
        g = [f'  <g id="lf-{side}-e-{eid}" class="lf-edge">']
        line_pts = list(pts)
        if head:
            length = max(1.0, ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5)
            ux, uy = (x2 - x1) / length, (y2 - y1) / length
            bx, by = x2 - ux * 9, y2 - uy * 9
            line_pts[-1] = (round(x2 - ux * 7), round(y2 - uy * 7))
            tri = f"{x2},{y2} {bx - uy * 5:.1f},{by + ux * 5:.1f} {bx + uy * 5:.1f},{by - ux * 5:.1f}"
        path = " ".join(f"{px},{py}" for px, py in line_pts)
        g.append(f'    <polyline class="lf-line" points="{path}" fill="none" stroke="{idle}" stroke-width="2" stroke-linejoin="round"/>')
        if head:
            g.append(f'    <polygon class="lf-head" points="{tri}" fill="{idle}"/>')
        g.append("  </g>")
        edges.append("\n".join(g))

    # ---- To-Be lane ----
    draw_lane(
        lanes, 20, 16, 1360, 430, GREEN_BORDER, GREEN_TINT, GREEN_DARK,
        "To-Be — Root Router + Domain Sub-Agents + Domain-Scoped Data Agents",
        "Lit from the ADK events of the live run", GREEN_LIGHT, GREEN_DARK,
    )
    rows = [104, 172, 240, 308, 376]
    node("tobe", "user", 44, rows[2] - 26, 156, 52, "User Prompt", icon="icon-mdi-person")
    node("tobe", "root", 264, rows[2] - 26, 220, 52, "Root Router", "cymbal_enterprise_root_router", "icon-vertex-ai")
    node("tobe", "sub-customer", 552, rows[0] - 26, 260, 52, "Customer Sub-Agent", "customer_marketing_subagent", "icon-agents")
    node("tobe", "sub-product", 552, rows[1] - 26, 260, 52, "Product Sub-Agent", "product_profitability_subagent", "icon-agents")
    node("tobe", "sub-supply", 552, rows[2] - 26, 260, 52, "Supply Chain Sub-Agent", "supply_chain_logistics_subagent", "icon-agents")
    node("tobe", "fan", 552, rows[3] - 26, 260, 52, "Cross-Domain Fan-out Tool", "run_cross_domain_caa_analysis", "icon-mdi-widgets")
    node("tobe", "mem", 552, rows[4] - 26, 260, 52, "Memory & State Tools", "load_memory · save · inspect", "icon-cloud-sql")
    node("tobe", "ca-customer", 892, rows[0] - 26, 270, 52, "Customer Data Agent · 4 tables", "cymbal_customer_marketing_ca", "icon-data-analytics")
    node("tobe", "ca-product", 892, rows[1] - 26, 270, 52, "Product Data Agent · 3 tables", "cymbal_product_profitability_ca", "icon-data-analytics")
    node("tobe", "ca-supply", 892, rows[2] - 26, 270, 52, "Supply Data Agent · 5 tables", "cymbal_supply_chain_ca", "icon-data-analytics")
    bq_node("tobe", 1216, rows[0] - 26, 140, rows[2] - rows[0] + 52)

    edge("tobe", "user--root", [(200, rows[2]), (264, rows[2])])
    for nid, ry in (("sub-customer", rows[0]), ("sub-product", rows[1]), ("fan", rows[3]), ("mem", rows[4])):
        edge("tobe", f"root--{nid}", [(484, rows[2]), (518, rows[2]), (518, ry), (552, ry)])
    edge("tobe", "root--sub-supply", [(484, rows[2]), (552, rows[2])])
    for dom, ry in (("customer", rows[0]), ("product", rows[1]), ("supply", rows[2])):
        edge("tobe", f"fan--ca-{dom}", [(812, rows[3]), (852, rows[3]), (852, ry), (892, ry)])
        edge("tobe", f"sub-{dom}--ca-{dom}", [(812, ry), (892, ry)])
        edge("tobe", f"ca-{dom}--bq", [(1162, ry), (1216, ry)])
    edge("tobe", "peer-cp", [(682, rows[0] + 26), (682, rows[1] - 26)], head=False)
    edge("tobe", "peer-ps", [(682, rows[1] + 26), (682, rows[2] - 26)], head=False)

    # ---- As-Is lane ----
    draw_lane(
        lanes, 20, 464, 1360, 244, GREY_BORDER, GREY_TINT, TEXT_MAIN,
        "As-Is — One ADK Agent with 3 Built-in DataAgentToolset Functions on One Monolithic Data Agent",
        "Lit from the ADK events of the live run", GREY_LIGHT, TEXT_SUB,
    )
    arows = [550, 606, 662]
    node("asis", "user", 44, arows[1] - 26, 156, 52, "User Prompt", icon="icon-mdi-person")
    node("asis", "agent", 264, arows[1] - 26, 220, 52, "ADK Agent (single)", "asis_default_data_agent_tools", "icon-vertex-ai")
    node("asis", "tool-list", 552, arows[0] - 23, 260, 46, "Built-in Tool · Discovery", "list_accessible_data_agents", "icon-mdi-widgets")
    node("asis", "tool-info", 552, arows[1] - 23, 260, 46, "Built-in Tool · Metadata", "get_data_agent_info", "icon-mdi-widgets")
    node("asis", "tool-ask", 552, arows[2] - 23, 260, 46, "Built-in Tool · Stateless Chat", "ask_data_agent", "icon-mdi-widgets")
    node("asis", "ca", 892, 583, 270, 102, "Monolithic Data Agent · 32 tables", "cymbal_enterprise_monolithic_ca", "icon-data-analytics")
    bq_node("asis", 1216, 583, 140, 102)

    edge("asis", "user--agent", [(200, arows[1]), (264, arows[1])])
    edge("asis", "agent--tool-list", [(484, arows[1]), (518, arows[1]), (518, arows[0]), (552, arows[0])])
    edge("asis", "agent--tool-info", [(484, arows[1]), (552, arows[1])])
    edge("asis", "agent--tool-ask", [(484, arows[1]), (518, arows[1]), (518, arows[2]), (552, arows[2])])
    edge("asis", "tool-info--ca", [(812, arows[1]), (892, arows[1])])
    edge("asis", "tool-ask--ca", [(812, arows[2]), (892, arows[2])])
    edge("asis", "ca--bq", [(1162, 634), (1216, 634)])

    body = lanes + ['  <g id="lf-edges">'] + edges + ["  </g>"] + nodes
    wrap_and_render("fig5_live_execution_flow", w, h, body)


if __name__ == "__main__":
    build_fig1()
    build_fig2()
    build_fig3()
    build_fig4()
    build_fig5()
