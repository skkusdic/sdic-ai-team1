import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fpdf import FPDF
from fpdf.enums import XPos, YPos

FONT_CANDIDATES = [
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "NanumGothic.ttf"),
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
]


def _setup_font(pdf: FPDF) -> str:
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            pdf.add_font("KoreanFont", "", path)
            pdf.set_font("KoreanFont", size=16)
            return "KoreanFont"
    pdf.set_font("Helvetica", size=16)
    return "Helvetica"


def embed_text(text: str) -> list:
    pass  # TODO: 4주차에 OpenAI embeddings로 구현


def run_report_agent(state: dict) -> dict:
    company = state.get("company", "기업")
    financials = state.get("financials", {})
    analysis = state.get("analysis", "")

    pdf = FPDF()
    pdf.add_page()
    font_name = _setup_font(pdf)

    pdf.set_font(font_name, size=16)
    pdf.cell(0, 12, f"{company} 기업 분석 리포트", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.ln(6)

    pdf.set_font(font_name, size=12)
    pdf.cell(0, 10, "1. 재무 데이터 요약", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font(font_name, size=10)

    if financials:
        for key, value in list(financials.items())[:10]:
            pdf.cell(0, 8, f"  {key}: {value}"[:80], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    else:
        pdf.cell(0, 8, "  재무 데이터 없음", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(4)
    pdf.set_font(font_name, size=12)
    pdf.cell(0, 10, "2. 분석 결과", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font(font_name, size=10)

    if analysis:
        for line in str(analysis).split("\n"):
            pdf.multi_cell(pdf.epw, 8, f"  {line[:100]}")
    else:
        pdf.cell(0, 8, "  분석 결과 없음", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf_filename = f"{company}_report.pdf"
    pdf_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), pdf_filename)
    pdf.output(pdf_path)

    return {**state, "pdf_path": pdf_path}


if __name__ == "__main__":
    mock_state = {
        "company": "에이피알",
        "financials": {
            "매출액_2023": "1,234,567백만원",
            "영업이익_2023": "123,456백만원",
            "당기순이익_2023": "98,765백만원",
            "매출액_2022": "1,100,000백만원",
            "영업이익_2022": "110,000백만원",
        },
        "analysis": "에이피알은 화장품 및 뷰티 디바이스 전문 기업입니다.\n매출 성장률은 전년 대비 약 12% 증가하였습니다.\n영업이익률은 약 10%로 안정적인 수익성을 보이고 있습니다.",
    }

    print("보고서 생성 시작...")
    result = run_report_agent(mock_state)
    print(f"PDF 생성 완료: {result['pdf_path']}")
    print(f"파일 존재 여부: {os.path.exists(result['pdf_path'])}")
