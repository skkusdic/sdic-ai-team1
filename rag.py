import re
from collections import Counter

import numpy as np
from anthropic import Anthropic


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def _build_chunks(financials: dict, company: str) -> list[dict]:
    chunks = []
    years = sorted(financials.items())

    for year, d in years:
        rev, op, net = d["매출액"], d["영업이익"], d["순이익"]
        margin = op / rev * 100 if rev else 0.0
        chunks.append({
            "label": f"{year}년 재무",
            "text": (
                f"{company} {year}년: 매출액 {rev:,}억원, "
                f"영업이익 {op:,}억원, 순이익 {net:,}억원, "
                f"영업이익률 {margin:.1f}%"
            ),
        })

    for i in range(1, len(years)):
        py, pd_ = years[i - 1]
        cy, cd = years[i]
        def chg(curr, prev):
            return (curr - prev) / prev * 100 if prev else 0.0
        chunks.append({
            "label": f"{py}→{cy}년 변화",
            "text": (
                f"{company} {py}→{cy}년 YoY: "
                f"매출액 {chg(cd['매출액'], pd_['매출액']):+.1f}%, "
                f"영업이익 {chg(cd['영업이익'], pd_['영업이익']):+.1f}%, "
                f"순이익 {chg(cd['순이익'], pd_['순이익']):+.1f}%"
            ),
        })

    return chunks


def _tfidf_matrix(docs: list[str]):
    tokenized = [_tokenize(d) for d in docs]
    vocab: dict[str, int] = {}
    for tokens in tokenized:
        for t in tokens:
            vocab.setdefault(t, len(vocab))

    def tf_vec(tokens: list[str]) -> np.ndarray:
        vec = np.zeros(len(vocab))
        if not tokens:
            return vec
        counts = Counter(tokens)
        for t, cnt in counts.items():
            if t in vocab:
                vec[vocab[t]] = cnt / len(tokens)
        return vec

    return [tf_vec(t) for t in tokenized]


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom else 0.0


def retrieve(query: str, financials: dict, company: str, top_k: int = 3) -> list[tuple[float, dict]]:
    chunks = _build_chunks(financials, company)
    docs = [c["text"] for c in chunks] + [query]
    vecs = _tfidf_matrix(docs)
    q_vec = vecs[-1]
    scored = sorted(
        zip([_cosine(q_vec, v) for v in vecs[:-1]], chunks),
        key=lambda x: -x[0],
    )
    return scored[:top_k]


def answer_with_rag(query: str, financials: dict, company: str) -> tuple[list, str]:
    top = retrieve(query, financials, company, top_k=3)
    context = "\n".join(item["text"] for _, item in top)
    client = Anthropic()
    resp = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": (
                f"다음 재무 정보를 참고하여 질문에 답변하세요.\n\n"
                f"[참고 문서]\n{context}\n\n"
                f"[질문] {query}\n"
                "한국어로 간결하게 답변해 주세요."
            ),
        }],
    )
    return top, resp.content[0].text
