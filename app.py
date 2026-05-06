import os
import streamlit as st
import pandas as pd
from graph import pipeline

st.set_page_config(page_title="AI 재무 컨설팅 어시스턴트", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;700&display=swap');

html, body, [class*="css"], .stApp {
    font-family: 'Noto Sans KR', sans-serif;
    background-color: #dcedc8 !important;
    color: #000000 !important;
}

[data-testid="stAppViewContainer"] {
    background-color: #dcedc8 !important;
}

[data-testid="stSidebar"] {
    background-color: #c5e1a5 !important;
}

h1, h2, h3, h4, h5, h6,
.stTitle, .stSubheader, .stHeader,
.stMarkdown, .stText, .stWrite,
label, .stTextInput label,
.stDataFrame, .stAlert,
.stSidebar, .stSidebar * {
    color: #000000 !important;
}

.stButton > button {
    color: #000000 !important;
    border-color: #558b2f !important;
    background-color: transparent !important;
    transition: background-color 0.3s ease;
}

.stButton > button:hover {
    background-color: #aed581 !important;
}

/* 표 셀 가운데 정렬 */
[data-testid="stDataFrame"] td,
[data-testid="stDataFrame"] th {
    text-align: center !important;
    justify-content: center !important;
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
    function init() {
        const sections = document.querySelectorAll('.fade-section');
        if (!sections.length) { setTimeout(init, 400); return; }

        // 페이지 전체 높이 기준으로 위치에 따라 초기 흐림 정도 결정
        const pageHeight = document.body.scrollHeight || 1000;

        sections.forEach(el => {
            const top = el.getBoundingClientRect().top + window.scrollY;
            const depthRatio = Math.min(top / pageHeight, 1); // 0(위) ~ 1(아래)
            const maxBlur = 10;
            const minOpacity = 0.1;

            const initBlur = depthRatio * maxBlur;
            const initOpacity = 1 - depthRatio * (1 - minOpacity);
            const initTranslate = depthRatio * 20;

            el.style.opacity = initOpacity;
            el.style.filter = `blur(${initBlur}px)`;
            el.style.transform = `translateY(${initTranslate}px)`;
            el.dataset.initBlur = initBlur;
            el.dataset.initOpacity = initOpacity;
            el.dataset.initTranslate = initTranslate;
        });

        function onScroll() {
            const viewH = window.innerHeight;
            const viewCenter = viewH / 2;

            sections.forEach(el => {
                const rect = el.getBoundingClientRect();
                const elCenter = rect.top + rect.height / 2;
                const distance = Math.abs(elCenter - viewCenter);
                const maxDist = viewH * 0.65;
                // 중앙에 가까울수록 ratio=1, 멀수록 ratio=0
                const ratio = Math.max(0, Math.min(1, 1 - distance / maxDist));

                const initBlur = parseFloat(el.dataset.initBlur || 0);
                const initOpacity = parseFloat(el.dataset.initOpacity || 1);
                const initTranslate = parseFloat(el.dataset.initTranslate || 0);

                el.style.opacity = initOpacity + (1 - initOpacity) * ratio;
                el.style.filter = `blur(${initBlur * (1 - ratio)}px)`;
                el.style.transform = `translateY(${initTranslate * (1 - ratio)}px)`;
            });
        }

        const scrollEl = window.parent.document.querySelector('[data-testid="stAppViewContainer"]')
                       || window.parent.document.body;
        scrollEl.addEventListener('scroll', onScroll, { passive: true });
        window.addEventListener('scroll', onScroll, { passive: true });
        onScroll();
    }

    setTimeout(init, 900);
})();
</script>
""", unsafe_allow_html=True)

# 상단: 타이틀(좌) + 로고(우) — 타이틀은 항상 선명
col_title, col_logo = st.columns([5, 1])
with col_title:
    st.markdown('<h1 style="opacity:1; filter:none;">AI 재무 컨설팅 어시스턴트</h1>', unsafe_allow_html=True)
with col_logo:
    logo_path = os.path.join(os.path.dirname(__file__), "skku_logo.png")
    if os.path.exists(logo_path):
        st.image(logo_path, width=180)
    else:
        st.markdown("<div style='text-align:right; font-weight:bold;'>성균관대학교</div>", unsafe_allow_html=True)

st.markdown('<div class="fade-section">', unsafe_allow_html=True)
st.markdown("---")
st.markdown('</div>', unsafe_allow_html=True)

with st.sidebar:
    st.header("팀 정보")
    st.write("**팀명:** SDIC AI Team 1")
    st.write("**분석 기업:** 에이피알")
    st.write("**현재 주차:** 2주차")
    st.markdown("---")
    st.write("DART API + Claude AI 기반")

st.markdown('<div class="fade-section">', unsafe_allow_html=True)
st.markdown("#### 분석할 기업명을 입력하세요")
company = st.text_input("", placeholder="예: 에이피알", label_visibility="collapsed")
st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="fade-section">', unsafe_allow_html=True)
run = st.button("분석 시작")
st.markdown('</div>', unsafe_allow_html=True)

if run:
    if not company.strip():
        st.markdown('<div class="fade-section">', unsafe_allow_html=True)
        st.warning("기업명을 입력해주세요")
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        with st.spinner(f"{company} 분석 중..."):
            state = pipeline.invoke({
                "company": company.strip(),
                "data": {},
                "result": "",
                "analysis": "",
            })

        data = state["data"]
        if not data:
            st.markdown('<div class="fade-section">', unsafe_allow_html=True)
            st.error(f"'{company}' 데이터를 찾을 수 없습니다. 기업명을 확인해주세요.")
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            df = pd.DataFrame(
                [
                    {
                        "연도": year,
                        "매출액 (백만원)": d["매출액"],
                        "영업이익 (백만원)": d["영업이익"],
                        "순이익 (백만원)": d["순이익"],
                    }
                    for year, d in sorted(data.items())
                ]
            ).set_index("연도")

            st.markdown('<div class="fade-section">', unsafe_allow_html=True)
            st.subheader(f"{company} 연도별 재무 현황")
            st.dataframe(df, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

            st.markdown('<div class="fade-section">', unsafe_allow_html=True)
            st.subheader("Claude 분석")
            st.write(state["analysis"])
            st.markdown('</div>', unsafe_allow_html=True)

            st.markdown('<div class="fade-section">', unsafe_allow_html=True)
            st.success("분석 완료!")
            st.markdown('</div>', unsafe_allow_html=True)
