"""Report Lead — RAG 모듈 (사업보고서 스타일 RAG).

파이프라인:
  financials dict → 6단락 텍스트 → TF-IDF 벡터화 → data/{company}_rag.pkl 캐싱
  질문 → 코사인 유사도 검색(top-3) → Claude 답변 (발췌만 사용, 환각 차단)
"""
import os
import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from dotenv import load_dotenv

from claude_client import ask

load_dotenv()

_DATA_DIR = "data"


# ── 1. 재무 데이터 → 6단락 텍스트 ─────────────────────────────────────────

def _financials_to_paragraphs(company: str, financials: dict) -> list[str]:
    """연도별 단락 5개 + 종합 단락 1개, 총 6개 반환."""
    paragraphs = []
    sorted_years = sorted(financials.keys(), key=lambda y: int(y))

    for year in sorted_years:
        m = financials[year]
        rev = m.get("매출액", 0) // 100
        op = m.get("영업이익", 0) // 100
        net = m.get("순이익", 0) // 100
        margin = (m.get("영업이익", 0) / m.get("매출액", 1) * 100) if m.get("매출액") else 0

        paragraphs.append(
            f"{company}의 {year}년 재무 실적: 매출액 {rev:,}억원, "
            f"영업이익 {op:,}억원, 순이익 {net:,}억원. "
            f"영업이익률은 {margin:.1f}%였다."
        )

    # 종합 단락
    first_year = sorted_years[0]
    last_year = sorted_years[-1]
    first_rev = financials[first_year].get("매출액", 0) // 100
    last_rev = financials[last_year].get("매출액", 0) // 100
    rev_change = ((last_rev - first_rev) / first_rev * 100) if first_rev else 0

    best_year = max(sorted_years, key=lambda y: financials[y].get("영업이익", 0))
    worst_year = min(sorted_years, key=lambda y: financials[y].get("영업이익", 0))

    paragraphs.append(
        f"{company} {first_year}~{last_year}년 종합: "
        f"매출액은 {first_rev:,}억원에서 {last_rev:,}억원으로 {rev_change:+.1f}% 변화했다. "
        f"영업이익이 가장 높았던 해는 {best_year}년, "
        f"가장 낮았던 해는 {worst_year}년이다."
    )

    return paragraphs


# ── 2. 인덱스 빌드 / 캐시 로드 ────────────────────────────────────────────

def build_index(company: str, financials: dict) -> tuple[list[str], TfidfVectorizer, np.ndarray]:
    """캐시(.pkl) 있으면 로드, 없으면 TF-IDF 학습 후 저장."""
    os.makedirs(_DATA_DIR, exist_ok=True)
    pkl_path = os.path.join(_DATA_DIR, f"{company}_rag.pkl")

    if os.path.exists(pkl_path):
        print(f"[RAG] 캐시 로드: {pkl_path}")
        return joblib.load(pkl_path)

    print(f"[RAG] TF-IDF 벡터화 중...")
    chunks = _financials_to_paragraphs(company, financials)
    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
    matrix = vectorizer.fit_transform(chunks)
    joblib.dump((chunks, vectorizer, matrix), pkl_path)
    print(f"[RAG] 저장 완료: {pkl_path} (chunk {len(chunks)}개)")
    return chunks, vectorizer, matrix


# ── 3. 코사인 유사도 검색 ──────────────────────────────────────────────────

def search(
    query: str,
    chunks: list[str],
    vectorizer: TfidfVectorizer,
    matrix: np.ndarray,
    k: int = 3,
) -> list[tuple[float, dict]]:
    """질문과 가장 유사한 chunk k개를 (점수, {"label": ..., "text": ...}) 리스트로 반환."""
    query_vec = vectorizer.transform([query])
    scores = cosine_similarity(query_vec, matrix)[0]
    top_indices = np.argsort(scores)[::-1][:k]
    return [
        (float(scores[i]), {"label": f"발췌 {rank+1}", "text": chunks[i]})
        for rank, i in enumerate(top_indices)
    ]


# ── 4. 전체 파이프라인: 질문 → Claude 답변 ────────────────────────────────

def answer(query: str, company: str, financials: dict) -> tuple[str, list[tuple[str, float]]]:
    """RAG 파이프라인 실행. (Claude 답변, top-3 발췌 리스트) 반환."""
    if not financials:
        return "데이터를 찾을 수 없습니다.", []

    chunks, vectorizer, matrix = build_index(company, financials)
    k = min(len(chunks), 6)
    top3 = search(query, chunks, vectorizer, matrix, k=k)

    excerpts = "\n\n".join(
        f"[{chunk['label']}] (유사도 {score:.4f})\n{chunk['text']}"
        for score, chunk in top3
    )

    prompt = f"""아래 발췌를 사용해서 질문에 한국어로 답하세요.
발췌에 없는 수치나 연도는 절대 추측하지 마세요. 모르면 "정보 부족"이라고 하세요.

발췌:
{excerpts}

질문: {query}

답변:"""

    reply = ask(prompt, max_tokens=400)
    return reply, top3


