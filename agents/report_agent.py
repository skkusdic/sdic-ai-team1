import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fpdf import FPDF
from fpdf.enums import XPos, YPos

FONT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts", "NanumGothic.ttf")


class KoreanPDF(FPDF):
    def __init__(self, company: str = ""):
        super().__init__()
        self.company = company
        self.add_font("NanumGothic", "", FONT_PATH)

    def header(self):
        self.set_font("NanumGothic", size=10)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, f"{self.company} 기업 분석 리포트", align="L",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(200, 200, 200)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)
        self.set_text_color(0, 0, 0)

    def footer(self):
        self.set_y(-15)
        self.set_font("NanumGothic", size=9)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, f"{self.page_no()} 페이지", align="C",
                  new_x=XPos.RIGHT, new_y=YPos.TOP)


def generate_pdf(company: str, financials: dict, analysis: str) -> str:
    pdf = KoreanPDF(company=company)
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # 제목
    pdf.set_font("NanumGothic", size=18)
    pdf.cell(0, 14, f"{company} 기업 분석 리포트", align="C",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    # 1. 재무 데이터 5개년 표
    pdf.set_font("NanumGothic", size=13)
    pdf.cell(0, 10, "1. 5개년 재무 데이터", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)

    if financials:
        col_w = [22, 38, 38, 38]
        headers = ["연도", "매출액(억원)", "영업이익(억원)", "순이익(억원)"]

        # 표 헤더
        pdf.set_fill_color(240, 240, 240)
        pdf.set_font("NanumGothic", size=10)
        for i, h in enumerate(headers):
            pdf.cell(col_w[i], 9, h, border=1, align="C", fill=True,
                     new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.ln()

        # 표 데이터
        for year in sorted(financials.keys()):
            d = financials[year]
            row = [
                str(year),
                f"{d.get('매출액', 0):,}",
                f"{d.get('영업이익', 0):,}",
                f"{d.get('순이익', 0):,}",
            ]
            for i, val in enumerate(row):
                pdf.cell(col_w[i], 9, val, border=1, align="C",
                         new_x=XPos.RIGHT, new_y=YPos.TOP)
            pdf.ln()
    else:
        pdf.set_font("NanumGothic", size=10)
        pdf.cell(0, 8, "  재무 데이터 없음", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(6)

    # 2. Claude 분석
    pdf.set_font("NanumGothic", size=13)
    pdf.cell(0, 10, "2. Claude 분석", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)
    pdf.set_font("NanumGothic", size=10)

    if analysis:
        for line in analysis.split("\n"):
            line = line.strip()
            if line:
                pdf.multi_cell(0, 7, line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.ln(1)
    else:
        pdf.cell(0, 8, "  분석 결과 없음", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf_filename = f"{company}_report.pdf"
    pdf_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), pdf_filename)
    pdf.output(pdf_path)
    return pdf_path


def run_report_agent(state: dict) -> dict:
    company = state.get("company", "기업")
    financials = state.get("financials", {})
    analysis = state.get("analysis", "")

    pdf_path = generate_pdf(company, financials, analysis)
    return {**state, "pdf_path": pdf_path}


def embed_text(text: str) -> list:
    pass  # TODO: 4주차에 OpenAI embeddings로 구현


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    mock_state = {
        "company": "에이피알",
        "financials": {
            2021: {"매출액": 149883, "영업이익": 18234, "순이익": 14102},
            2022: {"매출액": 198210, "영업이익": 24501, "순이익": 19800},
            2023: {"매출액": 241560, "영업이익": 31200, "순이익": 25600},
            2024: {"매출액": 289000, "영업이익": 38900, "순이익": 31200},
            2025: {"매출액": 320000, "영업이익": 42000, "순이익": 34500},
        },
        "analysis": "이 기업의 영업이익률은 13.1%로 안정적인 수익 구조를 유지하고 있습니다.\n"
                    "5개년 매출 성장률은 연평균 약 16.4%로 꾸준한 성장세를 보이고 있습니다.\n"
                    "영업이익은 2021년 대비 2025년 약 2.3배 증가하였으며, 수익성이 개선되는 추세입니다.\n"
                    "순이익률 역시 전반적으로 상승하고 있어 재무 건전성이 양호합니다.",
    }

    print("보고서 생성 시작...")
    result = run_report_agent(mock_state)
    print(f"PDF 생성 완료: {result['pdf_path']}")
    print(f"파일 존재 여부: {os.path.exists(result['pdf_path'])}")
