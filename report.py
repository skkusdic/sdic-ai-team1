import os
import anthropic
from fpdf import FPDF
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def generate_report(company_name: str, financials: dict, analysis: str) -> str:
    """PDF 보고서를 생성하고 파일 경로를 반환한다."""
    pdf = FPDF()
    pdf.add_page()

    # TODO Week 4: 한글 폰트 등록 및 본문 내용 채우기
    # TODO Week 4: 재무 테이블 (financials) 삽입
    # TODO Week 4: Claude 분석 텍스트 (analysis) 삽입

    output_path = f"{company_name}_report.pdf"
    pdf.output(output_path)
    return output_path


def embed_document(text: str) -> list:
    # TODO Week 4: OpenAI embeddings로 RAG 구현 예정
    pass


def _format_report(data: dict) -> str:
    company = data.get("company", "알 수 없음")
    lines = [f"[ {company} 재무 요약 ]"]

    for year_data in data.get("financials", []):
        year = year_data.get("year")
        revenue = year_data.get("revenue")
        operating_profit = year_data.get("operating_profit")
        net_income = year_data.get("net_income")
        lines.append(
            f"{year}년: 매출 {revenue}조 / 영업이익 {operating_profit}조 / 순이익 {net_income}조"
        )

    return "\n".join(lines)


if __name__ == "__main__":
    mock_financials = {
        2022: {"매출액": 302_000_000, "영업이익": 43_000_000, "순이익": 55_000_000},
        2023: {"매출액": 258_000_000, "영업이익":  6_000_000, "순이익": 15_000_000},
        2024: {"매출액": 300_000_000, "영업이익": 32_000_000, "순이익": 34_000_000},
    }
    mock_analysis = "테스트용 분석 텍스트입니다."
    path = generate_report("삼성전자", mock_financials, mock_analysis)
    print(f"PDF 생성 완료: {path}")
