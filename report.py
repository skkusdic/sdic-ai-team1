import os
import anthropic
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def generate_report(data: dict) -> str:
    # TODO Week 4: fpdf2로 PDF 생성 예정
    pass


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
    mock_data = {
        "company": "삼성전자",
        "financials": [
            {"year": 2022, "revenue": 302, "operating_profit": 43, "net_income": 55},
            {"year": 2023, "revenue": 258, "operating_profit": 6,  "net_income": 15},
            {"year": 2024, "revenue": 300, "operating_profit": 32, "net_income": 34},
        ],
    }
    print(_format_report(mock_data))
