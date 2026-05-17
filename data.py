import os
import sqlite3
import requests
from datetime import datetime

import dart_fss as dart
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv(override=True)

DB_PATH = "financials.db"
DART_API_KEY = os.environ["DART_API_KEY"]
DART_ENDPOINT = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"

dart.set_api_key(DART_API_KEY)

_corp_list_cache = None

_REVENUE_LABELS = {"매출액", "영업수익", "수익(매출액)"}
_OPERATING_LABELS = {"영업이익", "영업이익(손실)", "영업손실"}
_NET_LABELS = {"당기순이익", "당기순이익(손실)", "당기순손실"}

# 영문 입력 → 한국어 회사명 변환 (대소문자 무시)
_EN_TO_KR = {
    "apr": "에이피알",
    "samsung": "삼성전자",
    "kakao": "카카오",
    "hyundai": "현대자동차",
    "kia": "기아",
    "lg": "LG전자",
    "sk hynix": "SK하이닉스",
    "hynix": "SK하이닉스",
    "naver": "NAVER",
    "kt": "케이티",
    "posco": "POSCO홀딩스",
    "lotte": "롯데쇼핑",
    "celltrion": "셀트리온",
    "krafton": "크래프톤",
    "ncsoft": "엔씨소프트",
    "netmarble": "넷마블",
}

# DART에 영문/약어로 등록된 회사 한글 별칭
_CORP_ALIASES = {
    "네이버": "NAVER",
    "케이티": "KT",
    "에스케이텔레콤": "SK텔레콤",
    "엘지전자": "LG전자",
    "엘지이노텍": "LG이노텍",
    "엘지화학": "LG화학",
    "엘지에너지솔루션": "LG에너지솔루션",
    "엘지생활건강": "LG생활건강",
    "엘지유플러스": "LG유플러스",
    "에스케이하이닉스": "SK하이닉스",
    "에스케이이노베이션": "SK이노베이션",
    "현대차": "현대자동차",
    "기아차": "기아",
    "포스코": "POSCO홀딩스",
    "비비큐": "BBQ",
}


def _get_corp_list():
    global _corp_list_cache
    if _corp_list_cache is None:
        _corp_list_cache = dart.get_corp_list()
    return _corp_list_cache


def _find_corp_code(company_name: str) -> str:
    corp_list = _get_corp_list()
    raw = company_name.strip()
    # 영문 입력이면 한국어로 변환
    raw = _EN_TO_KR.get(raw.lower(), raw)
    no_space = raw.replace(" ", "")
    candidates = [raw]
    if no_space != raw:
        candidates.append(no_space)
    if no_space in _CORP_ALIASES:
        candidates.append(_CORP_ALIASES[no_space])

    for cand in candidates:
        results = corp_list.find_by_corp_name(cand, exactly=True) or []
        listed = [r for r in results if r.stock_code]
        if listed:
            return listed[0].corp_code
        if results:
            return results[0].corp_code

    for cand in candidates:
        results = corp_list.find_by_corp_name(cand, exactly=False) or []
        listed = [r for r in results if r.stock_code]
        pool = listed if listed else results
        if pool:
            return min(pool, key=lambda r: len(r.corp_name)).corp_code

    return ""


def _extract_year(corp_code: str, year: int, fs_div: str) -> dict:
    """fnlttSinglAcntAll API로 단년 손익 추출. fs_div: 'CFS' 또는 'OFS'. 단위: 억원."""
    params = {
        "crtfc_key": DART_API_KEY,
        "corp_code": corp_code,
        "bsns_year": str(year),
        "reprt_code": "11011",
        "fs_div": fs_div,
    }
    try:
        resp = requests.get(DART_ENDPOINT, params=params, timeout=10).json()
    except Exception:
        return {}

    items = resp.get("list", [])
    data = {}
    for item in items:
        if item.get("sj_div") not in ("IS", "CIS"):
            continue
        nm = item.get("account_nm", "").strip()
        amt = item.get("thstrm_amount", "").replace(",", "")
        if not amt or amt == "-":
            continue
        try:
            val = int(amt) // 100_000_000
        except (ValueError, TypeError):
            continue
        if nm in _REVENUE_LABELS and "매출액" not in data:
            data["매출액"] = val
        elif nm in _OPERATING_LABELS and "영업이익" not in data:
            data["영업이익"] = val
        elif nm in _NET_LABELS and "순이익" not in data:
            data["순이익"] = val
    return data


