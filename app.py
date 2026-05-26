import os
import base64
import sqlite3

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Streamlit Cloud Secrets → os.environ 동기화
# 로컬은 .env(python-dotenv)로 읽히므로 이미 설정됨; Cloud는 여기서 주입
try:
    for _key in ("DART_API_KEY", "ANTHROPIC_API_KEY"):
        if _key in st.secrets and not os.environ.get(_key):
            os.environ[_key] = st.secrets[_key]
except Exception:
    pass  # 로컬 실행 시 secrets.toml 없어도 정상 동작

from graph import pipeline
from rag import retrieve, answer_with_rag
from text2sql import run_text2sql
from data import DB_PATH, get_dcf_inputs
from valuation import build_default_assumptions, calculate_dcf
try:
    from valuation import calculate_dcf_scenarios as _calc_scenarios
except ImportError:
    _calc_scenarios = None
try:
    from valuation import calculate_implied_discount_rate as _calc_implied
except ImportError:
    _calc_implied = None
try:
    from valuation import calculate_sensitivity as _calc_sens
except ImportError:
    _calc_sens = None
try:
    from valuation import calculate_roic as _calc_roic
except ImportError:
    _calc_roic = None
try:
    from valuation import calculate_dcf_confidence as _calc_confidence
except ImportError:
    _calc_confidence = None
try:
    from valuation import explain_valuation_gap as _explain_gap
except ImportError:
    _explain_gap = None
try:
    from valuation import calculate_dcf_montecarlo as _calc_mc
except ImportError:
    _calc_mc = None
try:
    from valuation import calculate_relative_valuation as _calc_rv
except ImportError:
    _calc_rv = None

st.set_page_config(page_title="AI 재무 컨설팅 어시스턴트", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap');
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css');

html, body, [class*="css"], .stApp {
    font-family: 'Pretendard', 'Noto Sans KR', sans-serif;
    background-color: #ffffff !important;
    color: #1a1a1a !important;
}

[data-testid="stAppViewContainer"] {
    background-color: #ffffff !important;
}

[data-testid="stSidebar"] {
    background-color: #f2f2f2 !important;
    border-right: 1px solid #eeeeee !important;
    border-left: 3px solid #2e7d32 !important;
}

h1, h2, h3, h4, h5, h6 {
    color: #1a1a1a !important;
    font-weight: 500 !important;
    letter-spacing: -0.02em !important;
}

h2, h3, [data-testid="stSubheader"] {
    font-size: 1.25rem !important;
    font-weight: 500 !important;
}

.stMarkdown, .stText, .stWrite,
label, .stTextInput label,
.stDataFrame, .stAlert,
.stSidebar, .stSidebar * {
    color: #1a1a1a !important;
}

.stTextInput > div > div > input {
    text-align: center !important;
    border: 1px solid #e0e0e0 !important;
    border-radius: 6px !important;
    padding: 10px 14px !important;
    font-size: 15px !important;
    background-color: rgba(255,255,255,0.35) !important;
    color: #1a1a1a !important;
    transition: border-color 0.2s ease !important;
}

.stTextInput > div > div > input:focus {
    border-color: #2e7d32 !important;
    box-shadow: 0 0 0 3px rgba(46,125,50,0.15) !important;
    outline: none !important;
}
.stTextInput > div[data-focused="true"],
.stTextInput > div > div[data-focused="true"] {
    border-color: #2e7d32 !important;
    box-shadow: 0 0 0 3px rgba(46,125,50,0.15) !important;
}
[data-baseweb="input"]:focus-within {
    border-color: #2e7d32 !important;
    box-shadow: 0 0 0 3px rgba(46,125,50,0.15) !important;
}

/* 라디오 버튼 레이블 텍스트 — 선택 여부 관계없이 항상 검정 */
[data-testid="stRadio"] label,
[data-testid="stRadio"] label *,
[data-testid="stRadio"] [role="radiogroup"] label p,
[data-testid="stRadio"] [role="radiogroup"] label span,
[data-baseweb="radio"] ~ div,
[data-baseweb="radio"] + div,
[data-baseweb="radio"][aria-checked="true"] ~ div,
[data-baseweb="radio"][aria-checked="true"] + div,
[data-baseweb="radio"] [aria-checked="true"] ~ div,
[role="radio"][aria-checked="true"] ~ div,
[role="radio"][aria-checked="true"] + div,
[data-testid="stRadio"] [aria-checked="true"] ~ div p,
[data-testid="stRadio"] [aria-checked="true"] ~ div span,
[data-testid="stRadio"] [aria-checked="true"] + div p,
[data-testid="stRadio"] [aria-checked="true"] + div span {
    color: #1a1a1a !important;
}
[data-baseweb="radio"] [data-checked="true"] > div,
[data-baseweb="radio"] input:checked + div,
[data-baseweb="radio"] [aria-checked="true"] > div:first-child {
    background-color: #2e7d32 !important;
    border-color: #2e7d32 !important;
}
[data-baseweb="radio"] > div:first-child {
    border-color: #2e7d32 !important;
}
/* 선택된 라디오 레이블 배경색 제거 */
[data-testid="stRadio"] label[data-checked="true"],
[data-testid="stRadio"] label[aria-checked="true"],
[data-testid="stRadio"] [aria-checked="true"],
[data-baseweb="radio"][aria-checked="true"],
[data-baseweb="radio-group"] [aria-checked="true"] {
    background-color: transparent !important;
}
/* 라디오 선택 시 레이블 전체 배경 초록 깔리는 것 완전 제거 */
[data-testid="stRadio"] label,
[data-testid="stRadio"] label:hover,
[data-testid="stRadio"] label:focus,
[data-testid="stRadio"] label:active,
[data-testid="stRadio"] label[data-active],
[data-testid="stRadio"] div[data-testid="stMarkdownContainer"],
[data-baseweb="radio-group"] label,
[data-baseweb="radio-group"] label:hover,
[data-baseweb="radio-group"] label > div,
[data-baseweb="radio-group"] label > div:hover,
[data-baseweb="radio-group"] label[data-focus-visible-added],
[data-baseweb="radio-group"] [data-selected="true"],
[data-baseweb="radio-group"] [data-checked="true"],
[data-baseweb="radio-group"] [aria-checked="true"] {
    background-color: transparent !important;
    background: transparent !important;
}
[data-baseweb="radio"]:hover > div:first-child {
    border-color: #2e7d32 !important;
    box-shadow: 0 0 0 3px rgba(46,125,50,0.15) !important;
}

.stButton > button {
    color: rgba(0,0,0,0.55) !important;
    border: none !important;
    background-color: rgba(46,125,50,0.45) !important;
    border-radius: 6px !important;
    padding: 10px 28px !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    letter-spacing: 0.02em !important;
    transition: background-color 0.2s ease !important;
}

.stButton > button:hover {
    background-color: rgba(27,94,32,0.6) !important;
}

[data-testid="stDataFrame"] thead th,
[data-testid="stDataFrame"] th {
    background-color: #2e7d32 !important;
    color: #ffffff !important;
    font-weight: 600 !important;
    text-align: center !important;
    padding: 12px 16px !important;
    border: none !important;
    letter-spacing: 0.02em !important;
    font-family: 'Pretendard','Noto Sans KR',sans-serif !important;
}
[data-testid="stDataFrame"] tbody td,
[data-testid="stDataFrame"] td {
    text-align: center !important;
    padding: 10px 16px !important;
    border-bottom: 1px solid #f0f0f0 !important;
    color: #1a1a1a !important;
    font-family: 'Pretendard','Noto Sans KR',sans-serif !important;
    font-size: 14px !important;
}
[data-testid="stDataFrame"] tbody tr:nth-child(even) td {
    background-color: #f9fafb !important;
}
[data-testid="stDataFrame"] tbody tr:hover td {
    background-color: #e8f5e9 !important;
}

hr {
    border: none !important;
    border-top: 1px solid #eeeeee !important;
    margin: 12px 0 !important;
}

.logo-row {
    display: flex;
    align-items: center;
    gap: 8px;
}

.logo-divider {
    width: 1px;
    height: 36px;
    background-color: #dddddd;
}

.agent-status-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 5px 0;
    font-size: 13px;
}

.agent-icon {
    font-size: 15px;
    width: 18px;
    text-align: center;
}

.fade-section {
    transition: opacity 0.5s ease, filter 0.5s ease, transform 0.5s ease;
    will-change: opacity, filter, transform;
}

