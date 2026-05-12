import os
import base64
import streamlit as st
import pandas as pd
from graph import pipeline

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
if "graph_state" not in st.session_state:
    st.session_state.graph_state = None

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
    st.markdown("진행 주차: **2주차**")
    st.markdown("---")
    st.markdown("#### 에이전트 상태")
    for key, label in [("data", "Data Agent"), ("analysis", "Analysis Agent"), ("report", "Report Agent")]:
        s = st.session_state.agent_status[key]
        st.markdown(
            f'<div class="agent-status-row">'
            f'<span class="agent-icon" style="color:{COLOR[s]};">{ICON[s]}</span>'
            f'<span style="color:{COLOR[s]};">{label}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
    st.markdown("---")
    st.markdown("<span style='font-size:12px; color:#888;'>DART API · Claude AI</span>", unsafe_allow_html=True)

# ── 입력 영역 ─────────────────────────────────────────────
st.markdown('<div class="fade-section">', unsafe_allow_html=True)
st.markdown("<p style='font-size:14px; color:#555; margin-bottom:6px;'>분석할 기업명을 입력하세요</p>", unsafe_allow_html=True)
company = st.text_input("", placeholder="예: 에이피알", label_visibility="collapsed")
st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="fade-section">', unsafe_allow_html=True)
run = st.button("분석 시작")
st.markdown('</div>', unsafe_allow_html=True)

# ── 분석 실행 ─────────────────────────────────────────────
if run:
    if not company.strip():
        st.error("기업명을 입력해주세요")
    else:
        st.session_state.agent_status = {"data": "실행 중", "analysis": "실행 중", "report": "실행 중"}
        st.session_state.graph_state = None

        with st.spinner(f"{company} 분석 중..."):
            graph_state = pipeline.invoke({
                "request": f"{company} 재무 분석해줘",
                "company": company.strip(),
                "next_agent": "",
                "financials": {},
                "analysis": "",
                "result": "",
                "pdf_path": "",
            })

        st.session_state.graph_state = graph_state

        financials = graph_state.get("financials", {})
        analysis   = graph_state.get("analysis", "")
        pdf_path   = graph_state.get("pdf_path", "")

        st.session_state.agent_status = {
            "data":     "완료",
            "analysis": "완료" if analysis   else "오류",
            "report":   "완료" if pdf_path   else "대기",
        }
        st.rerun()

# ── 결과 표시 ─────────────────────────────────────────────
if st.session_state.graph_state is not None:
    graph_state = st.session_state.graph_state
    financials  = graph_state.get("financials", {})
    analysis    = graph_state.get("analysis", "")
    pdf_path    = graph_state.get("pdf_path", "")

    if not financials:
        st.markdown('<div class="fade-section">', unsafe_allow_html=True)
        st.error(graph_state.get("result", "데이터를 찾을 수 없습니다. 기업명을 확인해주세요."))
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        df = pd.DataFrame(
            [
                {
                    "연도": year,
                    "매출액 (백만원)":   d["매출액"],
                    "영업이익 (백만원)": d["영업이익"],
                    "순이익 (백만원)":   d["순이익"],
                }
                for year, d in sorted(financials.items())
            ]
        ).set_index("연도")

        fmt = "{:,.0f}".format
        styled_df = df.style.format({
            "매출액 (백만원)":   fmt,
            "영업이익 (백만원)": fmt,
            "순이익 (백만원)":   fmt,
        }).set_properties(**{"text-align": "center"}).set_table_styles(
            [{"selector": "th", "props": [("text-align", "center")]}]
        )

        company_name = graph_state.get("company", "")

        tab1, tab2 = st.tabs(["재무 데이터", "Claude 분석"])

        with tab1:
            st.markdown('<div class="fade-section">', unsafe_allow_html=True)
            st.subheader(f"{company_name} 연도별 재무 현황")
            st.dataframe(styled_df, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

        with tab2:
            st.markdown('<div class="fade-section">', unsafe_allow_html=True)
            st.subheader(f"{company_name} 재무 분석")
            st.write(analysis if analysis else "분석 결과가 없습니다.")
            if pdf_path and os.path.exists(pdf_path):
                with open(pdf_path, "rb") as f:
                    st.download_button("PDF 다운로드", f, file_name=os.path.basename(pdf_path), mime="application/pdf")
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="fade-section">', unsafe_allow_html=True)
        st.success("분석 완료!")
        st.markdown('</div>', unsafe_allow_html=True)