def _fetch_from_dart(company_name: str) -> dict:
    corp_code = _find_corp_code(company_name)
    if not corp_code:
        return {}

    result = {}
    for year in range(2020, 2026):
        year_data = _extract_year(corp_code, year, "CFS")
        if not year_data or not {"매출액", "영업이익", "순이익"}.issubset(year_data):
            ofs = _extract_year(corp_code, year, "OFS")
            for k, v in ofs.items():
                year_data.setdefault(k, v)
        if {"매출액", "영업이익", "순이익"}.issubset(year_data):
            result[year] = year_data

    return result


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS financials (
            company  TEXT,
            year     INTEGER,
            매출액   INTEGER,
            영업이익 INTEGER,
            순이익   INTEGER,
            PRIMARY KEY (company, year)
        )
    """)


def _save_to_db(company_name: str, data: dict) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        _init_db(conn)
        for year, m in data.items():
            conn.execute(
                "INSERT OR REPLACE INTO financials (company, year, 매출액, 영업이익, 순이익) VALUES (?, ?, ?, ?, ?)",
                (company_name, int(year), m["매출액"], m["영업이익"], m["순이익"]),
            )
        conn.commit()


def _load_from_db(company_name: str) -> dict:
    if not os.path.exists(DB_PATH):
        return {}
    with sqlite3.connect(DB_PATH) as conn:
        _init_db(conn)
        rows = conn.execute(
            "SELECT year, 매출액, 영업이익, 순이익 FROM financials WHERE company = ? ORDER BY year",
            (company_name,),
        ).fetchall()
    return {
        str(year): {"매출액": rev, "영업이익": op, "순이익": net}
        for year, rev, op, net in rows
    }


def get_financials(company_name: str) -> dict:
    """6개년(2020~2025) 재무 데이터. 키는 문자열 연도. 단위: 억원."""
    cached = _load_from_db(company_name)
    if cached:
        return cached

    raw = _fetch_from_dart(company_name)
    if not raw:
        return {}

    data = {str(year): metrics for year, metrics in raw.items()}
    _save_to_db(company_name, data)
    return data


# ── 사업보고서 원문 텍스트 추출 ────────────────────────────────────────────

def _html_to_text(html: str) -> str:
    """BeautifulSoup으로 HTML → 순수 텍스트 변환."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return " ".join(soup.get_text(separator=" ").split())


def _fetch_business_section(corp_code: str, year: int) -> str:
    """dart-fss로 사업보고서에서 '사업의 내용' 섹션 텍스트 추출."""
    try:
        result = dart.filings.search(
            corp_code=corp_code,
            bgn_de=f"{year}0101",
            end_de=f"{year}1231",
            pblntf_ty="A",   # 사업보고서
            page_count=5,
        )
    except Exception:
        return ""

    if not result or len(result) == 0:
        return ""

    report = result[0]
    try:
        pages = report.pages
    except Exception:
        return ""

    # "사업의 내용" 타이틀 페이지 찾기 (부분 매칭)
    target_pages = [
        p for p in pages
        if "사업" in p.title and "내용" in p.title
    ]

    # 못 찾으면 전체 페이지에서 앞 3개 fallback
    if not target_pages:
        target_pages = pages[:3]

    texts = []
    for page in target_pages[:5]:  # 최대 5페이지만 처리
        try:
            texts.append(_html_to_text(page.html))
        except Exception:
            continue

    return "\n\n".join(texts)


def get_business_report_text(company_name: str, year: int = None) -> str:
    """
    DART 사업보고서 '사업의 내용' 섹션 텍스트 반환.
    SQLite 캐시 우선, 없으면 DART에서 파싱 후 저장.
    year 미지정 시 직전 연도 사용.
    """
    from db import init_db, save_business_report, load_business_report

    if year is None:
        year = datetime.now().year - 1

    init_db()

    cached = load_business_report(company_name, year, "사업의내용")
    if cached:
        return cached

    corp_code = _find_corp_code(company_name)
    if not corp_code:
        return ""

    text = _fetch_business_section(corp_code, year)

    if not text:
        return ""

    save_business_report(company_name, year, "사업의내용", text)
    return text


if __name__ == "__main__":
    import sys
    import time
    sys.stdout.reconfigure(encoding="utf-8")

    for name in ["에이피알", "카카오", "asdfasdf"]:
        t0 = time.time()
        d = get_financials(name)
        elapsed = time.time() - t0
        if not d:
            print(f"[{name}] no data ({elapsed:.1f}s)")
            continue
        print(f"[{name}] {len(d)}개년 ({elapsed:.1f}s)")
        for y, m in sorted(d.items()):
            print(f"  {y}: {m}")