.kpi-card {
    background: #ffffff;
    border: 1px solid #e8e8e8;
    border-radius: 12px;
    padding: 20px 24px;
    text-align: center;
    box-shadow: 0 6px 20px rgba(0,0,0,0.12), 0 2px 6px rgba(0,0,0,0.08);
    margin-bottom: 12px;
    transition: transform 0.2s ease, box-shadow 0.2s ease;
    cursor: default;
}
.kpi-card:hover {
    transform: translateY(-4px);
    box-shadow: 0 12px 32px rgba(46,125,50,0.15), 0 4px 10px rgba(0,0,0,0.08);
}
[data-testid="stVerticalBlockBorderWrapper"] {
    border: 1px solid #e8e8e8 !important;
    border-radius: 12px !important;
    box-shadow: 0 6px 20px rgba(0,0,0,0.12), 0 2px 6px rgba(0,0,0,0.08) !important;
    background: #ffffff !important;
    transition: transform 0.2s ease, box-shadow 0.2s ease !important;
    min-height: 130px !important;
    display: flex !important;
    flex-direction: column !important;
    justify-content: flex-start !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:hover {
    transform: translateY(-4px) !important;
    box-shadow: 0 12px 32px rgba(46,125,50,0.15), 0 4px 10px rgba(0,0,0,0.08) !important;
}
.kpi-label {
    font-size: 11px;
    color: #999;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    margin-bottom: 10px;
}
.kpi-value {
    font-size: 32px;
    font-weight: 700;
    color: #1a1a1a;
    margin-bottom: 6px;
    letter-spacing: -0.03em;
}
.kpi-delta {
    font-size: 14px;
    font-weight: 500;
}
.dcf-card {
    background: #ffffff;
    border: 1px solid #e8e8e8;
    border-radius: 12px;
    padding: 36px 20px;
    text-align: center;
    margin-bottom: 12px;
    box-shadow: 0 6px 20px rgba(0,0,0,0.12), 0 2px 6px rgba(0,0,0,0.08);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
    cursor: default;
}
.dcf-card:hover {
    transform: translateY(-4px);
    box-shadow: 0 12px 32px rgba(46,125,50,0.15), 0 4px 10px rgba(0,0,0,0.08);
}

[data-testid="stTabs"] > div:first-child {
    margin-bottom: 8px;
}
.result-section {
    margin-bottom: 40px;
}
.result-section + .result-section {
    padding-top: 12px;
    border-top: 1px solid #f0f0f0;
}

[data-testid="stTabs"] button {
    font-size: 14px;
    font-weight: 400;
    color: #666666;
    border-radius: 8px 8px 0 0;
    margin-right: 16px !important;
    transition: color 0.15s ease, background 0.15s ease;
}
[data-testid="stTabs"] button:hover {
    color: #2e7d32 !important;
    background: #f1f8f1 !important;
}
[data-testid="stTabs"] button[aria-selected="true"] {
    color: #1b5e20 !important;
    font-weight: 700 !important;
    background: #f1f8f1 !important;
    border-bottom: 3px solid #2e7d32 !important;
}
[data-testid="stTabs"] button[aria-selected="true"] p,
[data-testid="stTabs"] button[aria-selected="true"] span,
[data-testid="stTabs"] button[aria-selected="true"] div {
    font-weight: 700 !important;
    color: #1b5e20 !important;
}

[data-testid="stSpinner"],
[data-testid="stSpinner"] > div,
[data-testid="stSpinner"] > div > div {
    display: flex !important;
    justify-content: center !important;
    align-items: center !important;
    width: 100% !important;
    gap: 10px !important;
}
[data-testid="stSpinner"] p {
    text-align: center !important;
    margin: 0 !important;
}
[data-testid="stTabs"] [data-baseweb="tab-highlight"] {
    background-color: transparent !important;
}
[data-testid="stTabs"] [data-baseweb="tab-border"] {
    background-color: #eeeeee !important;
    height: 1px !important;
}

[data-testid="stDownloadButton"] > button {
    background-color: #f1f8f1 !important;
    color: #2e7d32 !important;
    border: 1px solid rgba(46,125,50,0.35) !important;
    font-weight: 500 !important;
}
[data-testid="stDownloadButton"] > button:hover {
    background-color: #e8f5e9 !important;
    border-color: #2e7d32 !important;
}

@keyframes spin {
    0%   { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}

@keyframes headerFadeIn {
    from { opacity: 0; transform: translateY(-10px); }
    to   { opacity: 1; transform: translateY(0); }
}
.header-logo {
    animation: headerFadeIn 3.2s cubic-bezier(0.22, 1, 0.36, 1) 0.2s both;
}
.header-title {
    animation: headerFadeIn 3.2s cubic-bezier(0.22, 1, 0.36, 1) 1.1s both;
}

/* 슬라이더 — 초록 테마 강제 적용 (Streamlit primary-color 변수 재정의 포함) */
:root, [data-testid="stApp"] {
    --primary-color: #2e7d32 !important;
}
[data-baseweb="slider"] [role="slider"],
[data-testid="stSlider"] [role="slider"] {
    background-color: #2e7d32 !important;
    border-color: #2e7d32 !important;
    box-shadow: none !important;
    outline: none !important;
}
[data-baseweb="slider"] [role="slider"]:focus,
[data-baseweb="slider"] [role="slider"]:focus-visible {
    box-shadow: 0 0 0 4px rgba(46,125,50,0.25) !important;
    outline: none !important;
}
[data-testid="stSliderTrackActive"],
[data-testid="stSlider"] [data-testid="stSliderTrackActive"],
[data-baseweb="slider"] [data-testid="stSliderTrackActive"],
[data-baseweb="slider"] [class*="TrackActive"],
[data-baseweb="slider"] [class*="trackActive"],
[data-baseweb="slider"] div[class*="track"] > div:first-child {
    background: #2e7d32 !important;
    background-color: #2e7d32 !important;
    background-image: none !important;
}
[data-baseweb="slider"] [class*="Track"]:not([class*="Active"]):not([class*="active"]),
[data-testid="stSlider"] [class*="Track"]:not([data-testid="stSliderTrackActive"]) {
    background: #c8e6c9 !important;
    background-color: #c8e6c9 !important;
}

/* st.warning() — 둥근 모서리 + 그린 테마 통일 */
[data-testid="stAlert"]:has(svg[data-testid="stAlertDynamicIcon"]) {
    background-color: #f1f8e9 !important;
    border-color: #a5d6a7 !important;
    border-radius: 12px !important;
    border-width: 1px !important;
    border-style: solid !important;
}
div[data-testid="stAlert"] {
    background-color: #f1f8e9 !important;
    border-color: #a5d6a7 !important;
    border-radius: 12px !important;
    border-width: 1px !important;
    border-style: solid !important;
    box-shadow: 0 2px 8px rgba(46,125,50,0.08) !important;
}
div[data-testid="stAlert"] svg {
    fill: #2e7d32 !important;
    color: #2e7d32 !important;
}
div[data-testid="stAlert"] p,
div[data-testid="stAlert"] div {
    color: #1b5e20 !important;
}

@keyframes sectionFadeUp {
    from { opacity: 0; transform: translateY(14px); }
    to   { opacity: 1; transform: translateY(0); }
}
@keyframes titleSlideIn {
    from { opacity: 0; transform: translateX(-12px); }
    to   { opacity: 1; transform: translateX(0); }
}
.analysis-section {
    opacity: 0;
    animation: sectionFadeUp 0.45s ease forwards;
    padding: 24px 0 24px 16px;
    border-left: 3px solid #c8e6c9;
}
.analysis-section-title {
    font-size: 1rem;
    font-weight: 700;
    color: #2e7d32;
    letter-spacing: -0.01em;
    margin-bottom: 12px;
    opacity: 0;
    animation: titleSlideIn 0.35s ease forwards;
}
.analysis-section-body {
    font-size: 15px;
    line-height: 1.95;
    color: #333333;
    margin: 0;
    word-break: keep-all;
}
.analysis-divider {
    height: 1px;
    background: #e8e8e8;
    margin: 4px 0;
    border: none;
}
.spinner-icon {
    display: inline-block;
    width: 11px;
    height: 11px;
    border: 2px solid #f59e0b;
    border-top-color: transparent;
    border-radius: 50%;
    animation: spin 0.75s linear infinite;
    vertical-align: middle;
    margin-right: 2px;
}

/* ── Expander 모서리 둥글게 + 색상 통일 ── */
[data-testid="stExpander"] {
    border-radius: 12px !important;
    border: 1px solid #e8e8e8 !important;
    overflow: hidden !important;
    box-shadow: none !important;
}
/* 헤더(접힌 상태) — 배경 흰색, 전체 모서리 둥글게 */
[data-testid="stExpander"] > details > summary,
[data-testid="stExpander"] [data-testid="stExpanderHeader"],
[data-testid="stExpander"] [role="button"] {
    background-color: #ffffff !important;
    border-radius: 12px !important;
    border: none !important;
    color: #1a1a1a !important;
}
/* 헤더(열린 상태) — 위 모서리만 둥글게 */
[data-testid="stExpander"] > details[open] > summary,
[data-testid="stExpander"][aria-expanded="true"] [data-testid="stExpanderHeader"],
[data-testid="stExpander"][aria-expanded="true"] [role="button"] {
    border-radius: 12px 12px 0 0 !important;
    border-bottom: 1px solid #f0f0f0 !important;
}
/* 내부 콘텐츠 영역 */
[data-testid="stExpanderDetails"],
[data-testid="stExpander"] > details > div {
    background-color: #ffffff !important;
    border-radius: 0 0 12px 12px !important;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<script>
(function() {
    const BLUR_MAX = 10;
    const OPACITY_MIN = 0.1;
    const TRANSLATE_MAX = 20;

    function getRatio(el) {
        const rect = el.getBoundingClientRect();
        const viewH = window.innerHeight;
        const elCenter = rect.top + rect.height / 2;
        const distance = Math.abs(elCenter - viewH / 2);
        return Math.max(0, Math.min(1, 1 - distance / (viewH * 0.65)));
    }

    function applyAll() {
        document.querySelectorAll('.fade-section').forEach(el => {
            const r = getRatio(el);
            el.style.opacity = OPACITY_MIN + (1 - OPACITY_MIN) * r;
            el.style.filter  = `blur(${BLUR_MAX * (1 - r)}px)`;
            el.style.transform = `translateY(${TRANSLATE_MAX * (1 - r)}px)`;
        });
    }

    function init() {
        const sections = document.querySelectorAll('.fade-section');
        if (!sections.length) { setTimeout(init, 400); return; }

        applyAll();

        const root = window.parent.document.querySelector('[data-testid="stAppViewContainer"]')
                  || window.parent.document.body;
        new MutationObserver(applyAll).observe(root, { childList: true, subtree: true });

        root.addEventListener('scroll', applyAll, { passive: true });
        window.addEventListener('scroll', applyAll, { passive: true });
    }

    setTimeout(init, 900);
})();

// ── 슬라이더 thumb 색상 동적 변경 (연두 → 진초록) ──
(function() {
    function lerp(a, b, t) { return Math.round(a + (b - a) * t); }
    function thumbColor(ratio) {
        return 'rgb('+lerp(200,27,ratio)+','+lerp(230,94,ratio)+','+lerp(201,32,ratio)+')';
    }
    function updateThumbs() {
        document.querySelectorAll('[role="slider"]').forEach(function(thumb) {
            var min = parseFloat(thumb.getAttribute('aria-valuemin') || 0);
            var max = parseFloat(thumb.getAttribute('aria-valuemax') || 1);
            var val = parseFloat(thumb.getAttribute('aria-valuenow') || min);
            if (max === min) return;
            var ratio = (val - min) / (max - min);
            var c = thumbColor(ratio);
            thumb.style.setProperty('background-color', c, 'important');
            thumb.style.setProperty('border-color', c, 'important');
        });
    }
    // 초기 실행 + 200ms마다 polling (Streamlit 재렌더 대응)
    setTimeout(updateThumbs, 600);
    setInterval(updateThumbs, 200);
})();
</script>
""", unsafe_allow_html=True)

# ── 세션 상태 초기화 ──────────────────────────────────────
if "agent_status" not in st.session_state:
    st.session_state.agent_status = {"data": "대기", "analysis": "대기", "report": "대기"}
if "final_state" not in st.session_state:
    st.session_state.final_state = None
if "company" not in st.session_state:
    st.session_state.company = ""
if "qa_history" not in st.session_state:
    st.session_state.qa_history = []
if "qa_mode" not in st.session_state:
    st.session_state.qa_mode = "자동"
if "cmp_company" not in st.session_state:
    st.session_state.cmp_company = ""
if "cmp_financials" not in st.session_state:
    st.session_state.cmp_financials = {}

# ── 헬퍼 함수 ────────────────────────────────────────────
def delta_pct(curr, prev):
    if prev and prev != 0:
        return f"{(curr - prev) / prev * 100:+.1f}%"
    return None

def delta_pp(curr, prev):
    if prev is not None:
        return f"{curr - prev:+.1f}%p"
    return None

def kpi_card(label, value, delta=None):
    delta_html = ""
    if delta:
        color = "#2e7d32" if delta.startswith("+") else "#dc2626"
        arrow = "↑" if delta.startswith("+") else "↓"
        delta_html = f'<div class="kpi-delta" style="color:{color};">{arrow} {delta}</div>'
    return (
        f'<div class="kpi-card">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}</div>'
        f'{delta_html}'
        f'</div>'
    )

# ── 로고 준비 ─────────────────────────────────────────────
skku_path = os.path.join(os.path.dirname(__file__), "skku.png")
sdic_path  = os.path.join(os.path.dirname(__file__), "skku_logo.png")

def img_to_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

def img_to_base64_transparent(path, threshold=235):
    """흰색/밝은 배경 픽셀을 투명하게 처리해서 base64 반환."""
    try:
        from PIL import Image
        import io
        img = Image.open(path).convert("RGBA")
        pixels = img.getdata()
        new_pixels = []
        for r, g, b, a in pixels:
            if r >= threshold and g >= threshold and b >= threshold:
                new_pixels.append((r, g, b, 0))
            else:
                new_pixels.append((r, g, b, a))
        img.putdata(new_pixels)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return img_to_base64(path)

_skku_b64 = img_to_base64_transparent(skku_path) if os.path.exists(skku_path) else None
_sdic_b64 = img_to_base64_transparent(sdic_path) if os.path.exists(sdic_path) else None

_wallpaper_path = os.path.join(os.path.dirname(__file__), "skku_wallpaper.jpg")
_wallpaper_b64  = img_to_base64(_wallpaper_path) if os.path.exists(_wallpaper_path) else None

_logo_center_html = ""
if _skku_b64 and _sdic_b64:
    _logo_center_html = (
        f'<div class="logo-row header-logo" style="justify-content:center; margin-bottom:28px;">'
        f'<img src="data:image/png;base64,{_skku_b64}" style="height:88px; width:auto; object-fit:contain;">'
        f'<div class="logo-divider" style="height:72px;"></div>'
        f'<img src="data:image/png;base64,{_sdic_b64}" style="height:88px; width:auto; object-fit:contain;">'
        f'</div>'
    )
elif _sdic_b64:
    _logo_center_html = (
        f'<div class="header-logo" style="display:flex; justify-content:center; margin-bottom:28px;">'
        f'<img src="data:image/png;base64,{_sdic_b64}" style="height:88px; width:auto; object-fit:contain;">'
        f'</div>'
    )

_logo_right_html = ""
if _skku_b64 and _sdic_b64:
    _logo_right_html = (
        f'<div class="logo-row header-logo" style="justify-content:flex-end;">'
        f'<img src="data:image/png;base64,{_skku_b64}" style="height:88px; width:auto; object-fit:contain;">'
        f'<div class="logo-divider" style="height:72px;"></div>'
        f'<img src="data:image/png;base64,{_sdic_b64}" style="height:88px; width:auto; object-fit:contain;">'
        f'</div>'
    )
elif _sdic_b64:
    _logo_right_html = (
        f'<div class="header-logo" style="display:flex; justify-content:flex-end;">'
        f'<img src="data:image/png;base64,{_sdic_b64}" style="height:88px; width:auto; object-fit:contain;">'
        f'</div>'
    )

# ── 헤더: 시작화면 vs 결과화면 분기 ─────────────────────────
_is_startup = st.session_state.final_state is None

if _is_startup:
    # 배경 그라데이션 + 시작화면 스타일 주입
    st.markdown("""
<style>
[data-testid="stAppViewContainer"] {
    background:
        linear-gradient(170deg, rgba(240,248,230,0.94) 0%, rgba(180,215,175,0.88) 55%, rgba(120,170,120,0.82) 100%),
        url('data:image/jpeg;base64,""" + (_wallpaper_b64 or "") + """') center 65%/cover no-repeat !important;
}
/* 사이드바: 버튼과 동일한 반투명 회색 */
[data-testid="stSidebar"] {
    background-color: rgba(60,60,60,0.22) !important;
    border-right: 1px solid rgba(60,60,60,0.12) !important;
    border-left: 3px solid rgba(10,61,20,0.7) !important;
}
/* 로고 배경 제거: stMain 내 모든 중간 wrapper 투명 처리 */
[data-testid="stMain"] * {
    background-color: transparent !important;
    background: transparent !important;
}
/* 시작 화면 레이블 텍스트 검정 */
[data-testid="stMain"] p,
[data-testid="stMain"] label,
[data-testid="stMain"] .stMarkdown p {
    color: #1a1a1a !important;
}
/* 검색창: 밝은 반투명 흰색 + 초록 테두리 */
[data-testid="stMain"] [data-baseweb="input"],
[data-testid="stMain"] [data-baseweb="base-input"] {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    outline: none !important;
}
[data-testid="stMain"] .stTextInput > div > div > input {
    background: rgba(120,120,120,0.28) !important;
    border: 2px solid #2e7d32 !important;
    color: #1a1a1a !important;
}
[data-testid="stMain"] .stTextInput > div > div > input::placeholder {
    color: rgba(0,0,0,0.50) !important;
}
[data-testid="stMain"] .stTextInput > div > div > input:focus {
    border-color: #1b5e20 !important;
    box-shadow: 0 0 0 3px rgba(46,125,50,0.20) !important;
}
/* 분석 시작 버튼: 초록 배경 + 흰 텍스트 */
[data-testid="stMain"] .stButton > button {
    background-color: rgba(46,125,50,0.88) !important;
    border: 2px solid #1b5e20 !important;
    color: #ffffff !important;
}
[data-testid="stMain"] .stButton > button:hover {
    background-color: rgba(27,94,32,0.96) !important;
    border-color: #1b5e20 !important;
}

/* ── 요소 그림자 (밝은 배경용으로 완화) ── */
[data-testid="stMain"] h1 {
    text-shadow:
        0 2px 6px rgba(46,125,50,0.18),
        0 6px 18px rgba(0,0,0,0.08) !important;
}
.header-logo img {
    filter: drop-shadow(0 8px 18px rgba(0,0,0,0.14)) !important;
}
[data-testid="stMain"] .stTextInput > div > div > input {
    box-shadow: 0 4px 14px rgba(0,0,0,0.09) !important;
}
[data-testid="stMain"] .stButton > button {
    box-shadow: 0 4px 18px rgba(46,125,50,0.28) !important;
}

/* ── 순차 페이드인: (레이블+검색창 동시) → 버튼 ── */
[data-testid="stMain"] .stMarkdown p {
    animation: headerFadeIn 2.8s cubic-bezier(0.22, 1, 0.36, 1) 2.0s both;
}
[data-testid="stMain"] .stTextInput {
    animation: headerFadeIn 2.8s cubic-bezier(0.22, 1, 0.36, 1) 2.0s both;
}
[data-testid="stMain"] .stButton {
    animation: headerFadeIn 2.8s cubic-bezier(0.22, 1, 0.36, 1) 3.0s both;
}
</style>
""", unsafe_allow_html=True)
    # 로고 + 타이틀 중앙 배치
    st.markdown(f"""
<div style="display:flex; flex-direction:column; align-items:center; justify-content:center;
            min-height:44vh; padding-top:32px; text-align:center;">
    {_logo_center_html}
    <h1 class="header-title"
        style="font-size:5.04rem; font-weight:500; margin:0; color:#1b5e20;
               font-family:'Pretendard', 'Noto Sans KR', sans-serif;
               text-shadow:0 2px 6px rgba(46,125,50,0.18),0 6px 18px rgba(0,0,0,0.08);">
        AI 재무 컨설팅 어시스턴트
    </h1>
</div>
""", unsafe_allow_html=True)
else:
    # 결과 화면: 기존 좌/우 레이아웃 + 흰 배경 명시
    st.markdown("""
<style>
[data-testid="stAppViewContainer"] {
    background: #ffffff !important;
}
[data-testid="stSidebar"] {
    background-color: #f2f2f2 !important;
    border-right: 1px solid #eeeeee !important;
    border-left: 3px solid #2e7d32 !important;
}
</style>
""", unsafe_allow_html=True)
    col_title, col_logo = st.columns([5, 1])
    with col_title:
        st.markdown(
            '<h1 class="header-title" style="font-size:2.24rem; font-weight:500; margin-bottom:0;'
            'font-family:Pretendard,\'Noto Sans KR\',sans-serif;">'
            'AI 재무 컨설팅 어시스턴트</h1>',
            unsafe_allow_html=True,
        )
    with col_logo:
        st.markdown(_logo_right_html, unsafe_allow_html=True)
    st.markdown('<div class="fade-section">', unsafe_allow_html=True)
    st.markdown("---")
    st.markdown('</div>', unsafe_allow_html=True)

# ── 사이드바 ──────────────────────────────────────────────
ICON = {"대기": "○", "실행 중": "◌", "완료": "●", "오류": "✗"}
COLOR = {"대기": "#aaaaaa", "실행 중": "#f59e0b", "완료": "#2e7d32", "오류": "#dc2626"}

with st.sidebar:
    st.markdown(
        "<div style='margin:0; padding:0;'>"
        "<span style='font-size:1.5em; font-weight:700; display:block; margin-bottom:0; line-height:1.3;'>SDIC AI Team 1</span>"
        "<p style='font-size:13px; color:#555; line-height:2.0; margin-top:0; margin-bottom:20px;'>"
        "Pipeline | 이수빈<br>"
        "Data | 김나은<br>"
        "UI | 권지연<br>"
        "Report | 성한동"
        "</p></div>",
        unsafe_allow_html=True,
    )
    _dart_path   = os.path.join(os.path.dirname(__file__), "dart_logo.png")
    _claude_path = os.path.join(os.path.dirname(__file__), "claude_logo.png")
    _bok_path    = os.path.join(os.path.dirname(__file__), "bok_logo.png")
    _naver_path  = os.path.join(os.path.dirname(__file__), "naver_logo.png")
    _dart_b64   = img_to_base64_transparent(_dart_path)   if os.path.exists(_dart_path)   else None
    _claude_b64 = img_to_base64_transparent(_claude_path) if os.path.exists(_claude_path) else None
    _bok_b64    = img_to_base64_transparent(_bok_path)    if os.path.exists(_bok_path)    else None
    _naver_b64  = img_to_base64_transparent(_naver_path)  if os.path.exists(_naver_path)  else None
    _logo_html = ""
    if _dart_b64:
        _logo_html += (
            f'<div style="overflow:hidden; display:inline-flex; align-items:center;">'
            f'<img src="data:image/png;base64,{_dart_b64}" style="'
            f'height:28px; width:auto; object-fit:contain;'
            f'mix-blend-mode:multiply; border:none; outline:none; box-shadow:none;'
            f'clip-path:inset(2px);'
            f'">'
            f'</div>'
        )
    if _bok_b64:
        _logo_html += (
            f'<img src="data:image/png;base64,{_bok_b64}" style="'
            f'height:16px; width:auto; object-fit:contain;'
            f'mix-blend-mode:multiply; border:none; outline:none; box-shadow:none;">'
        )
    if _naver_b64:
        _logo_html += (
            f'<img src="data:image/png;base64,{_naver_b64}" style="'
            f'height:11px; width:auto; object-fit:contain;'
            f'mix-blend-mode:multiply; border:none; outline:none; box-shadow:none;">'
        )
    if _claude_b64:
        _logo_html += (
            f'<img src="data:image/png;base64,{_claude_b64}" style="'
            f'height:20px; width:auto; object-fit:contain;'
            f'mix-blend-mode:multiply; border:none; outline:none; box-shadow:none;'
            f'">'
        )
    st.markdown(f"""
<div style="margin:0; padding:0; line-height:1.4;">
    <div style="font-size:13px; color:#888; margin-bottom:2px;">Powered by</div>
    <div style="font-size:13px; color:#888; font-weight:700; margin-bottom:6px;">DART API · BOK ECOS · Naver · Claude AI</div>
    <div style="display:flex; gap:10px; align-items:center; margin-left:-4px; margin-bottom:14px;">
        {_logo_html}
    </div>
</div>
""", unsafe_allow_html=True)
    st.markdown("<div style='height:0.2px; background-color:#000000; margin:0 0 10px 0; border-radius:1px;'></div>", unsafe_allow_html=True)
    st.markdown("#### 에이전트 상태")
    for key, label in [("data", "Data Agent"), ("analysis", "Analysis Agent"), ("report", "Report Agent")]:
        s = st.session_state.agent_status[key]
        if s == "실행 중":
            icon_html = '<span class="spinner-icon"></span>'
        else:
            icon_html = f'<span class="agent-icon" style="color:{COLOR[s]};">{ICON[s]}</span>'
        st.markdown(
            f'<div class="agent-status-row">'
            f'{icon_html}'
            f'<span style="color:{COLOR[s]};">{label}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
    st.markdown("<div style='margin-top:20px;'></div>", unsafe_allow_html=True)
    st.markdown("#### SQLite 캐시")
    if os.path.exists(DB_PATH):
        with sqlite3.connect(DB_PATH) as _conn:
            _rows = _conn.execute(
                "SELECT company, COUNT(*) FROM financials GROUP BY company ORDER BY company"
            ).fetchall()
        if _rows:
            for _corp, _cnt in _rows:
                st.markdown(
                    f"<span style='font-size:12px; color:#2e7d32;'>● {_corp} ({_cnt}개년)</span>",
                    unsafe_allow_html=True,
                )
        else:
            st.markdown("<span style='font-size:12px; color:#aaa;'>저장된 데이터 없음</span>", unsafe_allow_html=True)
    else:
        st.markdown("<span style='font-size:12px; color:#aaa;'>DB 없음</span>", unsafe_allow_html=True)
    st.markdown("#### 데이터 소스")
    _data_source = (
        st.session_state.final_state.get("data_source", "")
        if st.session_state.final_state
        else ""
    )
    if _data_source == "cache":
        st.markdown(
            "<span style='font-size:13px; color:#1565c0;'>● cache (SQLite)</span>",
            unsafe_allow_html=True,
        )
    elif _data_source == "dart":
        st.markdown(
            "<span style='font-size:13px; color:#2e7d32;'>● dart (API)</span>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<span style='font-size:12px; color:#aaa;'>분석 전</span>",
            unsafe_allow_html=True,
        )

# ── 입력 영역 ─────────────────────────────────────────────
st.markdown('<div class="fade-section">', unsafe_allow_html=True)
_inp_l, _inp_c, _inp_r = st.columns([1, 2, 1])
with _inp_c:
    st.markdown("<p style='font-size:14px; color:#555; margin-bottom:6px; text-align:center;'>분석할 기업명을 입력하세요</p>", unsafe_allow_html=True)
    company_input = st.text_input("", placeholder="예: 에이피알", label_visibility="collapsed")
    st.markdown("<p style='font-size:12px; color:#aaa; margin-top:6px; text-align:center;'>본 프로그램은 금융감독원 DART에 공시 의무가 있는 국내 상장·비상장 기업에 대한 분석을 지원합니다.</p>", unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="fade-section">', unsafe_allow_html=True)
_b1, _b2, _b3 = st.columns([2, 1, 2])
with _b2:
    run = st.button("분석 시작", use_container_width=True)
st.markdown('</div>', unsafe_allow_html=True)

# ── 분석 실행 ─────────────────────────────────────────────
if run:
    if not company_input.strip():
        st.error("기업명을 입력해주세요")
    else:
        st.session_state.agent_status = {"data": "실행 중", "analysis": "실행 중", "report": "실행 중"}
        st.session_state.final_state = None
        if st.session_state.get("company") != company_input.strip():
            for _sk in ["dcf_g_pct", "dcf_m_pct", "dcf_w_pct",
                        "dcf_tgr_pct", "dcf_tax_pct"]:
                st.session_state.pop(_sk, None)

        with _b2:
            _spin = st.empty()
            _spin.markdown(
                '<div style="display:flex;justify-content:center;align-items:center;'
                'gap:8px;padding:10px 0;">'
                '<span style="display:inline-block;width:14px;height:14px;'
                'border:2.5px solid rgba(10,61,20,0.25);border-top-color:#0a3d14;'
                'border-radius:50%;animation:spin 0.75s linear infinite;flex-shrink:0;"></span>'
                '<span style="font-size:14px;color:#1a1a1a;font-weight:500;'
                'white-space:nowrap;">분석 중</span>'
                '</div>',
                unsafe_allow_html=True,
            )
        graph_state = pipeline.invoke({
            "request": f"{company_input} 재무 분석해줘",
            "company": company_input.strip(),
            "next_agent": "",
            "financials": {},
            "analysis": "",
            "result": "",
            "pdf_path": "",
        })

        st.session_state.final_state = graph_state
        st.session_state.company = company_input.strip()

        financials = graph_state.get("financials", {})
        analysis   = graph_state.get("analysis", "")
        pdf_path   = graph_state.get("pdf_path", "")

        st.session_state.agent_status = {
            "data":     "완료",
            "analysis": "완료" if analysis else "오류",
            "report":   "완료" if pdf_path else "대기",
        }
        st.rerun()

# ── 결과 표시 ─────────────────────────────────────────────
if "final_state" in st.session_state and st.session_state.final_state is not None:
    st.markdown('<div style="margin-top:80px;"></div>', unsafe_allow_html=True)
    graph_state  = st.session_state.final_state
    company_name = st.session_state.company
    financials   = graph_state.get("financials", {})
    analysis     = graph_state.get("analysis", "")
    pdf_path     = graph_state.get("pdf_path", "")

    if not financials:
        st.markdown('<div class="fade-section">', unsafe_allow_html=True)
        st.error(graph_state.get("result", "데이터를 찾을 수 없습니다. 기업명을 확인해주세요."))
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        # ── DataFrame 구성 ──
        rows = []
        for year, d in sorted(financials.items()):
            rev = d["매출액"]
            op  = d["영업이익"]
            net = d["순이익"]
            margin = round(op / rev * 100, 1) if rev else 0.0
            rows.append({
                "연도": year,
                "매출액 (백만원)":   rev,
                "영업이익 (백만원)": op,
                "순이익 (백만원)":   net,
                "영업이익률 (%)":  margin,
            })
        df = pd.DataFrame(rows)

        # ── KPI 값 ──
        latest = df.iloc[-1]
        prev   = df.iloc[-2] if len(df) >= 2 else None

        rev_curr = latest["매출액 (백만원)"]
        op_curr  = latest["영업이익 (백만원)"]
        net_curr = latest["순이익 (백만원)"]
        mg_curr  = latest["영업이익률 (%)"]
        latest_year = f"{int(latest['연도'])}년"

        rev_prev = prev["매출액 (백만원)"]   if prev is not None else None
        op_prev  = prev["영업이익 (백만원)"] if prev is not None else None
        net_prev = prev["순이익 (백만원)"]   if prev is not None else None
        mg_prev  = prev["영업이익률 (%)"]  if prev is not None else None

        # ── YoY 성장률 표 ──
        yoy = df[["연도"]].copy()
        for col in ["매출액 (백만원)", "영업이익 (백만원)", "순이익 (백만원)"]:
            yoy[col + " YoY"] = df[col].pct_change().apply(
                lambda x: f"{x * 100:+.1f}%" if pd.notna(x) else "—"
            )

        # ── 공통 테이블 스타일 헬퍼 ──
        _TBL_STYLES = [
            # 테이블 전체: 컨테이너 너비 100% 채우기
            {"selector": "", "props": [
                ("width", "100%"), ("border-collapse", "collapse"),
            ]},
            {"selector": "th", "props": [
                ("background-color", "#2e7d32"), ("color", "#ffffff"),
                ("font-weight", "600"), ("text-align", "center"),
                ("padding", "11px 14px"), ("border", "none"),
                ("font-family", "'Pretendard','Noto Sans KR',sans-serif"),
                ("letter-spacing", "0.02em"),
                ("white-space", "nowrap"),  # 헤더 줄바꿈 방지
            ]},
            {"selector": "td", "props": [
                ("text-align", "center"), ("padding", "9px 14px"),
                ("font-family", "'Pretendard','Noto Sans KR',sans-serif"),
                ("font-size", "14px"), ("border-bottom", "1px solid #f0f0f0"),
                ("white-space", "nowrap"),  # 셀 내용 한 줄 유지
            ]},
            {"selector": "tr:nth-child(even) td", "props": [("background-color", "#f9fafb")]},
            {"selector": "tr:hover td", "props": [("background-color", "#e8f5e9")]},
        ]
        def _tbl(df, fmt_dict=None, na_rep="-"):
            s = df.style.format(fmt_dict, na_rep=na_rep) if fmt_dict else df.style
            return s.set_table_styles(_TBL_STYLES).hide(axis="index")

        def _show_tbl(styler):
            # st.dataframe()은 Arrow 렌더러를 사용해 Pandas Styler CSS를 무시함
            # → to_html()로 직접 렌더링해야 text-align 등 스타일이 적용됨
            # width:100% 로 컨테이너(박스 포함) 너비 전체를 채우고, 넘치면 가로 스크롤
            st.markdown(
                '<div style="width:100%; overflow-x:auto;">'
                + styler.to_html()
                + '</div>',
                unsafe_allow_html=True,
            )

        # ── 스타일 DataFrame ──
        fmt = "{:,.0f}".format
        styled_df = _tbl(df, fmt_dict={
            "매출액 (백만원)":   fmt,
            "영업이익 (백만원)": fmt,
            "순이익 (백만원)":   fmt,
            "영업이익률 (%)":  "{:.1f}".format,
        })

        # ── 탭 ──
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["재무 데이터", "Claude 분석", "AI 질문", "기업 비교", "DCF 밸류에이션"])

        with tab1:
            st.markdown('<div class="fade-section">', unsafe_allow_html=True)
            st.markdown(
                f"<p style='font-size:1.875rem; font-weight:700; color:#1a1a1a; letter-spacing:-0.02em; margin-bottom:4px;'>{company_name} 연도별 재무 현황</p>"
                f"<p style='font-size:13px; color:#999; margin-bottom:16px;'>단위: 백만원</p>",
                unsafe_allow_html=True,
            )

            # KPI 카드 4장
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.markdown(kpi_card(f"매출액 ({latest_year})", f"{rev_curr:,.0f}", delta_pct(rev_curr, rev_prev)), unsafe_allow_html=True)
            with c2:
                st.markdown(kpi_card(f"영업이익 ({latest_year})", f"{op_curr:,.0f}", delta_pct(op_curr, op_prev)), unsafe_allow_html=True)
            with c3:
                st.markdown(kpi_card(f"순이익 ({latest_year})", f"{net_curr:,.0f}", delta_pct(net_curr, net_prev)), unsafe_allow_html=True)
            with c4:
                st.markdown(kpi_card(f"영업이익률 ({latest_year})", f"{mg_curr:.1f}%", delta_pp(mg_curr, mg_prev)), unsafe_allow_html=True)

            st.markdown('<div style="margin:32px 0 24px 0; height:1px; background:#eeeeee;"></div>', unsafe_allow_html=True)
            _show_tbl(styled_df)

            st.markdown('<div style="margin-top:48px;"></div>', unsafe_allow_html=True)
            # 3지표 추이 막대 차트 — 매출액 꼭짓점 점+선 항상 표시
            _years = [int(y) for y in df["연도"].tolist()]
            _bar_cols  = ["매출액 (백만원)", "영업이익 (백만원)", "순이익 (백만원)"]
            _bar_names = ["매출액", "영업이익", "순이익"]
            _bar_clrs  = ["#1b5e20", "#4caf50", "#aed581"]

            # overlay 모드: 큰 값 먼저(뒤), 작은 값 나중(앞) 순으로 그려야
            # 작은 막대가 앞에 오고 큰 막대가 차이만큼 위로 튀어나오는 효과
            _bar_w = 0.2  # 두 차트 공통 막대 두께
            _bar_cols_sorted  = ["매출액 (백만원)", "영업이익 (백만원)", "순이익 (백만원)"]
            _bar_names_sorted = ["매출액", "영업이익", "순이익"]
            _bar_clrs_sorted  = ["#1b5e20", "#4caf50", "#aed581"]

            _bar_traces = [
                go.Bar(name=nm, x=_years, y=df[col].tolist(), marker_color=clr,
                       width=_bar_w, showlegend=True)
                for col, nm, clr in zip(_bar_cols_sorted, _bar_names_sorted, _bar_clrs_sorted)
            ]
            # overlay 모드에서는 막대가 x 중심에 겹치므로 오프셋 없음
            _trend_lines = [
                go.Scatter(
                    name="매출액 추이선",
                    x=_years, y=df["매출액 (백만원)"].tolist(),
                    mode="lines+markers",
                    line=dict(color="#1b5e20", width=2.5),
                    marker=dict(size=10, color="#1b5e20", line=dict(width=2, color="white")),
                    showlegend=False,
                ),
                go.Scatter(
                    name="영업이익 추이선",
                    x=_years, y=df["영업이익 (백만원)"].tolist(),
                    mode="lines+markers",
                    line=dict(color="#4caf50", width=2.5),
                    marker=dict(size=10, color="#4caf50", line=dict(width=2, color="white")),
                    showlegend=False,
                ),
                go.Scatter(
                    name="순이익 추이선",
                    x=_years, y=df["순이익 (백만원)"].tolist(),
                    mode="lines+markers",
                    line=dict(color="#aed581", width=2.5),
                    marker=dict(size=10, color="#aed581", line=dict(width=2, color="white")),
                    showlegend=False,
                ),
            ]
            fig_trend = go.Figure(data=_bar_traces + _trend_lines)
            fig_trend.update_layout(
                title=dict(
                    text=f"{company_name} 매출액 / 영업이익 / 순이익 추이",
                    font=dict(family="Pretendard, Noto Sans KR, sans-serif", size=20, color="#1a1a1a"),
                    x=0, xanchor="left",
                ),
                barmode="overlay",
                xaxis=dict(tickmode="array", tickvals=_years, ticktext=[str(y) for y in _years]),
                yaxis=dict(title="백만원"),
                height=800,
            )
            st.plotly_chart(fig_trend, use_container_width=True)

            # 영업이익률 막대 차트 + 상단 점 연결선
            _mg_vals = df["영업이익률 (%)"].tolist()
            _mg_bar = go.Bar(
                name="영업이익률",
                x=_years, y=_mg_vals,
                marker_color="#4caf50",
                width=_bar_w,
                showlegend=True,
            )
            _mg_line = go.Scatter(
                name="영업이익률 추이선",
                x=_years, y=_mg_vals,
                mode="lines+markers",
                line=dict(color="#4caf50", width=2.5),
                marker=dict(size=10, color="#4caf50", line=dict(width=2, color="white")),
                showlegend=False,
            )
            fig_margin = go.Figure(data=[_mg_bar, _mg_line])
            fig_margin.update_layout(
                title=dict(
                    text=f"{company_name} 영업이익률 추이",
                    font=dict(family="Pretendard, Noto Sans KR, sans-serif", size=20, color="#1a1a1a"),
                    x=0, xanchor="left",
                ),
                xaxis=dict(tickmode="array", tickvals=_years, ticktext=[str(y) for y in _years]),
                yaxis=dict(title="영업이익률 (%)"),
            )
            st.plotly_chart(fig_margin, use_container_width=True)

            # 꺾은선 드로잉 애니메이션 — components.v1.html 로 스크립트 실행 보장
            import streamlit.components.v1 as _components
            _components.html("""
<script>
(function() {
    var doc = window.parent.document;

    function prepare(chart) {
        if (chart.dataset.lineAnimDone) return;
        var paths = chart.querySelectorAll('.lines .js-line');
        if (!paths.length) return;
        chart.dataset.lineAnimDone = '1';

        paths.forEach(function(p) {
            try {
                var len = p.getTotalLength();
                if (!len) return;
                p.style.transition = 'none';
                p.style.strokeDasharray = len + ' ' + len;
                p.style.strokeDashoffset = len;
            } catch(e) {}
        });
        chart.querySelectorAll('.scatter .points path').forEach(function(pt) {
            pt.style.transition = 'none';
            pt.style.opacity = '0';
        });

        // Streamlit 메인 스크롤 컨테이너 감지
        var scrollRoot = doc.querySelector('[data-testid="stAppViewContainer"]') || doc.documentElement;

        new IntersectionObserver(function(entries, obs) {
            entries.forEach(function(entry) {
                if (!entry.isIntersecting) return;
                obs.disconnect();
                var el = entry.target;
                requestAnimationFrame(function() {
                    requestAnimationFrame(function() {
                        el.querySelectorAll('.lines .js-line').forEach(function(p) {
                            try {
                                p.style.transition = 'stroke-dashoffset 1.5s cubic-bezier(0.4,0,0.2,1)';
                                p.style.strokeDashoffset = '0';
                            } catch(e) {}
                        });
                        el.querySelectorAll('.scatter .points path').forEach(function(pt, i) {
                            pt.style.transition = 'opacity 0.35s ease ' + (1.3 + i * 0.08) + 's';
                            pt.style.opacity = '1';
                        });
                    });
                });
            });
        }, { threshold: 0.15, root: null }).observe(chart);
    }

    function scan() {
        doc.querySelectorAll('.js-plotly-plot').forEach(prepare);
    }

    // 반복 스캔: Plotly 렌더 완료 대기
    var attempts = 0;
    var iv = setInterval(function() {
        scan();
        attempts++;
        if (attempts > 20) clearInterval(iv);
    }, 400);

    // DOM 변화 감지 (탭 전환·재렌더 대응)
    var t = null;
    new MutationObserver(function() {
        clearTimeout(t);
        t = setTimeout(scan, 300);
    }).observe(doc.body, { childList: true, subtree: true });
})();
</script>
""", height=0)

            st.markdown('<div style="margin-top:48px;"></div>', unsafe_allow_html=True)
            st.markdown(
                "<p style='font-family:Pretendard,\"Noto Sans KR\",sans-serif;"
                "font-size:20px; font-weight:700; color:#1a1a1a;"
                "margin:0 0 8px 0;'>YoY 성장률</p>",
                unsafe_allow_html=True,
            )
            _show_tbl(_tbl(yoy))
            st.markdown('</div>', unsafe_allow_html=True)

        with tab2:
            import re as _re
            st.markdown('<div class="fade-section">', unsafe_allow_html=True)
            st.markdown(
                f"<p style='font-size:1.875rem; font-weight:700; color:#1a1a1a;"
                f"letter-spacing:-0.02em; margin-bottom:24px;'>"
                f"{company_name} 사업 내용 분석</p>",
                unsafe_allow_html=True,
            )

            if not analysis:
                st.info("분석 결과가 없습니다.")
            else:
                def _inline_html(text):
                    t = _re.sub(r'#+\s*', '', text)
                    t = _re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', t)
                    t = _re.sub(r'\*([^*\n]+?)\*', r'<em>\1</em>', t)
                    return t.strip()

                def _split_sentences(text):
                    t = _re.sub(r'#+\s*', '', text)
                    lines = [l.strip() for l in t.split('\n') if l.strip()]
                    sentences = []
                    for line in lines:
                        if line.startswith('- ') or line.startswith('• '):
                            sentences.append(line[2:].strip())
                        else:
                            # 마침표 뒤 공백으로 문장 분리 (한글/영문 시작 확인)
                            parts = _re.split(r'(?<=\.)\s+(?=[가-힣A-Za-z])', line)
                            for part in parts:
                                if part.strip():
                                    sentences.append(part.strip())
                    # 콜론만으로 끝나는 짧은 레이블(예: "주요사업 영역:") 제거
                    return [s for s in sentences if s and not _re.match(r'^[^.!?]{1,40}:$', s)]

                _DEFAULT_TITLES = {
                    "1": "주요 사업 영역",
                    "2": "핵심 제품·서비스",
                    "3": "고객 및 시장",
                    "4": "성장 전략",
                }

                def _parse_sections(text):
                    t = _re.sub(r'(?m)^#+\s+.+\n?', '', text.strip()).strip()
                    t = _re.sub(r'\*+([^*\n]+)\*+', r'\1', t)
                    t = _re.sub(r'#+', '', t)
                    # 들여쓰기 있는 "  1. " 형식도 처리
                    raw = _re.split(r'(?m)^\s*(\d+)\.\s+', t)
                    sections = []
                    i = 1
                    while i + 1 < len(raw):
                        num     = raw[i].strip()
                        content = raw[i + 1].strip()
                        lines   = content.split('\n', 1)
                        first   = lines[0].strip()
                        rest    = lines[1].strip() if len(lines) > 1 else ''
                        if ':' in first:
                            ci   = first.index(':')
                            cand = first[:ci].strip()
                            if len(cand) <= 35:
                                title = cand
                                body  = (first[ci+1:].strip() + ('\n' + rest if rest else '')).strip()
                            else:
                                title = _DEFAULT_TITLES.get(num, f"항목 {num}")
                                body  = content
                        else:
                            if len(first) > 40:
                                title = _DEFAULT_TITLES.get(num, f"항목 {num}")
                                body  = content
                            else:
                                title, body = first, rest
                        # body가 비어있으면 title을 body로 내리고 기본 제목 사용
                        if not body.strip() and title:
                            body  = title
                            title = _DEFAULT_TITLES.get(num, f"항목 {num}")
                        # body 앞머리의 "제목:" 중복 레이블 제거
                        _body_head = body.lstrip()
                        _dup_pat = _re.compile(
                            r'^' + _re.escape(title) + r'\s*:\s*', _re.IGNORECASE
                        )
                        if _dup_pat.match(_body_head):
                            body = _dup_pat.sub('', _body_head, count=1).strip()
                        sections.append((num, title, body))
                        i += 2
                    return sections

                _sections = _parse_sections(analysis)

                _SENT_BOX = (
                    'background:#ffffff; border:1px solid #e8e8e8; border-left:3px solid #2e7d32;'
                    'border-radius:0 8px 8px 0; padding:11px 18px; margin-bottom:6px;'
                    'box-shadow:0 1px 3px rgba(0,0,0,0.04);'
                )
                _SENT_TXT = (
                    "font-family:'Pretendard','Noto Sans KR',sans-serif;"
                    'font-size:14.5px; line-height:1.75; color:#333; margin:0; word-break:keep-all;'
                )
                _SUBTITLE = (
                    "font-family:'Pretendard','Noto Sans KR',sans-serif;"
                    "font-size:20px; font-weight:700; color:#1a1a1a; margin:28px 0 10px 0;"
                )

                def _render_sections(sections):
                    _html = ''
                    for _i, (_num, _title, _body) in enumerate(sections):
                        _mt = '28px' if _i > 0 else '4px'
                        _html += (
                            f'<p style="{_SUBTITLE} margin-top:{_mt};">'
                            f'{_num}. {_title}</p>'
                        )
                        _td = f"{_i * 0.1:.2f}s"
                        _html += (
                            f'<div style="{_SENT_BOX} animation:sectionFadeUp 0.35s ease {_td} both;">'
                            f'<p style="{_SENT_TXT}">{_inline_html(_body)}</p></div>'
                        )
                    return _html

                if _sections:
                    st.markdown(_render_sections(_sections), unsafe_allow_html=True)
                else:
                    # fallback: 번호 섹션 파싱 재시도 (들여쓰기·기타 형식 포함)
                    _clean = _re.sub(r'(?m)^#+\s*', '', analysis.strip())
                    _clean = _re.sub(r'#+', '', _clean)
                    _clean = _re.sub(r'\*+([^*\n]+)\*+', r'\1', _clean)
                    _fb_raw = _re.split(r'(?m)^\s*(\d+)\.\s+', _clean)
                    if len(_fb_raw) > 2:
                        # 번호 섹션 발견 → 같은 방식으로 렌더링
                        _fb_secs = []
                        _fb_i = 1
                        while _fb_i + 1 < len(_fb_raw):
                            _fn = _fb_raw[_fb_i].strip()
                            _fc = _fb_raw[_fb_i + 1].strip()
                            _ft = _DEFAULT_TITLES.get(_fn, f"항목 {_fn}")
                            _fb_secs.append((_fn, _ft, _fc))
                            _fb_i += 2
                        st.markdown(_render_sections(_fb_secs), unsafe_allow_html=True)
                    else:
                        # 진짜 fallback: 전체 텍스트를 하나의 박스로
                        _html = (
                            f'<div style="{_SENT_BOX} animation:sectionFadeUp 0.35s ease 0s both;">'
                            f'<p style="{_SENT_TXT}">{_inline_html(_clean)}</p></div>'
                        )
                        st.markdown(_html, unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

            # ── PDF 다운로드 (Claude 분석 탭 안) ──
            if pdf_path and os.path.exists(pdf_path):
                st.markdown('<div style="margin-top:32px;"></div>', unsafe_allow_html=True)
                with open(pdf_path, "rb") as f:
                    _pdf_c1, _pdf_c2, _pdf_c3 = st.columns([2, 1, 2])
                    with _pdf_c2:
                        st.download_button(
                            label="PDF 리포트 다운로드  ↓",
                            data=f,
                            file_name=f"{company_name}_재무분석.pdf",
                            mime="application/pdf",
                            use_container_width=True,
                        )

        with tab3:
            st.markdown('<div class="fade-section">', unsafe_allow_html=True)
            st.markdown(
                f"<p style='font-size:1.875rem; font-weight:700; color:#1a1a1a;"
                f"letter-spacing:-0.02em; margin-bottom:24px;'>"
                f"{company_name} AI 질문</p>",
                unsafe_allow_html=True,
            )

            _TEXT2SQL_KEYWORDS = {"평균", "합계", "합", "총", "최대", "최소", "몇", "계산", "비교", "순위", "sum", "avg", "max", "min"}

            st.markdown(
                "<p style='font-family:Pretendard,\"Noto Sans KR\",sans-serif;"
                "font-size:20px; font-weight:700; color:#1a1a1a; margin:0 0 8px 0;'>질의 모드</p>",
                unsafe_allow_html=True,
            )
            mode = st.radio(
                "질의 모드",
                ["자동", "RAG", "Text2SQL"],
                index=["자동", "RAG", "Text2SQL"].index(st.session_state.qa_mode),
                horizontal=True,
                key="tab3_mode",
                label_visibility="collapsed",
            )
            st.session_state.qa_mode = mode

            st.markdown(
                "<p style='font-size:12px; color:#888; margin-top:4px;'>"
                "자동: 수치·계산 키워드 감지 시 Text2SQL, 나머지는 RAG</p>",
                unsafe_allow_html=True,
            )

            question = st.text_input(
                "질문을 입력하세요",
                placeholder="예: 영업이익률이 가장 높은 연도는? / 매출 평균은?",
                key="tab3_question",
                label_visibility="collapsed",
            )
            _q1, _q2, _q3 = st.columns([2, 1, 2])
            with _q2:
                ask_btn = st.button("질문하기", key="tab3_ask", use_container_width=True)

            if ask_btn and question.strip():
                q = question.strip()

                if mode == "자동":
                    used_mode = "Text2SQL" if any(kw in q for kw in _TEXT2SQL_KEYWORDS) else "RAG"
                else:
                    used_mode = mode

                with st.spinner(f"{used_mode} 처리 중..."):
                    try:
                        if used_mode == "RAG":
                            top_chunks, claude_answer = answer_with_rag(q, financials, company_name)
                            result = {"mode": "RAG", "q": q, "chunks": top_chunks, "answer": claude_answer}
                        else:
                            sql, df_result, err = run_text2sql(q, company_name)
                            result = {"mode": "Text2SQL", "q": q, "sql": sql, "df": df_result, "error": err}
                    except Exception as e:
                        result = {"mode": used_mode, "q": q, "error": str(e)}

                st.session_state.qa_history.insert(0, result)

            if st.session_state.qa_history:
                st.markdown("---")
                for _qa_idx, item in enumerate(st.session_state.qa_history):
                    st.markdown(
                        f"<div style='margin-top:24px;'>"
                        f"<div style='font-size:11px; color:#aaa; margin-bottom:6px; letter-spacing:0.04em;'>입력된 질문</div>"
                        f"<p style='font-size:1.43rem; font-weight:700; color:#1a1a1a; "
                        f"letter-spacing:-0.01em; margin:0 0 8px 0; "
                        f"padding-left:16px; border-left:4px solid #2e7d32;'>"
                        f"Q.&nbsp; {item['q']}</p>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    badge_color = "#2e7d32" if item["mode"] == "RAG" else "#1b5e20"
                    st.markdown(
                        f"<span style='font-size:11px; background:{badge_color}; color:#fff; "
                        f"padding:2px 8px; border-radius:4px;'>{item['mode']}</span>",
                        unsafe_allow_html=True,
                    )

                    if "error" in item and item["mode"] not in ("RAG", "Text2SQL"):
                        st.error(item["error"])
                    elif item["mode"] == "RAG":
                        st.markdown("**참고 발췌 (상위 3개)**")
                        for score, chunk in item["chunks"]:
                            with st.expander(f"{chunk['label']} — 유사도 {score:.3f}"):
                                st.write(chunk["text"])
                        st.markdown(
                            "<div style='font-size:11px; color:#aaa; margin-bottom:6px; letter-spacing:0.04em;'>AI 답변</div>",
                            unsafe_allow_html=True,
                        )
                        st.markdown(
                            f"<div style='"
                            f"background-color:#f1f8f1; "
                            f"border:1px solid #c8e6c9; "
                            f"border-left:4px solid #2e7d32; "
                            f"border-radius:8px; "
                            f"padding:16px 20px; "
                            f"color:#1a1a1a; "
                            f"line-height:1.8;'>"
                            f"<p style='font-size:1.43rem; font-weight:700; color:#1a1a1a; "
                            f"letter-spacing:-0.01em; margin:0 0 10px 0;'>A.</p>"
                            f"<span style='font-size:15px;'>{item['answer']}</span>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown("**생성된 SQL**")
                        st.code(item["sql"], language="sql")
                        if item.get("error"):
                            st.error(f"실행 오류: {item['error']}")
                        elif item["df"] is not None:
                            # DataFrame → 숫자/텍스트 답변 변환 (컬럼명 기반 자동 포맷)
                            _df_ans = item["df"]

                            def _fmt_val(col, val):
                                """컬럼명에 따라 값 포맷 결정.
                                DB 숫자는 백만원 금액 또는 % 비율뿐이므로
                                year/연도 → 정수, %계열 → %, 그 외 → 원"""
                                import math as _math
                                if val is None:
                                    return "데이터 없음"
                                try:
                                    _fv = float(val)
                                    if _math.isnan(_fv):
                                        return "데이터 없음"
                                    # 연도 컬럼 — 쉼표 없이 정수
                                    if col.lower() in ("year", "연도"):
                                        return str(int(_fv))
                                    # % 비율 컬럼
                                    if any(k in col for k in ["율", "률", "성장", "rate", "margin"]):
                                        return f"{_fv:.2f}%"
                                    # 그 외 모든 숫자 → 백만원 금액
                                    return f"{_fv:,.0f}원"
                                except (ValueError, TypeError):
                                    return str(val)

                            try:
                                if len(_df_ans) == 1 and len(_df_ans.columns) == 1:
                                    _col = _df_ans.columns[0]
                                    _ans_text = _fmt_val(_col, _df_ans.iloc[0, 0])
                                elif len(_df_ans) == 1:
                                    _parts = [
                                        f"{_col}: <strong>{_fmt_val(_col, _val)}</strong>"
                                        for _col, _val in zip(_df_ans.columns, _df_ans.iloc[0])
                                    ]
                                    _ans_text = "&nbsp;&nbsp;|&nbsp;&nbsp;".join(_parts)
                                else:
                                    _row_texts = []
                                    for _, _row in _df_ans.iterrows():
                                        _parts = [
                                            f"{_col}: <strong>{_fmt_val(_col, _val)}</strong>"
                                            for _col, _val in zip(_df_ans.columns, _row)
                                        ]
                                        _row_texts.append("&nbsp;&nbsp;|&nbsp;&nbsp;".join(_parts))
                                    _ans_text = "<br>".join(_row_texts)
                            except Exception as _e:
                                _ans_text = str(_df_ans.to_dict())

                            st.markdown(
                                "<div style='font-size:11px; color:#aaa; margin-bottom:6px; letter-spacing:0.04em;'>AI 답변</div>",
                                unsafe_allow_html=True,
                            )
                            st.markdown(
                                f"<div style='"
                                f"background-color:#f1f8f1; "
                                f"border:1px solid #c8e6c9; "
                                f"border-left:4px solid #2e7d32; "
                                f"border-radius:8px; "
                                f"padding:16px 20px; "
                                f"color:#1a1a1a; "
                                f"line-height:1.8;'>"
                                f"<p style='font-size:1.43rem; font-weight:700; color:#1a1a1a; "
                                f"letter-spacing:-0.01em; margin:0 0 10px 0;'>A.</p>"
                                f"<span style='font-size:15px;'>{_ans_text}</span>"
                                f"</div>",
                                unsafe_allow_html=True,
                            )

                    if _qa_idx < len(st.session_state.qa_history) - 1:
                        st.markdown(
                            "<div style='height:1px; background:#2e7d32; opacity:0.25; margin:28px 0 0 0;'></div>",
                            unsafe_allow_html=True,
                        )

            st.markdown('</div>', unsafe_allow_html=True)

        with tab4:
            st.markdown('<div class="fade-section">', unsafe_allow_html=True)
            st.markdown(
                "<p style='font-size:1.875rem; font-weight:700; color:#1a1a1a;"
                "letter-spacing:-0.02em; margin-bottom:16px;'>기업 비교</p>",
                unsafe_allow_html=True,
            )
            # ── 기업 선택 카드 레이아웃 ──
            _pad_l, _center_col, _pad_r = st.columns([1, 2, 1])
            with _center_col:
                _col_l, _col_mid, _col_r = st.columns([5, 1, 5])
                with _col_l:
                    st.markdown(
                        f'<div style="aspect-ratio:4/3; display:flex; flex-direction:column; '
                        f'justify-content:center; align-items:center; gap:16px; '
                        f'border:1px solid #e8e8e8; border-radius:12px; '
                        f'box-shadow:0 6px 20px rgba(0,0,0,0.12), 0 2px 6px rgba(0,0,0,0.08);">'
                        f'<div style="font-size:13px; color:#999; letter-spacing:0.06em; text-transform:uppercase;">비교 기준 기업</div>'
                        f'<div style="font-size:1.6rem; font-weight:700; color:#1a1a1a; letter-spacing:-0.02em;">{company_name}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                with _col_mid:
                    st.markdown(
                        '<div style="display:flex; flex-direction:column; align-items:center; margin-bottom:-56px;">'
                        '  <div style="padding-top:100px; width:100%;">'
                        '    <div style="height:2px; background:#e0e0e0;"></div>'
                        '  </div>'
                        '  <div style="width:2px; flex:1; min-height:180px; background:#e0e0e0;"></div>'
                        '</div>',
                        unsafe_allow_html=True,
                    )
                with _col_r:
                    with st.container(border=True):
                        st.markdown('<div style="height:55px;"></div>', unsafe_allow_html=True)
                        st.markdown(
                            '<div style="font-size:13px; color:#999; letter-spacing:0.06em; text-transform:uppercase; margin-bottom:12px; text-align:center;">비교 대상 기업</div>',
                            unsafe_allow_html=True,
                        )
                        _ri_l, _ri_c, _ri_r = st.columns([1, 2, 1])
                        with _ri_c:
                            cmp_input = st.text_input(
                                "",
                                placeholder="비교할 기업명을 입력해주세요",
                                key="cmp_company_input",
                                label_visibility="collapsed",
                            )
                        st.markdown('<div style="height:55px;"></div>', unsafe_allow_html=True)

                _btn_l, _btn_c, _btn_r = st.columns([2, 1, 2])
                with _btn_c:
                    st.markdown(
                        '<div style="display:flex; justify-content:center; margin-top:-44px; margin-bottom:4px;">'
                        '<div style="width:2px; height:100px; background:#e0e0e0;"></div>'
                        '</div>',
                        unsafe_allow_html=True,
                    )
                    cmp_btn = st.button("비교 조회", key="cmp_btn", use_container_width=True)

            if cmp_btn and cmp_input.strip():
                with st.spinner(f"{cmp_input} 데이터 조회 중..."):
                    from data import get_financials as _get_fin
                    cmp_fin = _get_fin(cmp_input.strip())
                if not cmp_fin:
                    st.error(f"'{cmp_input}' 데이터를 찾을 수 없습니다. 기업명을 확인해주세요.")
                else:
                    st.session_state.cmp_company = cmp_input.strip()
                    st.session_state.cmp_financials = cmp_fin

            # 비교 결과 렌더링
            if st.session_state.get("cmp_financials"):
                cmp_name = st.session_state.cmp_company
                cmp_fin  = st.session_state.cmp_financials

                # 연도 키를 문자열로 정규화 (파이프라인은 int, get_financials는 str)
                fin_norm = {str(k): v for k, v in financials.items()}
                cmp_norm = {str(k): v for k, v in cmp_fin.items()}
                common_years = sorted(set(fin_norm.keys()) & set(cmp_norm.keys()), key=lambda y: int(y))

                if not common_years:
                    st.warning("두 기업 간 공통 연도 데이터가 없습니다.")
                else:
                    st.markdown(
                        '<div style="height:1px; background:#eeeeee; margin:32px 0 40px 0;"></div>',
                        unsafe_allow_html=True,
                    )

                    # ── 지표별 카드 3개 ──
                    _fmt = "{:,.0f}".format
                    _metrics = ["매출액", "영업이익", "순이익"]
                    _mc1, _mc2, _mc3 = st.columns(3)
                    for _col, _metric in zip([_mc1, _mc2, _mc3], _metrics):
                        _rows = []
                        for _y in common_years:
                            _rows.append({
                                "연도":        _y,
                                company_name: fin_norm[_y].get(_metric, 0),
                                cmp_name:     cmp_norm[_y].get(_metric, 0),
                            })
                        _mdf = pd.DataFrame(_rows)
                        _mstyled = _tbl(_mdf, fmt_dict={company_name: _fmt, cmp_name: _fmt})
                        with _col:
                            with st.container(border=True):
                                st.markdown(
                                    f'<p style="font-family:Pretendard,\'Noto Sans KR\',sans-serif;'
                                    f'font-size:20px; font-weight:700; color:#1a1a1a;'
                                    f'margin:0 0 12px 0; text-align:center;">'
                                    f'{_metric} (백만원)</p>',
                                    unsafe_allow_html=True,
                                )
                                _show_tbl(_mstyled)

                    # ── 그룹 막대 차트 ──
                    for metric in ["매출액", "영업이익", "순이익"]:
                        fig_cmp = go.Figure([
                            go.Bar(
                                name=company_name,
                                x=common_years,
                                y=[fin_norm[y].get(metric, 0) for y in common_years],
                                marker_color="#1b5e20",
                                width=0.2,
                            ),
                            go.Bar(
                                name=cmp_name,
                                x=common_years,
                                y=[cmp_norm[y].get(metric, 0) for y in common_years],
                                marker_color="#aed581",
                                width=0.2,
                            ),
                        ])
                        fig_cmp.update_layout(
                            title=dict(
                                text=f"{metric} 비교 (백만원)",
                                font=dict(family="Pretendard, Noto Sans KR, sans-serif", size=20, color="#1a1a1a"),
                                x=0, xanchor="left",
                            ),
                            barmode="group",
                            xaxis=dict(tickmode="array", tickvals=common_years, ticktext=[str(y) for y in common_years]),
                            yaxis_title="백만원",
                            height=400,
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                        )
                        st.plotly_chart(fig_cmp, use_container_width=True)

                    # ── 막대 차트 좌→우 등장 애니메이션 ──
                    import streamlit.components.v1 as _cmp_comp
                    _cmp_comp.html("""
<script>
(function() {
    var doc = window.parent.document;

    function prepareBar(chart) {
        if (chart.dataset.barAnimDone || chart.dataset.lineAnimDone) return;
        var barsLayer = chart.querySelector('.barlayer');
        if (!barsLayer) return;
        var paths = Array.from(barsLayer.querySelectorAll('path'));
        if (!paths.length) return;

        chart.dataset.barAnimDone = '1';

        // 화면 x 좌표 기준으로 좌→우 정렬
        paths.sort(function(a, b) {
            return a.getBoundingClientRect().left - b.getBoundingClientRect().left;
        });

        // 초기 상태: 바닥에서 찌그러져 보이지 않음
        paths.forEach(function(p) {
            p.style.transition = 'none';
            p.style.transformOrigin = '50% 100%';
            p.style.transform = 'scaleY(0)';
            p.style.opacity = '0';
        });

        new IntersectionObserver(function(entries, obs) {
            entries.forEach(function(entry) {
                if (!entry.isIntersecting) return;
                obs.disconnect();
                requestAnimationFrame(function() {
                    requestAnimationFrame(function() {
                        var n = paths.length;
                        paths.forEach(function(p, i) {
                            var delay = (i / Math.max(n - 1, 1)) * 480;
                            p.style.transition =
                                'transform 0.75s cubic-bezier(0.34,1.56,0.64,1) ' + delay + 'ms,' +
                                'opacity 0.35s ease ' + delay + 'ms';
                            p.style.transform = 'scaleY(1)';
                            p.style.opacity = '1';
                        });
                    });
                });
            });
        }, { threshold: 0.2, root: null }).observe(chart);
    }

    function scan() {
        doc.querySelectorAll('.js-plotly-plot').forEach(prepareBar);
    }

    var attempts = 0;
    var iv = setInterval(function() {
        scan();
        attempts++;
        if (attempts > 25) clearInterval(iv);
    }, 400);

    var t = null;
    new MutationObserver(function() {
        clearTimeout(t);
        t = setTimeout(scan, 300);
    }).observe(doc.body, { childList: true, subtree: true });
})();
</script>
""", height=0)

            st.markdown('</div>', unsafe_allow_html=True)

        with tab5:
            st.markdown('<div class="fade-section">', unsafe_allow_html=True)
            st.markdown(
                "<p style='font-size:1.875rem; font-weight:700; color:#1a1a1a;"
                "letter-spacing:-0.02em; margin-bottom:16px;'>DCF 밸류에이션</p>",
                unsafe_allow_html=True,
            )
            company_name = st.session_state.get("company", "")
            if not company_name:
                st.info("왼쪽 사이드바에서 기업명을 입력하고 분석을 시작해주세요.")
            else:
                with st.spinner("DCF 입력 데이터 수집 중..."):
                    dcf_inputs = get_dcf_inputs(company_name)

                if not dcf_inputs:
                    st.error("DCF 데이터를 불러오지 못했습니다. 기업명을 확인해주세요.")
                else:
                    assumptions = build_default_assumptions(dcf_inputs)
                    _current_price = dcf_inputs.get("market_metrics", {}).get("current_price")

                    # ── D1: 사용 가이드 ──────────────────────────────────────────
                    with st.expander("DCF 밸류에이션이란?", expanded=False):
                        st.markdown("""
DCF(Discounted Cash Flow)는 기업이 미래에 창출할 현금을 현재 가치로 환산해 내재가치를 추정하는 방법입니다.

슬라이더 조정 방법
- 매출 성장률: DART 3개년 CAGR 기반 자동 추정. 낙관/보수 시나리오로 조정해보세요.
- 영업이익률(OPM): 최근 3~5년 평균. 값이 높을수록 주당가치 상승.
- 할인율(WACC): 투자자가 요구하는 최소 수익률. 높을수록 주당가치 하락.
- 영구성장률(TGR): 5년 이후 영구 성장률. 통상 GDP 수준 1~3%. WACC보다 반드시 낮게 설정.
- 법인세율: 기본값 실효세율 24%.

결과 해석
- 주당 DCF 가치 > 현재가 → Upside (시장이 과소평가 구간일 수 있음)
- 주당 DCF 가치 < 현재가 → Downside (현재가에 고성장 기대 반영된 상태일 수 있음)
- ROIC > WACC → 자본비용을 초과하는 수익을 창출하는 기업
- 신뢰도 등급 A~D: 데이터 완전성·예측 가능성·모델 품질 종합 채점
""")

                    # ── D2: 가정 조정 슬라이더 ──────────────────────────────────
                    st.markdown(
                        "<p style='font-family:Pretendard,\"Noto Sans KR\",sans-serif;"
                        "font-size:20px; font-weight:700; color:#1a1a1a; margin:0 0 12px 0;'>가정 조정</p>",
                        unsafe_allow_html=True,
                    )
                    _sl, _sc, _sr = st.columns([1, 6, 1])
                    with _sc:
                        _sleft, _sright = st.columns([3, 1])
                        with _sright:
                            if st.button("DART 기본값 복원", key="reset_sliders",
                                         help="DART 공시 데이터 기반 자동 추정값으로 초기화"):
                                for _sk in ["dcf_g_pct", "dcf_m_pct", "dcf_w_pct",
                                            "dcf_tgr_pct", "dcf_tax_pct"]:
                                    st.session_state.pop(_sk, None)
                                st.rerun()

                        _g_def   = min(50, max(0,  int(round(float(assumptions["revenue_growth_rate"]) * 100))))
                        _m_def   = min(50, max(0,  int(round(float(assumptions["operating_margin"])    * 100))))
                        _w_def   = min(20, max(5,  int(round(float(assumptions["discount_rate"])       * 100))))
                        _tgr_def = min(5,  max(0,  int(round(float(assumptions["terminal_growth_rate"]) * 100))))
                        _tax_def = min(35, max(10, int(round(float(assumptions["tax_rate"])            * 100))))

                        _col1, _col2 = st.columns(2)
                        with _col1:
                            g_pct = st.slider("매출 성장률", 0, 50,
                                              st.session_state.get("dcf_g_pct", _g_def),
                                              1, format="%d%%", key="dcf_g_pct",
                                              help="DART 3개년 CAGR 기반 자동 추정")
                            st.caption(f"DART 기준값: {_g_def}%  |  K뷰티·소비재 평균 5~20%")
                            g = g_pct / 100

                            m_pct = st.slider("영업이익률 (OPM)", 0, 50,
                                              st.session_state.get("dcf_m_pct", _m_def),
                                              1, format="%d%%", key="dcf_m_pct",
                                              help="최근 3~5년 평균. OPM ↑ → 주당가치 ↑")
                            st.caption(f"DART 기준값: {_m_def}%  |  영업이익률 ↑ → FCF ↑ → 주당가치 ↑")
                            margin = m_pct / 100

                            w_pct = st.slider("할인율 (WACC)", 5, 20,
                                              st.session_state.get("dcf_w_pct", _w_def),
                                              1, format="%d%%", key="dcf_w_pct",
                                              help="WACC ↑ → 주당가치 ↓")
                            st.caption(f"CAPM 기준값: {_w_def}%  |  한국 성장주 통상 8~14%")
                            wacc = w_pct / 100

                        with _col2:
                            tgr_pct = st.slider("영구성장률 (TGR)", 0, 5,
                                                st.session_state.get("dcf_tgr_pct", _tgr_def),
                                                1, format="%d%%", key="dcf_tgr_pct",
                                                help="통상 1~3%. WACC보다 낮게 설정 필수")
                            st.caption(f"DART 기준값: {_tgr_def}%  |  통상 1~3%")
                            tgr = tgr_pct / 100

                            tax_pct = st.slider("법인세율", 10, 35,
                                                st.session_state.get("dcf_tax_pct", _tax_def),
                                                1, format="%d%%", key="dcf_tax_pct",
                                                help="실효 법인세율. 한국 기준 22~25%")
                            st.caption(f"DART 기준값: {_tax_def}%  |  NOPAT = 영업이익 × (1 − 세율)")
                            tax = tax_pct / 100

                    assumptions.update({
                        "revenue_growth_rate":  g,
                        "operating_margin":     margin,
                        "discount_rate":        wacc,
                        "terminal_growth_rate": tgr,
                        "tax_rate":             tax,
                    })

                    result = calculate_dcf(dcf_inputs, assumptions)

                    if result.get("error"):
                        st.error(result["error"])
                    else:
                        val      = result["valuation"]
                        vps      = val.get("value_per_share")
                        v_status = val.get("valuation_status", "valid")
                        v_note   = val.get("valuation_note", "")

                        if vps is not None:
                            vps_display = f"{vps:,}원"
                        elif v_status == "invalid_negative_fcf":
                            vps_display = "N/A (FCF 음수)"
                        elif v_status == "invalid_negative_ev":
                            vps_display = "N/A (EV 음수)"
                        elif v_status == "invalid_negative_equity":
                            vps_display = "N/A (순부채 초과)"
                        else:
                            vps_display = "N/A"

                        # ── D3: Upside / Downside 배너 ───────────────────────────
                        st.markdown('<div style="margin-top:28px;"></div>', unsafe_allow_html=True)
                        if vps is not None and _current_price and _current_price > 0:
                            _gap       = (vps - _current_price) / _current_price
                            _gap_label = "Upside" if _gap >= 0 else "Downside"
                            _gap_color = "#1b5e20" if _gap >= 0 else "#dc2626"
                            _gap_bg    = "#e8f5e9" if _gap >= 0 else "#ffebee"
                            st.markdown(
                                    f'<div style="display:flex; align-items:center;'
                                    f'justify-content:space-between; padding:14px 20px;'
                                    f'border-radius:10px; background:{_gap_bg};'
                                    f'border:1px solid {_gap_color}44; margin-bottom:12px;">'
                                    f'<div style="font-size:14px; color:#555;">'
                                    f'현재가 <strong style="color:#1a1a1a;">{_current_price:,}원</strong>'
                                    f'&nbsp;→&nbsp;DCF 주당가치'
                                    f' <strong style="color:#1a1a1a;">{vps:,}원</strong>'
                                    f'</div>'
                                    f'<div style="font-size:20px; font-weight:700; color:{_gap_color};">'
                                    f'{_gap_label} {_gap:+.1%}'
                                    f'</div></div>',
                                    unsafe_allow_html=True,
                                )

                        # ── Gap LLM 설명 ──────────────────────────────────
                        if _explain_gap is not None and vps is not None and _current_price and _current_price > 0:
                            try:
                                _gap_cache_key = f"gap_exp_{company_name}_{vps}_{_current_price}"
                                if _gap_cache_key not in st.session_state:
                                    with st.spinner("차이 원인 분석 중..."):
                                        st.session_state[_gap_cache_key] = _explain_gap(dcf_inputs, result, assumptions)
                                _gap_explain = st.session_state.get(_gap_cache_key, "")
                                if _gap_explain:
                                    with st.expander("이러한 차이가 발생하는 이유는?", expanded=False):
                                        st.markdown(_gap_explain)
                            except Exception:
                                pass

                        # ── D3: 성장 프로파일 배지 ───────────────────────────────
                        _gp_profile = assumptions.get("growth_profile", "")
                        _gp_note    = assumptions.get("growth_assumption_note", "")
                        _GP_LABEL = {
                            "high_growth_fade_down":       "고성장 페이드다운",
                            "moderate_growth_convergence": "중성장 수렴형",
                            "low_growth_stable":           "저성장 안정형",
                            "negative_growth_recovery":    "역성장/회복형",
                            "insufficient_data":           "데이터 부족",
                        }
                        _GP_COLOR = {
                            "high_growth_fade_down":       "#2e7d32",
                            "moderate_growth_convergence": "#2e7d32",
                            "low_growth_stable":           "#4caf50",
                            "negative_growth_recovery":    "#dc2626",
                            "insufficient_data":           "#757575",
                        }
                        if _gp_profile in _GP_LABEL:
                            _gp_clr    = _GP_COLOR[_gp_profile]
                            _gp_korean = _GP_LABEL[_gp_profile]
                            st.markdown(
                                f'<div style="display:flex; align-items:center;'
                                f'gap:10px; margin-bottom:16px; flex-wrap:wrap;">'
                                f'<span style="font-size:12px; color:#888;">DART 자동 분류</span>'
                                f'<span style="background:{_gp_clr}18; color:{_gp_clr};'
                                f'border:1px solid {_gp_clr}55; border-radius:20px;'
                                f'padding:3px 14px; font-size:14px; font-weight:600;">'
                                f'{_gp_korean}</span></div>',
                                unsafe_allow_html=True,
                            )
                            if _gp_note:
                                st.caption(_gp_note)

                        # ── KPI 카드 3개 ─────────────────────────────────────────
                        def _dcf_card(label, value):
                            return (
                                f'<div class="dcf-card">'
                                f'<div style="font-size:14px; color:#999; letter-spacing:0.06em;'
                                f'text-transform:uppercase; margin-bottom:14px;">{label}</div>'
                                f'<div style="font-size:26px; font-weight:600; color:#1a1a1a;'
                                f'letter-spacing:-0.02em; white-space:nowrap;">{value}</div>'
                                f'</div>'
                            )
                        _ev_disp  = (f"{val['enterprise_value']:,.0f}억원"
                                     if val['enterprise_value'] >= 0
                                     else f"N/A (음수 EV {val['enterprise_value']:,.0f}억)")
                        _eq_disp  = (f"{val['equity_value']:,.0f}억원"
                                     if val['equity_value'] >= 0
                                     else f"N/A (순부채 초과 {val['equity_value']:,.0f}억)")
                        _dv1, _dv2, _dv3 = st.columns(3)
                        with _dv1:
                            st.markdown(_dcf_card("Enterprise Value", _ev_disp), unsafe_allow_html=True)
                        with _dv2:
                            st.markdown(_dcf_card("Equity Value", _eq_disp), unsafe_allow_html=True)
                        with _dv3:
                            st.markdown(_dcf_card("주당 가치", vps_display), unsafe_allow_html=True)

                        # ── D4: 경고 + ROIC + 신뢰도 ────────────────────────────
                        _build_warns = result.get("warnings") or []
                        def _analysis_box(msg):
                            """Claude 분석 탭 본문 박스 스타일로 메시지 표시"""
                            import html as _html_mod
                            _lines = _html_mod.escape(msg).replace('\n', '<br>')
                            st.markdown(
                                f'<div style="background:#ffffff; border:1px solid #e8e8e8;'
                                f'border-left:3px solid #2e7d32; border-radius:0 8px 8px 0;'
                                f'padding:14px 20px; margin-bottom:8px;'
                                f'box-shadow:0 1px 3px rgba(0,0,0,0.04);">'
                                f'<p style="font-family:\'Pretendard\',\'Noto Sans KR\',sans-serif;'
                                f'font-size:14px; line-height:1.8; color:#333; margin:0;'
                                f'word-break:keep-all;">{_lines}</p></div>',
                                unsafe_allow_html=True,
                            )
                        if (v_status == "invalid_negative_fcf" and v_note) or _build_warns:
                            st.markdown('<div style="margin-top:16px;"></div>', unsafe_allow_html=True)
                            if v_status == "invalid_negative_fcf" and v_note:
                                _analysis_box(v_note)
                            for _w in _build_warns:
                                _analysis_box(_w)

                        if _calc_roic is not None:
                            try:
                                _roic_res    = _calc_roic(dcf_inputs, assumptions)
                                _latest_roic = _roic_res.get("latest_roic")
                                _avg_roic    = _roic_res.get("avg_roic")
                                _roic_wacc   = _roic_res.get("wacc")
                                _spread      = _roic_res.get("spread")
                                _verdict     = _roic_res.get("verdict", "")
                                _verdict_note = _roic_res.get("verdict_note", "")
                                if _latest_roic is not None and _spread is not None:
                                    _roic_clr = "#1b5e20" if _spread > 0 else "#dc2626"
                                    _roic_bg  = "#e8f5e9" if _spread > 0 else "#ffebee"
                                    st.markdown('<div style="margin-top:20px;"></div>', unsafe_allow_html=True)
                                    st.markdown(
                                            f'<div style="padding:14px 20px; border-radius:10px;'
                                            f'background:{_roic_bg}; border:1px solid {_roic_clr}33; margin-bottom:8px;">'
                                            f'<div style="display:flex; justify-content:space-between;'
                                            f'align-items:center; margin-bottom:6px;">'
                                            f'<span style="font-size:14px; font-weight:600; color:{_roic_clr};">ROIC vs WACC</span>'
                                            f'<span style="font-size:14px; font-weight:700; color:{_roic_clr};">{_verdict}</span>'
                                            f'</div>'
                                            f'<div style="display:flex; gap:24px; font-size:14px; color:#555; flex-wrap:wrap;">'
                                            f'<span>최신 ROIC <strong style="color:#1a1a1a;">{_latest_roic:.1%}</strong></span>'
                                            f'<span>평균 ROIC <strong style="color:#1a1a1a;">{_avg_roic:.1%}</strong></span>'
                                            f'<span>WACC <strong style="color:#1a1a1a;">{_roic_wacc:.1%}</strong></span>'
                                            f'<span>Spread <strong style="color:{_roic_clr};">{_spread:+.1%}</strong></span>'
                                            f'</div>'
                                            f'<div style="font-size:12px; color:#666; margin-top:8px;">{_verdict_note}</div>'
                                            f'</div>',
                                            unsafe_allow_html=True,
                                        )
                            except Exception:
                                pass

                        if _calc_confidence is not None:
                            try:
                                _conf    = _calc_confidence(dcf_inputs, result, assumptions)
                                _score   = _conf.get("score", 0)
                                _grade   = _conf.get("grade", "D")
                                _gn      = _conf.get("grade_note", "")
                                _details = _conf.get("details", [])
                                st.markdown('<div style="margin-top:8px;"></div>', unsafe_allow_html=True)
                                with st.expander(f"DCF 신뢰도: {_grade}등급 ({_score}/100점) — {_gn}", expanded=False):
                                        for _d in _details:
                                            _ok_icon  = "✓" if _d["ok"] else "✗"
                                            _ok_color = "#2e7d32" if _d["ok"] else "#dc2626"
                                            st.markdown(
                                                f'<div style="display:flex; justify-content:space-between;'
                                                f'padding:6px 0; border-bottom:1px solid #f0f0f0; font-size:14px;">'
                                                f'<span style="color:{_ok_color}; font-weight:700; width:16px;">{_ok_icon}</span>'
                                                f'<span style="flex:1; color:#333; margin-left:8px;">{_d["item"]}</span>'
                                                f'<span style="color:#888; margin-left:12px;">{_d["earned_pts"]}/{_d["max_pts"]}pt</span>'
                                                f'</div>'
                                                f'<div style="font-size:12px; color:#666; padding:4px 0 8px 24px;">{_d["note"]}</div>',
                                                unsafe_allow_html=True,
                                            )
                            except Exception:
                                pass

                        # ── 5개년 추정 표 ─────────────────────────────────────────
                        st.markdown('<div style="margin-top:32px;"></div>', unsafe_allow_html=True)
                        st.markdown(
                            "<p style='font-family:Pretendard,\"Noto Sans KR\",sans-serif;"
                            "font-size:20px; font-weight:700; color:#1a1a1a; margin:0 0 12px 0;'>5개년 추정</p>",
                            unsafe_allow_html=True,
                        )
                        proj = result["projection"]
                        _FCF_METHOD_LABELS = {
                            "NOPAT_DA_CAPEX_CF_DIRECT": "FCF = NOPAT + D&A − 유지CAPEX (CF 직접 추출)",
                            "NOPAT_DA_CAPEX_XBRL":      "FCF = NOPAT + D&A − 유지CAPEX (XBRL fallback)",
                            "CFO_CAPEX":                "FCF = 영업현금흐름 − CAPEX (D&A 추출 불가)",
                            "LOW_CONFIDENCE_PROXY":     "⚠ FCF 신뢰도 낮음 — 참고값으로만 활용",
                        }
                        _fcf_method = result.get("fcf_method") or (proj.get(1, {}).get("fcf_method") if proj else None)
                        if _fcf_method and _fcf_method in _FCF_METHOD_LABELS:
                            _mt = _FCF_METHOD_LABELS[_fcf_method]
                            if _fcf_method == "LOW_CONFIDENCE_PROXY":
                                st.warning(_mt)
                            else:
                                st.caption(_mt)

                        _proj_rows = []
                        for yr, p in proj.items():
                            _maint = p.get("maintenance_capex") or p.get("capex")
                            _proj_rows.append({
                                "연차":           f"{yr}년차",
                                "매출(억원)":      p["revenue"],
                                "NOPAT(억원)":     p.get("nopat"),
                                "D&A(억원)":       p.get("depreciation"),
                                "유지CAPEX(억원)": _maint,
                                "성장CAPEX(억원)": p.get("growth_capex"),
                                "FCF(억원)":       p["fcf"],
                                "PV_FCF(억원)":    p["pv_fcf"],
                            })
                        _proj_df = pd.DataFrame(_proj_rows)
                        _fmt_cols = {c: "{:,.0f}" for c in _proj_df.columns if c != "연차"}
                        _proj_styled = _tbl(_proj_df, fmt_dict=_fmt_cols, na_rep="-")
                        _show_tbl(_proj_styled)

                        # ── D5: 민감도 히트맵 ─────────────────────────────────────
                        if _calc_sens is not None:
                            try:
                                st.markdown('<div style="margin-top:40px;"></div>', unsafe_allow_html=True)
                                st.markdown(
                                    "<p style='font-family:Pretendard,\"Noto Sans KR\",sans-serif;"
                                    "font-size:20px; font-weight:700; color:#1a1a1a; margin:0 0 12px 0;'>민감도 분석 (성장률 × 할인율)</p>",
                                    unsafe_allow_html=True,
                                )
                                with st.spinner("민감도 계산 중..."):
                                    _sens = _calc_sens(dcf_inputs, assumptions)
                                _s_grs = _sens["growth_rates"]
                                _s_drs = _sens["discount_rates"]
                                _s_mat = _sens["matrix"]
                                _s_z, _s_text = [], []
                                for _s_dr in _s_drs:
                                    _s_zr, _s_tr = [], []
                                    for _s_gr in _s_grs:
                                        _sv = _s_mat.get(_s_dr, {}).get(_s_gr)
                                        if _sv is not None and _current_price and _current_price > 0:
                                            _s_zr.append((_sv - _current_price) / _current_price)
                                        else:
                                            _s_zr.append(0.0)
                                        _s_tr.append(f"{int(_sv):,}" if _sv is not None else "N/A")
                                    _s_z.append(_s_zr)
                                    _s_text.append(_s_tr)
                                _fig_sens = go.Figure(go.Heatmap(
                                    z=_s_z,
                                    x=[f"{int(_s_gr * 100)}%" for _s_gr in _s_grs],
                                    y=[f"{_s_dr:.1%}" for _s_dr in _s_drs],
                                    text=_s_text,
                                    texttemplate="%{text}",
                                    textfont={"size": 11, "color": "#1a1a1a"},
                                    colorscale=[[0.0,"#dc2626"],[0.35,"#fca5a5"],[0.5,"#f9fafb"],[0.65,"#a5d6a7"],[1.0,"#1b5e20"]],
                                    zmid=0.0, zmin=-0.5, zmax=0.5, showscale=False,
                                ))
                                _base_g = assumptions.get("revenue_growth_rate", 0)
                                _base_w = assumptions.get("discount_rate", 0.09)
                                _s_gi = min(range(len(_s_grs)), key=lambda i: abs(_s_grs[i] - _base_g))
                                _s_wi = min(range(len(_s_drs)), key=lambda i: abs(_s_drs[i] - _base_w))
                                _fig_sens.add_shape(type="rect",
                                    x0=_s_gi-0.5, x1=_s_gi+0.5, y0=_s_wi-0.5, y1=_s_wi+0.5,
                                    line=dict(color="#1a1a1a", width=3))
                                _fig_sens.update_layout(
                                    height=260, margin=dict(l=60, r=20, t=12, b=52),
                                    xaxis=dict(title="매출 성장률 (1년차)", side="bottom", tickfont=dict(size=11)),
                                    yaxis=dict(title="WACC", tickfont=dict(size=11), autorange="reversed"),
                                    paper_bgcolor="white", plot_bgcolor="white",
                                )
                                st.plotly_chart(_fig_sens, use_container_width=True)
                                _cp_txt = f"현재가 기준 ({_current_price:,}원)" if _current_price else ""
                                st.caption(f"■ 테두리: 현재 Base 가정 위치  |  {_cp_txt}: 초록=Upside / 빨강=Downside")
                            except Exception as _se:
                                st.caption(f"민감도 분석 로드 실패: {_se}")

                        # ── D6: Bear / Base / Bull 시나리오 ───────────────────────
                        if _calc_scenarios is not None:
                            try:
                                _asm_scen = build_default_assumptions(dcf_inputs)
                                _scen_res = _calc_scenarios(dcf_inputs, _asm_scen)
                                _scenarios = _scen_res.get("scenarios", {})
                                _gp        = _scen_res.get("growth_profile", {})
                                st.markdown('<div style="margin-top:40px;"></div>', unsafe_allow_html=True)
                                st.markdown(
                                    "<p style='font-family:Pretendard,\"Noto Sans KR\",sans-serif;"
                                    "font-size:20px; font-weight:700; color:#1a1a1a; margin:0 0 12px 0;'>시나리오 분석 (Bear / Base / Bull)</p>",
                                    unsafe_allow_html=True,
                                )
                                if _gp.get("effective_cagr") is not None:
                                    st.caption(f"기준 CAGR: {_gp['effective_cagr']:.1%}  |  프로파일: {_gp.get('profile', '')}  |  {_gp.get('note', '')}")
                                st.caption("※ 시나리오는 DART 공시 기반 자동 추정값 기준이며, 위 슬라이더 설정과 독립적으로 계산됩니다.")

                                _SC_CLR = {"bear":"#4caf50","base":"#2e7d32","bull":"#1b5e20"}
                                _SC_BG  = {"bear":"#f1f8f1","base":"#e8f5e9","bull":"#c8e6c9"}
                                _SC_LBL = {"bear":"Bear","base":"Base","bull":"Bull"}
                                _sc1, _sc2, _sc3 = st.columns(3)
                                for _card_col, _skey in zip([_sc1, _sc2, _sc3], ["bear","base","bull"]):
                                    _s    = _scenarios.get(_skey, {})
                                    _svps = _s.get("value_per_share")
                                    _ss   = _s.get("valuation_status", "valid")
                                    _sgap = _s.get("valuation_gap")
                                    _sclr = _SC_CLR[_skey]
                                    _sbg  = _SC_BG[_skey]
                                    _sgrl = _s.get("growth_rates") or []
                                    _sg1  = f"{_sgrl[0]:.1%}" if _sgrl else "-"
                                    if _svps is not None:
                                        _svt = f"{_svps:,}원"
                                    elif _ss == "invalid_negative_fcf":
                                        _svt = "N/A (FCF 음수)"
                                    elif _ss == "invalid_negative_ev":
                                        _svt = "N/A (EV 음수)"
                                    elif _ss == "invalid_negative_equity":
                                        _svt = "N/A (순부채 초과)"
                                    else:
                                        _svt = "N/A"
                                    _gap_html = ""
                                    if _sgap is not None:
                                        _gc2 = "#2e7d32" if _sgap >= 0 else "#dc2626"
                                        _gap_html = f'<div style="font-size:14px; color:{_gc2}; margin-top:8px;">{"↑" if _sgap>=0 else "↓"} vs 현재가 {_sgap:+.1%}</div>'
                                    with _card_col:
                                        st.markdown(
                                            f'<div style="background:{_sbg}; border:2px solid {_sclr};'
                                            f'border-radius:12px; padding:24px 16px; text-align:center; margin-bottom:12px;">'
                                            f'<div style="font-size:14px; color:{_sclr}; font-weight:700;'
                                            f'letter-spacing:0.06em; text-transform:uppercase; margin-bottom:12px;">{_SC_LBL[_skey]}</div>'
                                            f'<div style="font-size:26px; font-weight:700; color:#1a1a1a;">{_svt}</div>'
                                            f'<div style="font-size:12px; color:#666; margin-top:8px;">'
                                            f'성장률 1년차 {_sg1}  |  WACC {_s.get("discount_rate",0):.1%}</div>'
                                            f'<div style="font-size:12px; color:#666;">'
                                            f'OPM {_s.get("operating_margin",0):.1%}  |  TGR {_s.get("terminal_growth_rate",0):.1%}</div>'
                                            f'{_gap_html}</div>',
                                            unsafe_allow_html=True,
                                        )

                                # 범위 바
                                _vps_vals = {k: _scenarios[k]["value_per_share"] for k in ("bear","base","bull") if _scenarios.get(k,{}).get("value_per_share") is not None}
                                _s_cur_p  = _scenarios.get("base",{}).get("current_price") or _current_price
                                if len(_vps_vals) >= 2:
                                    _rmin = min(_vps_vals.values()) * 0.85
                                    _rmax = max(_vps_vals.values()) * 1.15
                                    _fig_rng = go.Figure()
                                    # 배경 범위 사각형 — 하단에 좁게 배치 (마커/텍스트와 겹치지 않도록)
                                    if "bear" in _vps_vals and "bull" in _vps_vals:
                                        _fig_rng.add_shape(type="rect", x0=_vps_vals["bear"], x1=_vps_vals["bull"], y0=0.05, y1=0.28, fillcolor="rgba(46,125,50,0.12)", line=dict(width=0))
                                    # Bear / Base / Bull 수직선 + 마커 — 마커를 박스 위(y=0.65)에 두고 텍스트는 위로
                                    for _rk, (_rclr, _rlbl) in {"bear":("#4caf50","Bear"),"base":("#2e7d32","Base"),"bull":("#1b5e20","Bull")}.items():
                                        if _rk in _vps_vals:
                                            _fig_rng.add_shape(type="line", x0=_vps_vals[_rk], x1=_vps_vals[_rk], y0=0.05, y1=0.67, line=dict(color=_rclr, width=2.5))
                                            _fig_rng.add_trace(go.Scatter(x=[_vps_vals[_rk]], y=[0.68], mode="markers+text",
                                                marker=dict(size=14, color=_rclr),
                                                text=[f"{_rlbl}<br>{_vps_vals[_rk]:,}원"],
                                                textposition="top center", textfont=dict(size=11, color=_rclr), showlegend=False))
                                    # 현재가 — 마커를 박스 위(y=0.65)에 두고 텍스트는 위로
                                    if _s_cur_p and _s_cur_p > 0:
                                        _fig_rng.add_shape(type="line", x0=_s_cur_p, x1=_s_cur_p, y0=0.05, y1=0.67, line=dict(color="#f59e0b", width=2, dash="dash"))
                                        _fig_rng.add_trace(go.Scatter(x=[_s_cur_p], y=[0.68], mode="markers+text",
                                            marker=dict(size=10, color="#f59e0b", symbol="diamond"),
                                            text=[f"현재가<br>{_s_cur_p:,}원"],
                                            textposition="top center", textfont=dict(size=11, color="#b45309"), showlegend=False))
                                    _fig_rng.update_layout(height=300, margin=dict(l=30,r=80,t=90,b=45),
                                        xaxis=dict(range=[_rmin,_rmax], tickformat=",", ticksuffix="원", title="주당 가치 (원)"),
                                        yaxis=dict(visible=False, range=[0,1.35]), paper_bgcolor="white", plot_bgcolor="white")
                                    st.plotly_chart(_fig_rng, use_container_width=True)

                                # 시나리오 상세 표
                                _scen_rows = []
                                for _skey in ("bear","base","bull"):
                                    _s    = _scenarios.get(_skey, {})
                                    _svps = _s.get("value_per_share")
                                    _ss   = _s.get("valuation_status", "valid")
                                    _sgap = _s.get("valuation_gap")
                                    _sgrl = _s.get("growth_rates") or []
                                    _grepr = "  /  ".join(f"{r:.0%}" for r in _sgrl) if _sgrl else "-"
                                    if _svps is not None:
                                        _svc = f"{_svps:,}원"
                                    elif _ss == "invalid_negative_fcf":
                                        _svc = "N/A [FCF 음수]"
                                    elif _ss == "invalid_negative_ev":
                                        _svc = "N/A [EV 음수]"
                                    elif _ss == "invalid_negative_equity":
                                        _svc = "N/A [순부채 초과]"
                                    else:
                                        _svc = "N/A"
                                    _scen_rows.append({
                                        "시나리오":      _SC_LBL[_skey],
                                        "성장률(1→5년)": _grepr,
                                        "WACC":          f"{_s.get('discount_rate',0):.1%}",
                                        "OPM":           f"{_s.get('operating_margin',0):.1%}",
                                        "TGR":           f"{_s.get('terminal_growth_rate',0):.1%}",
                                        "주당가치":      _svc,
                                        "vs 현재가":     f"{_sgap:+.1%}" if _sgap is not None else "-",
                                    })
                                if _scen_rows:
                                    _show_tbl(_tbl(pd.DataFrame(_scen_rows)))

                            except Exception as _e:
                                st.caption(f"시나리오 분석 로드 실패: {_e}")

                        # ── Monte Carlo ───────────────────────────────────
                        if _calc_mc is not None and vps is not None:
                            try:
                                _mc_key = f"mc_{company_name}_{assumptions.get('revenue_growth_rate',0):.3f}_{assumptions.get('discount_rate',0):.3f}"
                                if _mc_key not in st.session_state:
                                    with st.spinner("Monte Carlo 1,000회 시뮬레이션 중..."):
                                        st.session_state[_mc_key] = _calc_mc(dcf_inputs, assumptions, n_simulations=1000)
                                _mc = st.session_state[_mc_key]
                                if _mc and "error" not in _mc:
                                    st.markdown('<div style="margin-top:40px;"></div>', unsafe_allow_html=True)
                                    st.markdown("<p style='font-family:Pretendard,\"Noto Sans KR\",sans-serif;font-size:20px;font-weight:700;color:#1a1a1a;margin:0 0 12px 0;'>Monte Carlo 시뮬레이션</p>", unsafe_allow_html=True)
                                    st.caption(f"성장률 ±5pp / OPM ±3pp / WACC ±1.5pp 정규분포 샘플링 — 유효 시뮬레이션 {_mc['valid_count']:,}회")
                                    _mc1, _mc2, _mc3, _mc4, _mc5 = st.columns(5)
                                    for _col, _lbl, _key in zip(
                                        [_mc1,_mc2,_mc3,_mc4,_mc5],
                                        ["P10","P25","P50","P75","P90"],
                                        ["p10","p25","p50","p75","p90"]
                                    ):
                                        with _col:
                                            st.metric(_lbl, f"{_mc[_key]:,}원")
                                    if _mc.get("upside_probability") is not None:
                                        _up = _mc["upside_probability"]
                                        _up_clr = "#1b5e20" if _up >= 0.5 else "#dc2626"
                                        st.markdown(f'<div style="margin-top:8px;font-size:14px;">현재가({_mc["current_price"]:,}원) 대비 Upside 확률: <strong style="color:{_up_clr};">{_up:.1%}</strong></div>', unsafe_allow_html=True)
                                    _fig_mc = go.Figure(go.Bar(
                                        x=_mc["histogram"]["bins"],
                                        y=_mc["histogram"]["counts"],
                                        marker_color=["#2e7d32" if b > (_mc["current_price"] or 0) else "#dc2626" for b in _mc["histogram"]["bins"]],
                                    ))
                                    if _mc.get("current_price"):
                                        _fig_mc.add_vline(x=_mc["current_price"], line_color="#f59e0b", line_width=2, line_dash="dash", annotation_text="현재가", annotation_position="top right")
                                    _fig_mc.update_layout(height=220, margin=dict(l=20,r=20,t=10,b=40), xaxis=dict(title="주당가치 (원)", tickformat=","), yaxis=dict(title="빈도"), paper_bgcolor="white", plot_bgcolor="white", bargap=0.05)
                                    st.plotly_chart(_fig_mc, use_container_width=True)
                            except Exception as _mce:
                                st.caption(f"Monte Carlo 로드 실패: {_mce}")

                        # ── D7: Reverse DCF ───────────────────────────────────────
                        if _calc_implied is not None and _current_price and _current_price > 0:
                            try:
                                _asm_rev = build_default_assumptions(dcf_inputs)
                                _imp = _calc_implied(dcf_inputs, _asm_rev, _current_price)
                                if _imp and _imp.get("implied_discount_rate") is not None:
                                    _idr   = _imp["implied_discount_rate"]
                                    _inote = _imp.get("note", "")
                                    st.markdown('<div style="margin-top:32px;"></div>', unsafe_allow_html=True)
                                    st.markdown(
                                        "<p style='font-family:Pretendard,\"Noto Sans KR\",sans-serif;"
                                        "font-size:20px; font-weight:700; color:#1a1a1a; margin:0 0 12px 0;'>Reverse DCF — 시장 내재 할인율</p>",
                                        unsafe_allow_html=True,
                                    )
                                    _idr_clr = "#1b5e20" if _idr < assumptions["discount_rate"] else "#dc2626"
                                    st.markdown(
                                        f'<div style="padding:16px 20px; border-radius:10px;'
                                        f'background:#f8f9fa; border:1px solid #e0e0e0;">'
                                        f'<div style="font-size:14px; color:#555; margin-bottom:8px;">'
                                        f'현재 주가({_current_price:,}원) 기준 시장 내재 WACC</div>'
                                        f'<div style="font-size:26px; font-weight:700; color:{_idr_clr}; margin-bottom:10px;">{_idr:.2%}</div>'
                                        f'<div style="font-size:14px; color:#666; line-height:1.7;">{_inote}</div>'
                                        f'</div>',
                                        unsafe_allow_html=True,
                                    )
                            except Exception:
                                pass

                        # ── D8: 상대가치 분석 ─────────────────────────────
                        if _calc_rv is not None and dcf_inputs:
                            try:
                                _rv_key = f"rv_{company_name}"
                                if _rv_key not in st.session_state:
                                    st.session_state[_rv_key] = _calc_rv(dcf_inputs, assumptions)
                                _rv = st.session_state[_rv_key]
                                if _rv and "error" not in _rv:
                                    st.markdown('<div style="margin-top:40px;"></div>', unsafe_allow_html=True)
                                    st.markdown("<p style='font-family:Pretendard,\"Noto Sans KR\",sans-serif;font-size:20px;font-weight:700;color:#1a1a1a;margin:0 0 12px 0;'>상대가치 분석</p>", unsafe_allow_html=True)
                                    st.caption(f"성장 프로파일 기준 한국 시장 밴드 비교 | 프로파일: {_rv.get('growth_profile', '')}")
                                    _rv1, _rv2, _rv3 = st.columns(3)
                                    for _col, _method in zip([_rv1, _rv2, _rv3], ["per", "pbr", "ev_ebit"]):
                                        _d = _rv.get(_method, {})
                                        if not _d or _d.get("value") is None:
                                            continue
                                        with _col:
                                            _label = {"per": "PER", "pbr": "PBR", "ev_ebit": "EV/EBIT"}[_method]
                                            _val   = _d["value"]
                                            _lo, _hi = _d["benchmark_low"], _d["benchmark_high"]
                                            _sig   = _d["signal"]
                                            _sig_clr = {"Upside":"#1b5e20","Downside":"#dc2626","Neutral":"#f59e0b","N/A":"#888"}.get(_sig, "#888")
                                            st.metric(_label, f"{_val:.1f}x", delta=f"밴드 {_lo:.1f}x–{_hi:.1f}x")
                                            st.markdown(f'<div style="font-size:14px;color:{_sig_clr};font-weight:700;">{_sig}</div>', unsafe_allow_html=True)
                                            if _d.get("implied_price"):
                                                st.caption(f"적정가 추정: {int(_d['implied_price']):,}원")
                            except Exception as _e:
                                st.caption(f"상대가치 분석 로드 실패: {_e}")

            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div style="margin-top:48px;"></div>', unsafe_allow_html=True)
        st.markdown("""
<div style="height:1px; background:#eeeeee;"></div>
""", unsafe_allow_html=True)
        st.markdown('<div class="fade-section">', unsafe_allow_html=True)
        st.markdown(
            '<p style="text-align:center; color:#2e7d32; font-size:1rem; font-weight:500; margin-top:8px;">분석이 완료되었습니다.</p>',
            unsafe_allow_html=True,
        )
        st.markdown('</div>', unsafe_allow_html=True)
