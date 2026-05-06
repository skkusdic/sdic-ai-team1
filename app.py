import streamlit as st
import pandas as pd
from graph import pipeline

st.set_page_config(page_title="AI 재무 컨설팅 어시스턴트", layout="wide")

with st.sidebar:
    st.header("팀 정보")
    st.write("**팀명:** SDIC AI Team 1")
    st.write("**분석 기업:** 에이피알")
    st.write("**현재 주차:** 2주차")

st.title("AI 재무 컨설팅 어시스턴트")
st.markdown("---")

company = st.text_input("기업명을 입력하세요", placeholder="예: 에이피알")

if st.button("분석 시작"):
    if not company.strip():
        st.warning("기업명을 입력해주세요")
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
            st.error(f"'{company}' 데이터를 찾을 수 없습니다. 기업명을 확인해주세요.")
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

            st.subheader(f"{company} 연도별 재무 현황")
            st.dataframe(df, use_container_width=True)

            st.subheader("Claude 분석")
            st.write(state["analysis"])

            st.success("분석 완료!")
