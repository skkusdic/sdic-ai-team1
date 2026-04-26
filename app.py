import streamlit as st

st.set_page_config(page_title="SDIC AI 기업 분석", page_icon="📊")
st.title("SDIC AI 기업 분석 에이전트")
st.caption("Team [N] — SDIC 2026")

company = st.text_input("분석할 기업명을 입력하세요", placeholder="예: 삼성전자")

if st.button("분석 시작", type="primary"):
    if not company:
        st.warning("기업명을 입력해주세요.")
    else:
        with st.spinner(f"{company} 분석 중..."):
            st.info(f"Hello {company} — 분석 파이프라인은 2주차부터 연결됩니다.")
