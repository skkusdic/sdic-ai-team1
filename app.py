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

st.set_page_config(page_title="AI 재무 컨설팅 어시스턴트", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap');

html, body, [class*="css"], .stApp {
    font-family: 'Noto Sans KR', sans-serif;
    background-color: #ffffff !important;
    color: #1a1a1a !important;
}

[data-testid="stAppViewContainer"] {
    background-color: #ffffff !important;
}

[data-testid="stSidebar"] {
    background-color: #fafafa !important;
    border-right: 1px solid #eeeeee !important;
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
    border: 1px solid #e0e0e0 !important;
    border-radius: 6px !important;
    padding: 10px 14px !important;
    font-size: 15px !important;
    background-color: #ffffff !important;
    color: #1a1a1a !important;
    transition: border-color 0.2s ease !important;
}

.stTextInput > div > div > input:focus {
    border-color: #1a1a1a !important;
    box-shadow: none !important;
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
    gap: 16px;
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
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    margin-bottom: 8px;
}
.kpi-label {
    font-size: 11px;
    color: #999;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    margin-bottom: 10px;
}
.kpi-value {
    font-size: 1.5rem;
    font-weight: 600;
    color: #1a1a1a;
    margin-bottom: 6px;
    letter-spacing: -0.02em;
}
.kpi-delta {
    font-size: 12px;
    font-weight: 500;
}

@keyframes spin {
    0%   { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
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

# ── 헤더: 타이틀 + 로고 ───────────────────────────────────
col_title, col_logo = st.columns([5, 1])
with col_title:
    st.markdown(
        '<h1 style="opacity:1; filter:none; font-size:3.2rem; font-weight:500; margin-bottom:0;">'
        'AI 재무 컨설팅 어시스턴트</h1>',
        unsafe_allow_html=True,
    )
with col_logo:
    skku_path = os.path.join(os.path.dirname(__file__), "skku.png")
    sdic_path  = os.path.join(os.path.dirname(__file__), "skku_logo.png")

    def img_to_base64(path):
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()

    if os.path.exists(skku_path) and os.path.exists(sdic_path):
        skku_b64 = img_to_base64(skku_path)
        sdic_b64  = img_to_base64(sdic_path)
        st.markdown(f"""
        <div class="logo-row" style="justify-content:flex-end;">
            <img src="data:image/png;base64,{skku_b64}" style="height:88px; width:auto; object-fit:contain;">
            <div class="logo-divider" style="height:72px;"></div>
            <img src="data:image/png;base64,{sdic_b64}" style="height:88px; width:auto; object-fit:contain;">
        </div>""", unsafe_allow_html=True)
    elif os.path.exists(sdic_path):
        sdic_b64 = img_to_base64(sdic_path)
        st.markdown(f"""
        <div style="display:flex; justify-content:flex-end;">
            <img src="data:image/png;base64,{sdic_b64}" style="height:88px; width:auto; object-fit:contain;">
        </div>""", unsafe_allow_html=True)

st.markdown('<div class="fade-section">', unsafe_allow_html=True)
st.markdown("---")
st.markdown('</div>', unsafe_allow_html=True)

# ── 사이드바 ──────────────────────────────────────────────
ICON = {"대기": "○", "실행 중": "◌", "완료": "●", "오류": "✗"}
COLOR = {"대기": "#aaaaaa", "실행 중": "#f59e0b", "완료": "#2e7d32", "오류": "#dc2626"}

with st.sidebar:
    st.markdown("#### 팀 정보")
    st.markdown("**SDIC AI Team 1**")
    st.markdown("분석 기업: **에이피알**")
    st.markdown("진행 주차: **4주차**")
    st.markdown("---")
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
    st.markdown("---")
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
    st.markdown("---")
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
    st.markdown("---")
    st.markdown("<span style='font-size:12px; color:#888;'>DART API · Claude AI</span>", unsafe_allow_html=True)

# ── 입력 영역 ─────────────────────────────────────────────
st.markdown('<div class="fade-section">', unsafe_allow_html=True)
st.markdown("<p style='font-size:14px; color:#555; margin-bottom:6px;'>분석할 기업명을 입력하세요</p>", unsafe_allow_html=True)
company_input = st.text_input("", placeholder="예: 에이피알", label_visibility="collapsed")
st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="fade-section">', unsafe_allow_html=True)
run = st.button("분석 시작")
st.markdown('</div>', unsafe_allow_html=True)

# ── 분석 실행 ─────────────────────────────────────────────
if run:
    if not company_input.strip():
        st.error("기업명을 입력해주세요")
    else:
        st.session_state.agent_status = {"data": "실행 중", "analysis": "실행 중", "report": "실행 중"}
        st.session_state.final_state = None

        with st.spinner(f"{company_input} 분석 중..."):
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
        latest_year = latest["연도"]

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
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["재무 데이터", "Claude 분석", "AI 질문 (RAG + Text2SQL)", "기업 비교", "DCF 밸류에이션"])

        with tab1:
            st.markdown('<div class="fade-section">', unsafe_allow_html=True)
            st.subheader(f"{company_name} 연도별 재무 현황 (백만원)")

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

            st.markdown("---")
            st.dataframe(styled_df, use_container_width=True)

            # 3지표 추이 막대 차트 — 매출액 꼭짓점 점+선 항상 표시
            _years = [int(y) for y in df["연도"].tolist()]
            _bar_cols  = ["매출액 (백만원)", "영업이익 (백만원)", "순이익 (백만원)"]
            _bar_names = ["매출액", "영업이익", "순이익"]
            _bar_clrs  = ["#1b5e20", "#4caf50", "#aed581"]

            _bar_traces = [
                go.Bar(name=nm, x=_years, y=df[col].tolist(), marker_color=clr,
                       showlegend=True)
                for col, nm, clr in zip(_bar_cols, _bar_names, _bar_clrs)
            ]
            # 매출액 막대 위 가운데에 점+선 — 그룹 내 첫 번째 막대 x 오프셋 직접 계산
            _bargap = 0.2
            _n = len(_bar_cols)  # 3
            _bar_w = (1.0 - _bargap) / _n
            _rev_offset = (0 - (_n - 1) / 2) * _bar_w
            _rev_x  = [y + _rev_offset for y in _years]
            _rev_y  = df["매출액 (백만원)"].tolist()

            _rev_line = go.Scatter(
                name="매출액 추이선",
                x=_rev_x, y=_rev_y,
                mode="lines+markers",
                line=dict(color="#1b5e20", width=2.5),
                marker=dict(size=10, color="#1b5e20", line=dict(width=2, color="white")),
                showlegend=True,
            )
            fig_trend = go.Figure(data=_bar_traces + [_rev_line])
            fig_trend.update_layout(
                title=f"{company_name} 매출액 / 영업이익 / 순이익 추이",
                barmode="group",
                bargap=0.2,
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
                line=dict(color="#1b5e20", width=2.5),
                marker=dict(size=10, color="#1b5e20", line=dict(width=2, color="white")),
                showlegend=True,
            )
            fig_margin = go.Figure(data=[_mg_bar, _mg_line])
            fig_margin.update_layout(
                title=f"{company_name} 영업이익률 추이",
                xaxis=dict(tickmode="array", tickvals=_years, ticktext=[str(y) for y in _years]),
                yaxis=dict(title="영업이익률 (%)"),
            )
            st.plotly_chart(fig_margin, use_container_width=True)

            # 차트 선/점 SVG path에 IntersectionObserver + CSS 애니메이션 적용
            st.markdown("""
<script>
(function() {
    var done = new WeakSet();

    function animateChart(chart) {
        if (done.has(chart)) return;
        var lines = chart.querySelectorAll('.js-line');
        if (!lines.length) return;
        done.add(chart);

        // 선·점 초기 숨김
        lines.forEach(function(p) {
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

        new IntersectionObserver(function(entries, obs) {
            entries.forEach(function(entry) {
                if (!entry.isIntersecting) return;
                var el = entry.target;
                el.querySelectorAll('.js-line').forEach(function(p) {
                    try {
                        p.getBoundingClientRect();
                        p.style.transition = 'stroke-dashoffset 1.4s ease';
                        p.style.strokeDashoffset = '0';
                    } catch(e) {}
                });
                el.querySelectorAll('.scatter .points path').forEach(function(pt, i) {
                    pt.style.transition = 'opacity 0.4s ease ' + (1.2 + i * 0.15) + 's';
                    pt.style.opacity = '1';
                });
                obs.disconnect();
            });
        }, { threshold: 0.25 }).observe(chart);
    }

    function scan() {
        var doc = window.parent.document;
        doc.querySelectorAll('.js-plotly-plot').forEach(animateChart);
    }

    // 최초 실행 + Streamlit 재렌더 시 재감지
    setTimeout(scan, 600);
    setTimeout(scan, 1400);
    var t = null;
    new MutationObserver(function() {
        clearTimeout(t);
        t = setTimeout(scan, 300);
    }).observe(window.parent.document.body, { childList: true, subtree: true });
})();
</script>
""", unsafe_allow_html=True)

            # YoY 성장률 표
            st.subheader("YoY 성장률")
            st.dataframe(yoy, use_container_width=True, hide_index=True)
            st.markdown('</div>', unsafe_allow_html=True)

        with tab2:
            st.markdown('<div class="fade-section">', unsafe_allow_html=True)
            st.subheader(f"{company_name} 재무 분석")
            st.write(analysis if analysis else "분석 결과가 없습니다.")
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
            st.subheader("기업 비교")
            st.markdown(f"**기준 기업:** {company_name}")

            cmp_input = st.text_input(
                "비교할 기업명 입력",
                placeholder="예: 카카오, Samsung, LGdisplay",
                key="cmp_company_input",
            )
            cmp_btn = st.button("비교 조회", key="cmp_btn")

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
                    st.markdown("---")
                    st.markdown(f"### {company_name} vs {cmp_name} — 재무 비교")

                    # ── 비교 표 ──
                    cmp_rows = []
                    for year in common_years:
                        a = fin_norm[year]
                        b = cmp_norm[year]
                        cmp_rows.append({
                            "연도":                        year,
                            f"{company_name} 매출액":      a.get("매출액", 0),
                            f"{cmp_name} 매출액":          b.get("매출액", 0),
                            f"{company_name} 영업이익":    a.get("영업이익", 0),
                            f"{cmp_name} 영업이익":        b.get("영업이익", 0),
                            f"{company_name} 순이익":      a.get("순이익", 0),
                            f"{cmp_name} 순이익":          b.get("순이익", 0),
                        })
                    cmp_df = pd.DataFrame(cmp_rows)

                    fmt_int = "{:,.0f}".format
                    fmt_cols = [c for c in cmp_df.columns if c != "연도"]
                    cmp_styled = cmp_df.style.format({c: fmt_int for c in fmt_cols}).set_properties(
                        **{"text-align": "center"}
                    ).set_table_styles([{"selector": "th", "props": [("text-align", "center")]}])
                    st.dataframe(cmp_styled, use_container_width=True)

                    # ── 그룹 막대 차트 ──
                    colors_a = {"매출액": "#1b5e20", "영업이익": "#4caf50", "순이익": "#aed581"}
                    colors_b = {"매출액": "#0d47a1", "영업이익": "#1976d2", "순이익": "#64b5f6"}

                    for metric in ["매출액", "영업이익", "순이익"]:
                        fig_cmp = go.Figure([
                            go.Bar(
                                name=company_name,
                                x=common_years,
                                y=[fin_norm[y].get(metric, 0) for y in common_years],
                                marker_color=colors_a[metric],
                            ),
                            go.Bar(
                                name=cmp_name,
                                x=common_years,
                                y=[cmp_norm[y].get(metric, 0) for y in common_years],
                                marker_color=colors_b[metric],
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
            st.subheader("DCF 밸류에이션")
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

                    st.markdown("### 가정 조정")
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
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Enterprise Value", f"{val['enterprise_value']:,.0f}억원")
                        c2.metric("Equity Value", f"{val['equity_value']:,.0f}억원")
                        vps = val.get("value_per_share")
                        c3.metric("주당 가치", f"{vps:,}원" if vps else "N/A")

                        st.markdown("### 5개년 추정")
                        import pandas as pd
                        proj = result["projection"]
                        df = pd.DataFrame([
                            {"연차": f"{yr}년차",
                             "매출(억원)": p["revenue"],
                             "FCF(억원)": p["fcf"],
                             "PV_FCF(억원)": p["pv_fcf"]}
                            for yr, p in proj.items()
                        ])
                        st.dataframe(df, use_container_width=True)

                        if result.get("warnings"):
                            for w in result["warnings"]:
                                st.warning(w)

        # ── PDF 다운로드 (탭 밖) ──
        if pdf_path and os.path.exists(pdf_path):
            with open(pdf_path, "rb") as f:
                st.download_button(
                    label="PDF 리포트 다운로드",
                    data=f,
                    file_name=f"{company_name}_재무분석.pdf",
                    mime="application/pdf",
                )

        st.markdown('<div class="fade-section">', unsafe_allow_html=True)
        st.success("분석 완료!")
        st.markdown('</div>', unsafe_allow_html=True)
