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
    top3 = search(query, chunks, vectorizer, matrix, k=3)

    excerpts = "\n\n".join(
        f"[{chunk['label']}] (유사도 {score:.4f})\n{chunk['text']}"
        for score, chunk in top3
    )

    prompt = f"""아래 발췌 3개만 사용해서 질문에 한국어로 답하세요.
발췌에 없는 수치나 연도는 절대 추측하지 마세요. 모르면 "정보 부족"이라고 하세요.

발췌:
{excerpts}

질문: {query}

답변:"""

    reply = ask(prompt, max_tokens=400)
    return reply, top3


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
