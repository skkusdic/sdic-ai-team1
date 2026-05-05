import streamlit as st
import pandas as pd
import time

st.set_page_config(page_title="AI 재무 컨설팅 어시스턴트", layout="wide")

with st.sidebar:
    st.header("팀 정보")
    st.write("**팀명:** SDIC AI Team 1")
    st.write("**분석 기업:** 삼성전자")
    st.write("**현재 주차:** 2주차")

st.title("AI 재무 컨설팅 어시스턴트")
st.markdown("---")

company = st.text_input("기업명을 입력하세요", placeholder="예: 삼성전자")

if st.button("분석 시작"):
    if not company.strip():
        st.warning("기업명을 입력해주세요")
    else:
        with st.spinner("데이터 불러오는 중..."):
            time.sleep(1.5)

        df = pd.DataFrame(
            {
                "연도": [2022, 2023, 2024],
                "매출액 (억원)": [3_023_514, 2_589_355, 3_002_454],
                "영업이익 (억원)": [433_766, 65_670, 328_548],
                "순이익 (억원)": [554_506, 154_871, 344_157],
            }
        )
        df = df.set_index("연도")

        st.subheader(f"{company} 재무 현황 (2022~2024)")
        st.dataframe(df, use_container_width=True)
        st.success("분석 완료!")
