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
    background-color: #ffffff !important;
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

.stButton > button {
    color: #ffffff !important;
    border: none !important;
    background-color: #2e7d32 !important;
    border-radius: 6px !important;
    padding: 10px 28px !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    letter-spacing: 0.02em !important;
    transition: background-color 0.2s ease !important;
}

.stButton > button:hover {
    background-color: #1b5e20 !important;
}

[data-testid="stDataFrame"] td,
[data-testid="stDataFrame"] th {
    text-align: center !important;
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
    font-size: 14px;
    color: #999;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    margin-bottom: 10px;
}
.kpi-value {
    font-size: 14px;
    font-weight: 600;
    color: #1a1a1a;
    margin-bottom: 6px;
    letter-spacing: -0.02em;
}
.kpi-delta {
    font-size: 14px;
    font-weight: 500;
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
    background-color: #c8e6c9 !important;
    height: 1px !important;
}

[data-testid="stDownloadButton"] > button {
    background-color: #dcedc8 !important;
    color: #2e7d32 !important;
    border: 1px solid #aed581 !important;
    font-weight: 500 !important;
}
[data-testid="stDownloadButton"] > button:hover {
    background-color: #c5e1a5 !important;
    border-color: #8bc34a !important;
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

/* 슬라이더 — 주황색 완전 제거, 초록 테마 적용 */
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
[data-baseweb="slider"] [class*="TrackActive"],
[data-baseweb="slider"] [class*="trackActive"] {
    background: linear-gradient(90deg, #c8e6c9, #1b5e20) !important;
}
[data-baseweb="slider"] [class*="Track"]:not([class*="Active"]):not([class*="active"]) {
    background: #e8f5e9 !important;
}

/* st.warning() 연한 연두색 */
[data-testid="stAlert"]:has(svg[data-testid="stAlertDynamicIcon"]) {
    background-color: #f1f8e9 !important;
    border-color: #a5d6a7 !important;
}
div[data-testid="stAlert"] {
    background-color: #f1f8e9 !important;
    border-color: #a5d6a7 !important;
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
        linear-gradient(170deg, rgba(187,202,146,0.88) 0%, rgba(45,69,53,0.93) 100%),
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
/* 검색창: 진한 반투명 회색 + 딥그린 두꺼운 테두리 */
[data-testid="stMain"] [data-baseweb="input"],
[data-testid="stMain"] [data-baseweb="base-input"] {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    outline: none !important;
}
[data-testid="stMain"] .stTextInput > div > div > input {
    background: rgba(60,60,60,0.45) !important;
    border: 2.5px solid #0a3d14 !important;
    color: #1a1a1a !important;
}
[data-testid="stMain"] .stTextInput > div > div > input::placeholder {
    color: rgba(0,0,0,0.55) !important;
}
[data-testid="stMain"] .stTextInput > div > div > input:focus {
    border-color: #0a3d14 !important;
    box-shadow: 0 0 0 3px rgba(10,61,20,0.3) !important;
}
/* 분석 시작 버튼: 진한 반투명 회색 + 딥그린 두꺼운 테두리 */
[data-testid="stMain"] .stButton > button {
    background-color: rgba(60,60,60,0.45) !important;
    border: 2.5px solid #0a3d14 !important;
    color: #1a1a1a !important;
}
[data-testid="stMain"] .stButton > button:hover {
    background-color: rgba(60,60,60,0.62) !important;
    border-color: #0a3d14 !important;
}

/* ── 제목 3D 바닥 그림자 ── */
[data-testid="stMain"] h1 {
    text-shadow: 0 30px 14px rgba(0,0,0,0.65) !important;
}
.header-logo img {
    filter: drop-shadow(0 30px 14px rgba(0,0,0,0.42)) !important;
}
[data-testid="stMain"] .stTextInput > div > div > input {
    box-shadow: 0 20px 14px rgba(0,0,0,0.42) !important;
}
[data-testid="stMain"] .stButton > button {
    box-shadow: 0 30px 14px rgba(0,0,0,0.42) !important;
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
        style="font-size:5.04rem; font-weight:500; margin:0; color:#ffffff;
               font-family:'Pretendard', 'Noto Sans KR', sans-serif;
               text-shadow:0 2px 16px rgba(0,0,0,0.18);">
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
    _dart_b64   = img_to_base64_transparent(_dart_path)   if os.path.exists(_dart_path)   else None
    _claude_b64 = img_to_base64_transparent(_claude_path) if os.path.exists(_claude_path) else None
    _logo_html = ""
    if _dart_b64:
        _logo_html += (
            f'<div style="overflow:hidden; display:inline-flex; align-items:center;">'
            f'<img src="data:image/png;base64,{_dart_b64}" style="'
            f'height:66px; width:auto; object-fit:contain;'
            f'mix-blend-mode:multiply; border:none; outline:none; box-shadow:none;'
            f'clip-path:inset(6px);'
            f'">'
            f'</div>'
        )
    if _claude_b64:
        _logo_html += (
            f'<img src="data:image/png;base64,{_claude_b64}" style="'
            f'height:28px; width:auto; object-fit:contain;'
            f'mix-blend-mode:multiply; border:none; outline:none; box-shadow:none;'
            f'">'
        )
    st.markdown(f"""
<div style="margin:0; padding:0; line-height:1.4;">
    <div style="font-size:13px; color:#888; margin-bottom:0;">Powered by</div>
    <div style="font-size:13px; color:#888; font-weight:700; margin-top:0;">DART API · Claude AI</div>
    <div style="display:flex; gap:4px; margin-top:2px; margin-bottom:0; align-items:center; margin-left:-20px;">
        {_logo_html}
    </div>
</div>
<div style="height:1px; background-color:{'#aaaaaa' if _is_startup else '#2e7d32'}; margin:16px 0 0 0; border-radius:1px;"></div>
""", unsafe_allow_html=True)
    st.markdown("<div style='margin-top:20px;'></div>", unsafe_allow_html=True)
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

        # ── 스타일 DataFrame ──
        fmt = "{:,.0f}".format
        styled_df = df.style.format({
            "매출액 (백만원)":   fmt,
            "영업이익 (백만원)": fmt,
            "순이익 (백만원)":   fmt,
            "영업이익률 (%)":  "{:.1f}".format,
        }).set_properties(**{"text-align": "center"}).set_table_styles(
            [{"selector": "th", "props": [("text-align", "center")]}]
        ).hide(axis="index")

        # ── 탭 ──
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["재무 데이터", "Claude 분석", "AI 질문", "기업 비교", "DCF 밸류에이션"])

        with tab1:
            st.markdown('<div class="fade-section">', unsafe_allow_html=True)
            st.markdown(f"<p style='font-size:1.875rem; font-weight:700; color:#1a1a1a; letter-spacing:-0.02em; margin-bottom:16px;'>{company_name} 연도별 재무 현황 (단위: 백만원)</p>", unsafe_allow_html=True)

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

            st.markdown('<div style="margin:32px 0 24px 0; border-top:1px solid #f0f0f0;"></div>', unsafe_allow_html=True)
            st.dataframe(styled_df, use_container_width=True, hide_index=True)

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
                title=f"{company_name} 매출액 / 영업이익 / 순이익 추이",
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
                title=f"{company_name} 영업이익률 추이",
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
            st.subheader("YoY 성장률")
            st.dataframe(yoy, use_container_width=True, hide_index=True)
            st.markdown('</div>', unsafe_allow_html=True)

        with tab2:
            import re as _re
            st.markdown('<div class="fade-section">', unsafe_allow_html=True)
            st.markdown(
                f"<p style='font-size:1.875rem; font-weight:700; color:#1a1a1a;"
                f"letter-spacing:-0.02em; margin-bottom:24px;'>"
                f"{company_name} 사업 분석 보고서</p>",
                unsafe_allow_html=True,
            )

            if not analysis:
                st.info("분석 결과가 없습니다.")
            else:
                def _sentences_html(text):
                    sents = _re.split(r'(?<=[.?!])\s+', text.strip())
                    return '<br>'.join(s.strip() for s in sents if s.strip())

                def _parse_sections(text):
                    # 마크다운 헤더 제거
                    t = _re.sub(r'(?m)^#+\s+.+\n?', '', text.strip()).strip()
                    # ** / * bold 마커 제거
                    t = _re.sub(r'\*+([^*\n]+)\*+', r'\1', t)

                    # re.split 으로 "줄 시작 숫자." 패턴에서 분리
                    # capturing group 으로 번호 유지
                    raw = _re.split(r'(?m)^(\d+)\.\s+', t)
                    # raw = ['앞텍스트', '1', '내용1', '2', '내용2', ...]
                    sections = []
                    i = 1
                    while i + 1 < len(raw):
                        num     = raw[i].strip()
                        content = raw[i + 1].strip()
                        # 첫 줄이 제목, 나머지가 본문
                        lines = content.split('\n', 1)
                        first = lines[0].strip()
                        rest  = lines[1].strip() if len(lines) > 1 else ''
                        # "제목: 본문" 형태 분리
                        if ':' in first:
                            ci = first.index(':')
                            cand = first[:ci].strip()
                            if len(cand) <= 35:
                                title = cand
                                body  = (first[ci+1:].strip() + ' ' + rest).strip()
                            else:
                                title, body = first, rest
                        else:
                            title, body = first, rest
                        sections.append((num, title, body))
                        i += 2
                    return sections

                _sections = _parse_sections(analysis)

                if _sections:
                    for _i, (_num, _title, _body) in enumerate(_sections):
                        _td  = f"{_i * 0.13:.2f}s"
                        _ttd = f"{_i * 0.13 + 0.07:.2f}s"
                        if _i > 0:
                            st.markdown(
                                '<div style="height:1px;background:#e0e0e0;margin:0;"></div>',
                                unsafe_allow_html=True,
                            )
                        st.markdown(f"""
<div style="padding:24px 0 20px 16px; border-left:3px solid #c8e6c9;
            animation:sectionFadeUp 0.4s ease {_td} both;">
  <div style="font-size:1rem; font-weight:700; color:#2e7d32; margin-bottom:12px;
              animation:titleSlideIn 0.35s ease {_ttd} both;">
    {_num}. {_title}
  </div>
  <p style="font-size:15px; line-height:1.95; color:#333; margin:0; word-break:keep-all;">
    {_sentences_html(_body)}
  </p>
</div>""", unsafe_allow_html=True)
                else:
                    # 번호 섹션이 없는 경우(fallback 분석) — 문단별로 구분
                    _paras = [p.strip() for p in _re.split(r'\n{2,}', analysis.strip()) if p.strip()]
                    for _pi, _para in enumerate(_paras):
                        if _pi > 0:
                            st.markdown(
                                '<div style="height:1px;background:#e0e0e0;margin:0;"></div>',
                                unsafe_allow_html=True,
                            )
                        st.markdown(
                            f'<div style="padding:20px 0 16px 16px; border-left:3px solid #c8e6c9;">'
                            f'<p style="font-size:15px;line-height:1.95;color:#333;margin:0;word-break:keep-all;">'
                            f'{_sentences_html(_para)}</p></div>',
                            unsafe_allow_html=True,
                        )
                # 디버그 expander (파싱 확인용)
                with st.expander("🔍 원문 보기 (디버그)", expanded=False):
                    st.code(analysis, language=None)
            st.markdown('</div>', unsafe_allow_html=True)

        with tab3:
            st.markdown('<div class="fade-section">', unsafe_allow_html=True)
            st.subheader(f"{company_name} AI 질문")

            _TEXT2SQL_KEYWORDS = {"평균", "합계", "합", "총", "최대", "최소", "몇", "계산", "비교", "순위", "sum", "avg", "max", "min"}

            mode = st.radio(
                "질의 모드",
                ["자동", "RAG", "Text2SQL"],
                index=["자동", "RAG", "Text2SQL"].index(st.session_state.qa_mode),
                horizontal=True,
                key="tab3_mode",
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
            ask_btn = st.button("질문하기", key="tab3_ask")

            if ask_btn and question.strip():
                q = question.strip()

                if mode == "자동":
                    used_mode = "Text2SQL" if any(kw in q for kw in _TEXT2SQL_KEYWORDS) else "RAG"
                else:
                    used_mode = mode

                with st.spinner(f"{used_mode} 처리 중..."):
                    try:
                        if used_mode == "RAG":
                            claude_answer, top_chunks = answer_with_rag(q, financials, company_name)
                            result = {"mode": "RAG", "q": q, "chunks": top_chunks, "answer": claude_answer}
                        else:
                            sql, df_result, err = run_text2sql(q, company_name)
                            result = {"mode": "Text2SQL", "q": q, "sql": sql, "df": df_result, "error": err}
                    except Exception as e:
                        result = {"mode": used_mode, "q": q, "error": str(e)}

                st.session_state.qa_history.insert(0, result)

            if st.session_state.qa_history:
                st.markdown("---")
                for item in st.session_state.qa_history:
                    st.markdown(f"**Q.** {item['q']}")
                    badge_color = "#1565c0" if item["mode"] == "RAG" else "#6a1b9a"
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
                        st.info(item["answer"])
                    else:
                        st.markdown("**생성된 SQL**")
                        st.code(item["sql"], language="sql")
                        if item.get("error"):
                            st.error(f"실행 오류: {item['error']}")
                        elif item["df"] is not None:
                            st.dataframe(item["df"], use_container_width=True, hide_index=True)

                    st.markdown("")

            st.markdown('</div>', unsafe_allow_html=True)

        with tab4:
            st.markdown('<div class="fade-section">', unsafe_allow_html=True)
            st.markdown(
                "<p style='font-size:1.875rem; font-weight:700; color:#1a1a1a;"
                "letter-spacing:-0.02em; margin-bottom:16px;'>기업 비교</p>",
                unsafe_allow_html=True,
            )
            # ── 기업 선택 카드 레이아웃 ──
            _card_style = (
                "background:#ffffff; border:1px solid #e8e8e8; border-radius:12px;"
                "padding:28px 32px; text-align:center;"
                "box-shadow:0 6px 20px rgba(0,0,0,0.12), 0 2px 6px rgba(0,0,0,0.08);"
            )
            _col_l, _col_mid, _col_r = st.columns([5, 1, 5])
            with _col_l:
                with st.container(border=True):
                    st.markdown(
                        f'<div style="text-align:center; padding:12px 0 8px 0;">'
                        f'<div style="font-size:13px; color:#999; letter-spacing:0.06em; text-transform:uppercase; margin-bottom:14px;">비교 기준 기업</div>'
                        f'<div style="font-size:1.6rem; font-weight:700; color:#1a1a1a; letter-spacing:-0.02em;">{company_name}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
            with _col_mid:
                st.markdown(
                    '<div style="display:flex; flex-direction:column; align-items:center; margin-bottom:-32px;">'
                    '  <div style="padding-top:65px; width:100%;">'
                    '    <div style="height:2px; background:#e0e0e0;"></div>'
                    '  </div>'
                    '  <div style="width:2px; flex:1; min-height:80px; background:#e0e0e0;"></div>'
                    '</div>',
                    unsafe_allow_html=True,
                )
            with _col_r:
                with st.container(border=True):
                    st.markdown(
                        '<div style="font-size:13px; color:#999; letter-spacing:0.06em; text-transform:uppercase; margin-bottom:12px; padding-top:12px; text-align:center;">비교 대상 기업</div>',
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

            _btn_l, _btn_c, _btn_r = st.columns([2, 1, 2])
            with _btn_c:
                st.markdown(
                    '<div style="display:flex; justify-content:center; margin-top:-16px; margin-bottom:4px;">'
                    '<div style="width:2px; height:28px; background:#e0e0e0;"></div>'
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
                        '<div style="height:1px; background:linear-gradient(90deg,#2e7d32,#81c784,#2e7d32); margin:32px 0 40px 0; border-radius:1px;"></div>',
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
                        _mstyled = (
                            _mdf.style
                            .format({company_name: _fmt, cmp_name: _fmt})
                            .set_properties(**{"text-align": "center"})
                            .set_table_styles([{"selector": "th", "props": [("text-align", "center")]}])
                            .hide(axis="index")
                        )
                        with _col:
                            with st.container(border=True):
                                st.markdown(
                                    f'<div style="font-size:14px; color:#999; letter-spacing:0.06em;'
                                    f'text-transform:uppercase; margin-bottom:12px; font-weight:500; text-align:center;">'
                                    f'{_metric} (백만원)</div>',
                                    unsafe_allow_html=True,
                                )
                                st.dataframe(_mstyled, use_container_width=True, hide_index=True)

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
                            title=f"{metric} 비교 (백만원)",
                            barmode="group",
                            xaxis=dict(tickmode="array", tickvals=common_years, ticktext=[str(y) for y in common_years]),
                            yaxis_title="백만원",
                            height=400,
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                        )
                        st.plotly_chart(fig_cmp, use_container_width=True)

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

                    # ── 슬라이더: 좌우 여백 추가 ──
                    st.markdown("### 가정 조정")
                    _sl, _sc, _sr = st.columns([1, 6, 1])
                    with _sc:
                        col1, col2 = st.columns(2)
                        with col1:
                            g = st.slider("매출 성장률", 0.0, 0.3,
                                          float(assumptions["revenue_growth_rate"]), 0.01,
                                          format="%.0f%%", key="dcf_g")
                            margin = st.slider("영업이익률", 0.0, 0.5,
                                               float(assumptions["operating_margin"]), 0.01,
                                               format="%.0f%%", key="dcf_m")
                            wacc = st.slider("할인율 (WACC)", 0.05, 0.2,
                                             float(assumptions["discount_rate"]), 0.005,
                                             format="%.1f%%", key="dcf_w")
                        with col2:
                            tgr = st.slider("영구성장률", 0.0, 0.05,
                                            float(assumptions["terminal_growth_rate"]), 0.005,
                                            format="%.1f%%", key="dcf_tgr")
                            tax = st.slider("법인세율", 0.1, 0.35,
                                            float(assumptions["tax_rate"]), 0.01,
                                            format="%.0f%%", key="dcf_tax")

                    assumptions.update({
                        "revenue_growth_rate": g,
                        "operating_margin": margin,
                        "discount_rate": wacc,
                        "terminal_growth_rate": tgr,
                        "tax_rate": tax,
                    })

                    result = calculate_dcf(dcf_inputs, assumptions)

                    if result.get("error"):
                        st.error(result["error"])
                    else:
                        val = result["valuation"]
                        vps = val.get("value_per_share")
                        v_status = val.get("valuation_status", "valid")
                        v_note   = val.get("valuation_note", "")

                        if vps is not None:
                            vps_display = f"{vps:,}원"
                            vps_warning = None
                        elif v_status == "invalid_negative_fcf":
                            vps_display = "N/A (FCF 음수)"
                            vps_warning = v_note
                        elif v_status == "invalid_negative_ev":
                            vps_display = "N/A (EV 음수)"
                            vps_warning = None
                        elif v_status == "invalid_negative_equity":
                            vps_display = "N/A (순부채 초과)"
                            vps_warning = None
                        else:
                            vps_display = "N/A"
                            vps_warning = None

                        # ── DCF KPI 카드 3개 ──
                        def _dcf_card(label, value):
                            return (
                                f'<div style="background:#ffffff; border:1px solid #e8e8e8; border-radius:12px;'
                                f'padding:36px 20px; text-align:center; margin-bottom:12px;'
                                f'box-shadow:0 6px 20px rgba(0,0,0,0.12), 0 2px 6px rgba(0,0,0,0.08);'
                                f'transition:transform 0.2s ease, box-shadow 0.2s ease; cursor:default;">'
                                f'<div style="font-size:13px; color:#999; letter-spacing:0.06em;'
                                f'text-transform:uppercase; margin-bottom:14px;">{label}</div>'
                                f'<div style="font-size:26px; font-weight:600; color:#1a1a1a;'
                                f'letter-spacing:-0.02em; white-space:nowrap;">{value}</div>'
                                f'</div>'
                            )
                        st.markdown('<div style="margin-top:28px;"></div>', unsafe_allow_html=True)
                        _, _dv1, _dv2, _dv3, _ = st.columns([1, 3, 3, 3, 1])
                        with _dv1:
                            st.markdown(_dcf_card("Enterprise Value", f"{val['enterprise_value']:,.0f}억원"), unsafe_allow_html=True)
                        with _dv2:
                            st.markdown(_dcf_card("Equity Value", f"{val['equity_value']:,.0f}억원"), unsafe_allow_html=True)
                        with _dv3:
                            st.markdown(_dcf_card("주당 가치", vps_display), unsafe_allow_html=True)
                        if vps_warning:
                            _, _wv, _ = st.columns([1, 3, 1])
                            with _wv:
                                st.warning(vps_warning)

                        # ── 5개년 추정 표 ──
                        st.markdown('<div style="margin-top:32px;"></div>', unsafe_allow_html=True)
                        st.markdown("### 5개년 추정")
                        proj = result["projection"]

                        _FCF_METHOD_LABELS = {
                            "NOPAT_DA_CAPEX_CF_DIRECT": "FCF = NOPAT + D&A − 유지CAPEX (CF 직접 추출)",
                            "NOPAT_DA_CAPEX_XBRL":      "FCF = NOPAT + D&A − 유지CAPEX (XBRL fallback)",
                            "CFO_CAPEX":                "FCF = 영업현금흐름 − CAPEX (D&A 추출 불가)",
                            "LOW_CONFIDENCE_PROXY":     "⚠ FCF 신뢰도 낮음 — 참고값으로만 활용",
                        }
                        _fcf_method = result.get("fcf_method") or (
                            proj.get(1, {}).get("fcf_method") if proj else None
                        )
                        if _fcf_method and _fcf_method in _FCF_METHOD_LABELS:
                            _, _mc, _ = st.columns([1, 4, 1])
                            with _mc:
                                _method_text = _FCF_METHOD_LABELS[_fcf_method]
                                if _fcf_method == "LOW_CONFIDENCE_PROXY":
                                    st.warning(_method_text)
                                else:
                                    st.caption(_method_text)

                        _proj_rows = []
                        for yr, p in proj.items():
                            _maint = p.get("maintenance_capex")
                            if _maint is None:
                                _maint = p.get("capex")
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
                        _proj_styled = (
                            _proj_df.style
                            .format(_fmt_cols, na_rep="-")
                            .set_properties(**{"text-align": "center"})
                            .set_table_styles([{"selector": "th", "props": [("text-align", "center")]}])
                            .hide(axis="index")
                        )
                        _, _tbl, _ = st.columns([1, 4, 1])
                        with _tbl:
                            st.dataframe(_proj_styled, use_container_width=True, hide_index=True)

                        # ── Bear / Base / Bull 시나리오 ──
                        if _calc_scenarios is not None:
                            try:
                                _asm_scen = build_default_assumptions(dcf_inputs)
                                _scen_res = _calc_scenarios(dcf_inputs, _asm_scen)
                                st.markdown('<div style="margin-top:32px;"></div>', unsafe_allow_html=True)
                                st.markdown("### 시나리오 분석")
                                _scen_rows = []
                                for _name, _s in _scen_res.items():
                                    _sv = _s.get("valuation", {})
                                    _ss = _sv.get("valuation_status", "valid")
                                    _svps = _sv.get("value_per_share")
                                    if _svps is not None:
                                        _vps_cell = f"{_svps:,}원"
                                    elif _ss == "invalid_negative_fcf":
                                        _vps_cell = "N/A [FCF 음수]"
                                    elif _ss == "invalid_negative_ev":
                                        _vps_cell = "N/A [EV 음수]"
                                    elif _ss == "invalid_negative_equity":
                                        _vps_cell = "N/A [순부채 초과]"
                                    else:
                                        _vps_cell = "N/A"
                                    _sa = _s.get("assumptions", {})
                                    _current_price = dcf_inputs.get("company_info", {}).get("current_price")
                                    if _svps and _current_price and _current_price > 0:
                                        _updown = f"{(_svps / _current_price - 1) * 100:+.1f}%"
                                    else:
                                        _updown = "-"
                                    _g_list = _sa.get("revenue_growth_rates") or [_sa.get("revenue_growth_rate", 0)] * 5
                                    _g_repr = f"{_g_list[0]:.1%}" if _g_list else "-"
                                    _scen_rows.append({
                                        "시나리오":       _name,
                                        "성장률(1~5년)":  _g_repr,
                                        "할인율":         f"{_sa.get('discount_rate', 0):.1%}",
                                        "OPM":            f"{_sa.get('operating_margin', 0):.1%}",
                                        "TGR":            f"{_sa.get('terminal_growth_rate', 0):.1%}",
                                        "주당가치":       _vps_cell,
                                        "현재가 대비":    _updown,
                                    })
                                if _scen_rows:
                                    _scen_df = pd.DataFrame(_scen_rows)
                                    _, _stbl, _ = st.columns([1, 4, 1])
                                    with _stbl:
                                        st.dataframe(
                                            _scen_df.style
                                            .set_properties(**{"text-align": "center"})
                                            .set_table_styles([{"selector": "th", "props": [("text-align", "center")]}])
                                            .hide(axis="index"),
                                            use_container_width=True,
                                            hide_index=True,
                                        )
                            except Exception as _e:
                                st.caption(f"시나리오 분석 로드 실패: {_e}")

                        if result.get("warnings"):
                            _, _wc, _ = st.columns([1, 4, 1])
                            with _wc:
                                for w in result["warnings"]:
                                    st.warning(w)
            st.markdown('</div>', unsafe_allow_html=True)

        # ── PDF 다운로드 (탭 밖) ──
        st.markdown('<div style="margin-top:48px;"></div>', unsafe_allow_html=True)
        if pdf_path and os.path.exists(pdf_path):
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

        st.markdown('<div style="margin-top:48px;"></div>', unsafe_allow_html=True)
        st.markdown("""
<div style="height:1px; background:linear-gradient(90deg,#2e7d32,#81c784,#2e7d32); border-radius:1px;"></div>
""", unsafe_allow_html=True)
        st.markdown('<div class="fade-section">', unsafe_allow_html=True)
        st.markdown(
            '<p style="text-align:center; color:#2e7d32; font-size:1rem; font-weight:500; margin-top:8px;">분석이 완료되었습니다.</p>',
            unsafe_allow_html=True,
        )
        st.markdown('</div>', unsafe_allow_html=True)