# ── 5. 사업보고서 원문 요약 ────────────────────────────────────────────────

_MAX_REPORT_CHARS = 15_000  # claude-haiku-4-5 비용 제어용 상한


def _financials_summary_text(company: str, financials: dict) -> str:
    """재무 데이터를 프롬프트에 삽입할 요약 텍스트로 변환."""
    if not financials:
        return ""
    lines = []
    for year, d in sorted(financials.items()):
        rev = d.get("매출액", 0)
        op = d.get("영업이익", 0)
        net = d.get("순이익", 0)
        margin = round(op / rev * 100, 1) if rev else 0
        lines.append(
            f"  {year}년: 매출 {rev:,}억원 / 영업이익 {op:,}억원 (이익률 {margin}%) / 순이익 {net:,}억원"
        )
    return f"{company} 재무 실적 ({min(financials)}~{max(financials)}년):\n" + "\n".join(lines)


def summarize_business_report(text: str, company: str, financials: dict = None) -> str:
    """
    DART 사업보고서 '사업의 내용' 텍스트를 받아 핵심 요약문 반환.
    financials가 있으면 재무 수치와 연계한 통합 분석 수행.
    텍스트가 없으면 빈 문자열 반환.
    """
    if not text or not text.strip():
        return ""

    truncated = text[:_MAX_REPORT_CHARS]
    if len(text) > _MAX_REPORT_CHARS:
        truncated += "\n\n(이하 생략)"

    prompt = (
        f"아래는 {company}의 DART 사업보고서 '사업의 내용' 섹션 원문입니다.\n"
        "발췌에 없는 내용은 절대 추측하지 말고, 주어진 정보만 근거로 분석하세요.\n\n"
        "다음 형식으로 한국어로 작성하세요.\n\n"
        "【작성 규칙】\n"
        "- 문체: 반드시 '~합니다' 체로 통일 (예: '운영하고 있습니다.', '차지하고 있습니다.')\n"
        "- 중요한 수치·브랜드명·키워드는 **굵게** 표시 (예: **47%**, **에이피알**, **K뷰티**)\n"
        "- 각 항목은 하나의 문단으로 작성: 원문 내용이 충분하면 2문장, 내용이 적으면 1문장으로 구성\n"
        "- 문단 내 문장을 줄바꿈 없이 이어서 작성 (목록·불릿 형식 금지)\n"
        "- 아래 번호와 항목명 형식을 반드시 그대로 출력할 것 (예: '1. 주요 사업 영역:')\n"
        "- 원문에서 해당 항목에 대한 내용을 찾을 수 없으면 그 항목 자체를 출력하지 말 것\n\n"
        "1. 주요 사업 영역: 이 기업이 영위하는 핵심 사업 분야와 그 비중\n"
        "2. 핵심 제품·서비스: 대표 제품/서비스의 특징과 차별점\n"
        "3. 고객 및 시장: 주요 고객층, 타깃 시장, 유통 채널\n"
        "4. 성장 전략: 향후 사업 확장 계획 및 핵심 전략 방향\n\n"
        f"[원문]\n{truncated}\n\n"
        "위 정보만 근거로 분석하세요."
    )

    return ask(prompt, max_tokens=1200)


# ── app.py 호환 별칭 ──────────────────────────────────────────────────────
retrieve = search

def answer_with_rag(query: str, financials: dict, company: str):
    """app.py 호출 규약(query, financials, company) 대응 래퍼. (top3, reply) 순서로 반환."""
    reply, top3 = answer(query, company, financials)
    return top3, reply


# ── 단독 실행 테스트 ──────────────────────────────────────────────────────

if __name__ == "__main__":
    from data import get_financials

    company = "에이피알"
    financials = get_financials(company)

    if not financials:
        print("재무 데이터 없음 — data.py 확인 필요")
    else:
        print(f"=== {company} RAG 테스트 ===\n")

        reply, top3 = answer("2023년 수익성은?", company, financials)
        print("[ 검색된 발췌 ]")
        for score, chunk in top3:
            print(f"  [{chunk['label']}] 유사도 {score:.4f} | {chunk['text'][:70]}...")
        print(f"\n[ Claude 답변 ]\n{reply}")

        print("\n--- 캐시 재로드 테스트 ---")
        reply2, _ = answer("영업이익이 가장 높은 해는?", company, financials)
        print(f"[ Claude 답변 ]\n{reply2}")
