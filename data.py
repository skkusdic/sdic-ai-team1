import os
import sqlite3
import requests
from datetime import datetime

import dart_fss as dart
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from claude_client import ask

load_dotenv(override=True)

DB_PATH = "financials.db"
DART_API_KEY = os.environ["DART_API_KEY"]
DART_ENDPOINT = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"

dart.set_api_key(DART_API_KEY)

_corp_list_cache = None

_REVENUE_LABELS   = {"매출액", "영업수익", "수익(매출액)", "매출"}
_OPERATING_LABELS = {"영업이익", "영업이익(손실)", "영업손실"}
_NET_LABELS       = {"당기순이익", "당기순이익(손실)", "당기순손실",
                     "연결당기순이익", "연결당기순이익(손실)", "연결당기순손실",
                     "당기순이익(손실)(A)", "당기순이익(A)"}
_COGS_LABELS      = {"매출원가", "제품매출원가", "상품매출원가", "원가합계", "영업원가", "매출원가(제품+상품)"}
_GROSS_LABELS     = {"매출총이익", "매출총손익", "매출이익"}
_SGA_LABELS       = {"판매비와관리비", "판매비와일반관리비", "판매관리비"}


def _get_corp_list():
    global _corp_list_cache
    if _corp_list_cache is None:
        _corp_list_cache = dart.get_corp_list()
    return _corp_list_cache


def _has_english(text: str) -> bool:
    return any(c.isascii() and c.isalpha() for c in text)


def _korean_part(text: str) -> str:
    """한국어 글자만 추출해서 반환."""
    return "".join(c for c in text if "가" <= c <= "힣" or "ㄱ" <= c <= "ㅎ")


def _normalize_name(company_name: str) -> str:
    """영문/혼합 입력이면 Claude로 DART 등록 회사명으로 변환, 한국어면 그대로 반환."""
    if not _has_english(company_name):
        return company_name
    from claude_client import ask
    result = ask(
        f"다음은 한국 기업명입니다: '{company_name}'\n"
        "이 기업의 DART(금융감독원 전자공시시스템) 등록 정식 회사명을 한국어로만 답하세요.\n"
        "반드시 회사명만 출력하고, 설명·부연·거절 문장은 절대 쓰지 마세요.\n"
        "모르면 한국어 부분만 붙여서 출력하세요.",
        max_tokens=30,
    ).strip()
    if not result or len(result) > 20 or not any("가" <= c <= "힣" for c in result):
        return company_name
    return result


# DART 공식명이 영문인 회사: 한국어 입력 → 영문 DART명 사전
_DART_ALIAS = {
    "네이버": "NAVER",
    "카카오뱅크": "카카오뱅크",   # 이미 한국어 — 이건 그대로
    "에스케이하이닉스": "SK하이닉스",
}


def _find_corp_code(company_name: str) -> str:
    corp_list = _get_corp_list()
    raw = company_name.strip()

    # 별칭 사전 우선 적용 (DART 공식명이 영문인 케이스 대응)
    if raw in _DART_ALIAS:
        raw = _DART_ALIAS[raw]

    normalized = _normalize_name(raw)

    def _strip_suffix(name: str) -> str:
        for suffix in ["주식회사", "(주)", " 주식회사"]:
            name = name.replace(suffix, "")
        return name.strip()

    def _build_candidates(*names) -> list:
        out = []
        for n in names:
            out += [n, _strip_suffix(n), n.replace(" ", ""), _strip_suffix(n).replace(" ", "")]
        return list(dict.fromkeys(out))

    candidates = _build_candidates(normalized, raw, _korean_part(raw))

    for cand in candidates:
        results = corp_list.find_by_corp_name(cand, exactly=True) or []
        listed = [r for r in results if r.stock_code]
        if listed:
            return listed[0].corp_code
        if results:
            return results[0].corp_code

    # 정확 일치 실패 — 한국어 약칭도 Claude로 DART 공식명 변환 시도
    # (예: "현대차" → "현대자동차", "기아차" → "기아", "네이버" → "NAVER")
    if not _has_english(raw):
        try:
            official = ask(
                f"'{raw}'의 DART(금융감독원 전자공시시스템) 등록 정식 회사명을 한국어로만 답하세요.\n"
                "회사명만 출력하세요. 예시: '현대자동차', 'LG전자', '삼성전자'",
                max_tokens=30,
            ).strip()
            if official and official != raw and any("가" <= c <= "힣" for c in official) and len(official) < 25:
                for cand in _build_candidates(official):
                    results = corp_list.find_by_corp_name(cand, exactly=True) or []
                    listed = [r for r in results if r.stock_code]
                    if listed:
                        return listed[0].corp_code
                    if results:
                        return results[0].corp_code
                # 공식명도 후보에 추가해 부분 검색에 활용
                candidates = _build_candidates(normalized, raw, _korean_part(raw), official)
        except Exception:
            pass

    for cand in candidates:
        results = corp_list.find_by_corp_name(cand, exactly=False) or []
        listed = [r for r in results if r.stock_code]
        pool = listed if listed else results
        if pool:
            # 쿼리 문자열로 시작하는 상장사 우선 — "LG" 검색 시 "㈜LG"(지주사)보다
            # "LG전자"가 먼저 선택되도록 방지
            starts = [r for r in pool if r.corp_name.startswith(cand)]
            target = starts if starts else pool
            return min(target, key=lambda r: len(r.corp_name)).corp_code

    return ""


def _extract_year(corp_code: str, year: int, fs_div: str) -> dict:
    """fnlttSinglAcntAll API로 단년 손익 추출. fs_div: 'CFS' 또는 'OFS'. 단위: 백만원."""
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
            val = int(amt) // 1_000_000
        except (ValueError, TypeError):
            continue
        if nm in _REVENUE_LABELS and "매출액" not in data:
            data["매출액"] = val
        elif nm in _OPERATING_LABELS and "영업이익" not in data:
            data["영업이익"] = val
        elif nm in _NET_LABELS and "순이익" not in data:
            data["순이익"] = val
        elif nm in _COGS_LABELS and "매출원가" not in data:
            data["매출원가"] = val
        elif nm in _GROSS_LABELS and "매출총이익" not in data:
            data["매출총이익"] = val
        elif nm in _SGA_LABELS and "판관비" not in data:
            data["판관비"] = val
    return data


def _fetch_from_dart(company_name: str) -> dict:
    corp_code = _find_corp_code(company_name)
    if not corp_code:
        return {}

    _optional = {"매출원가", "매출총이익", "판관비"}
    result = {}
    for year in range(2021, 2026):
        year_data = _extract_year(corp_code, year, "OFS")  # 별도 우선 (DART 기본 표시 기준)
        # 필수 컬럼 부족 또는 선택 컬럼 하나라도 없으면 CFS로 보완
        if (not year_data
                or not {"매출액", "영업이익", "순이익"}.issubset(year_data)
                or not _optional.issubset(year_data)):
            cfs = _extract_year(corp_code, year, "CFS")
            for k, v in cfs.items():
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
        year: {"매출액": rev, "영업이익": op, "순이익": net}
        for year, rev, op, net in rows
    }


def get_financials(company_name: str) -> dict:
    """5개년(2021~2025) 재무 데이터. 키는 정수 연도. 단위: 백만원."""
    from db import init_db as _db_init, load_financials as _db_load, save_financials as _db_save
    _db_init()

    # data_version=2 = OFS + 새 컬럼 완비 데이터만 신뢰
    cached = _db_load(company_name)
    if cached:
        cached_years = set(cached.keys())
        local_years  = set(_load_from_db(company_name).keys())
        if cached_years != local_years:          # 연도 불일치 시 동기화
            _save_to_db(company_name, cached)
        return cached

    # version=0 포함 구버전 캐시는 무시하고 DART 직접 재수집
    # (migration 경로로 3컬럼 데이터가 version=2로 저장되는 버그 방지)
    raw = _fetch_from_dart(company_name)
    if not raw:
        # DART 실패 시에만 구버전 data fallback
        old = _load_from_db(company_name)
        return old if old else {}

    _db_save(company_name, raw)        # data/sdic.db (Text2SQL용, version=2)
    _save_to_db(company_name, raw)     # financials.db (app.py 사이드바용)
    return raw


# ── 웹 뉴스 검색 ────────────────────────────────────────────────────────────

def search_company_news(company: str, extra_keywords: str = "", max_results: int = 5) -> list[str]:
    """
    DuckDuckGo로 기업 관련 최신 뉴스 헤드라인·요약 검색.
    API 키 불필요. 실패 시 빈 리스트 반환.
    반환: ["[날짜] 제목: 요약", ...]
    """
    try:
        from duckduckgo_search import DDGS
        from bs4 import BeautifulSoup as _BS

        query = f"{company} {extra_keywords}".strip() if extra_keywords else f"{company} 실적 사업 이슈"
        with DDGS() as ddgs:
            raw = list(ddgs.news(query, max_results=max_results, region="kr-kr"))

        snippets: list[str] = []
        for r in raw:
            title = _BS(r.get("title", ""), "html.parser").get_text().strip()
            body  = _BS(r.get("body",  ""), "html.parser").get_text().strip()[:200]
            date  = r.get("date", "")[:10]   # YYYY-MM-DD
            if title:
                snippets.append(f"[{date}] {title}" + (f": {body}" if body else ""))
        return snippets
    except Exception:
        return []


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


# ── DCF 입력값 수집 ──────────────────────────────────────────────────────

def _fetch_statements_raw(corp_code: str, year: int, fs_div: str) -> list:
    """fnlttSinglAcntAll API 원시 항목 리스트 반환. 실패 시 빈 리스트."""
    params = {
        "crtfc_key": DART_API_KEY,
        "corp_code": corp_code,
        "bsns_year": str(year),
        "reprt_code": "11011",
        "fs_div": fs_div,
    }
    try:
        resp = requests.get(DART_ENDPOINT, params=params, timeout=15).json()
        return resp.get("list", [])
    except Exception:
        return []


def _parse_item_amount(item: dict) -> int | None:
    """DART 항목의 당기 금액을 억원 단위 정수로 파싱. 없으면 None."""
    amt = item.get("thstrm_amount", "").replace(",", "").strip()
    if not amt or amt == "-":
        return None
    try:
        return int(int(amt) / 100_000_000)
    except (ValueError, TypeError):
        return None


def _match_account(items: list, sj_divs: tuple, candidates: list) -> int | None:
    """items에서 sj_div + account_nm 후보 매칭. 정확 일치 → 부분 포함 순으로 시도."""
    # 1단계: 정확 일치
    for cand in candidates:
        for item in items:
            if item.get("sj_div") not in sj_divs:
                continue
            if item.get("account_nm", "").strip() == cand:
                val = _parse_item_amount(item)
                if val is not None:
                    return val
    # 2단계: 부분 포함 (회사별 계정명 표기 차이 대응)
    for cand in candidates:
        for item in items:
            if item.get("sj_div") not in sj_divs:
                continue
            nm = item.get("account_nm", "").strip().replace(" ", "")
            key = cand.replace(" ", "")
            if key in nm or nm in key:
                val = _parse_item_amount(item)
                if val is not None:
                    return val
    return None


def _find_corp_obj(company_name: str):
    """회사명으로 DART 기업 객체 반환. 없으면 None.

    순서: 정확 일치 → Claude 공식명 변환 + 정확 일치 → 부분 일치.
    부분 일치를 Claude 변환 이전에 하면 약칭이 엉뚱한 기업과 매칭될 수 있어
    반드시 정확 일치 실패 후에만 부분 일치를 시도한다.
    """
    corp_list = _get_corp_list()
    raw = company_name.strip()

    # 별칭 사전 우선 적용 (_find_corp_code 와 동일 로직)
    if raw in _DART_ALIAS:
        raw = _DART_ALIAS[raw]

    def _exact(name: str):
        for cand in [name, name.replace(" ", "")]:
            results = corp_list.find_by_corp_name(cand, exactly=True) or []
            listed = [r for r in results if r.stock_code]
            if listed:
                return listed[0]
            if results:
                return results[0]
        return None

    def _partial(name: str):
        for cand in [name, name.replace(" ", "")]:
            results = corp_list.find_by_corp_name(cand, exactly=False) or []
            listed = [r for r in results if r.stock_code]
            pool = listed if listed else results
            if pool:
                return min(pool, key=lambda r: len(r.corp_name))
        return None

    # 1단계: 정확 일치
    result = _exact(raw)
    if result:
        return result

    # 2단계: Claude로 DART 공식명 변환 후 정확 일치 재시도 (영문·한국어 약칭 모두)
    official = raw
    try:
        converted = ask(
            f"'{raw}'의 DART(금융감독원 전자공시시스템) 등록 정식 회사명을 알려주세요. "
            "정식 회사명만 답하고 다른 말은 절대 쓰지 마세요.",
            max_tokens=30,
        ).strip()
        if converted and converted != raw:
            # "주식회사", "(주)", "(유)" 등 법인 접미사 제거 후 추가 후보 생성
            _suffixes = ["주식회사", "(주)", "(유)", "(합)", "㈜"]
            _prefixes = ["주식회사 "]
            stripped = converted
            for s in _suffixes:
                stripped = stripped.replace(s, "").strip()
            for p in _prefixes:
                if stripped.startswith(p):
                    stripped = stripped[len(p):].strip()

            official = converted
            for cand in dict.fromkeys([converted, stripped]):
                if not cand or cand == raw:
                    continue
                result = _exact(cand)
                if result:
                    print(f"[_find_corp_obj] '{raw}' → '{cand}' 으로 변환 후 검색")
                    return result
            official = stripped or converted  # 부분 일치용은 접미사 제거된 이름 사용
    except Exception:
        pass

    # 3단계: 부분 일치 (공식명 기준 — 변환 성공 시 공식명, 아니면 원본)
    return _partial(official)


def _fetch_shares(corp_code: str) -> dict:
    """DART 주식 수 조회. bsns_year 포함/미포함 두 번 시도. 실패 시 None 반환."""
    empty = {"shares_outstanding": None, "treasury_shares": None, "common_shares": None, "source_note": "조회실패"}
    base_year = datetime.now().year - 1

    def _to_int(val: str) -> int | None:
        v = val.replace(",", "").strip()
        return int(v) if v.lstrip("-").isdigit() else None

    # reprt_code 11011 = 사업보고서 (필수 파라미터)
    for year in [base_year, base_year - 1]:
        try:
            resp = requests.get(
                "https://opendart.fss.or.kr/api/stockTotqySttus.json",
                params={"crtfc_key": DART_API_KEY, "corp_code": corp_code,
                        "bsns_year": str(year), "reprt_code": "11011"},
                timeout=10,
            ).json()
            items = resp.get("list", [])
            if not items:
                continue
            # 보통주 행 우선, 없으면 첫 번째 행
            row = next((r for r in items if r.get("se") == "보통주"), items[0])
            treasury = _to_int(row.get("tesstk_co", ""))
            distb    = _to_int(row.get("distb_stock_co", ""))
            issued   = _to_int(row.get("istc_totqy", ""))
            # 유통주식수(자기주식 차감) 우선; 없거나 0이면 발행주식총수 fallback
            if distb is not None and distb > 0:
                outstanding = distb
                note = "유통주식수(자기주식차감, 보통주)"
            else:
                outstanding = issued
                note = "발행주식총수(자기주식미차감, 보통주)"
            return {
                "shares_outstanding": outstanding,
                "treasury_shares":    treasury,
                "common_shares":      distb,
                "source_note":        note,
            }
        except Exception:
            continue
    return empty


def get_current_price(stock_code: str) -> dict | None:
    """
    FinanceDataReader로 현재 주가 조회.

    Args:
        stock_code: KRX 종목코드 (예: "278470")
    Returns:
        {"current_price": int, "date": str} or None (조회 실패 시)
    """
    if not stock_code:
        return None
    try:
        import FinanceDataReader as fdr
        df = fdr.DataReader(stock_code)
        if df is None or df.empty:
            return None
        last_row = df.iloc[-1]
        return {
            "current_price": int(last_row["Close"]),
            "date": str(df.index[-1].date()),
        }
    except Exception as e:
        print(f"[get_current_price] 주가 조회 실패 ({stock_code}): {e}")
        return None


def calculate_beta(stock_code: str, period_years: int = 2) -> dict | None:
    """
    KOSPI 대비 일간 수익률 회귀로 beta 계산.

    Args:
        stock_code: KRX 종목코드 (예: "278470")
        period_years: 분석 기간 (기본 2년)
    Returns:
        {"beta": float, "period_years": int, "index": str, "method": str} or None
    """
    if not stock_code:
        return None
    try:
        import FinanceDataReader as fdr
        import numpy as np
        from datetime import datetime, timedelta

        end   = datetime.today()
        start = end - timedelta(days=period_years * 365)

        stock = fdr.DataReader(stock_code, start, end)
        kospi = fdr.DataReader("^KS11",    start, end)

        if stock is None or stock.empty or kospi is None or kospi.empty:
            return None

        common  = stock.index.intersection(kospi.index)
        if len(common) < 60:
            return None

        s_ret = stock.loc[common, "Close"].pct_change().dropna()
        k_ret = kospi.loc[common, "Close"].pct_change().dropna()
        common2 = s_ret.index.intersection(k_ret.index)
        s_ret = s_ret.loc[common2]
        k_ret = k_ret.loc[common2]

        cov  = np.cov(s_ret, k_ret)
        beta = float(cov[0, 1] / cov[1, 1])

        return {
            "beta":         round(beta, 4),
            "period_years": period_years,
            "index":        "KOSPI (^KS11)",
            "method":       "daily_return_regression",
        }
    except Exception as e:
        print(f"[calculate_beta] beta 계산 실패 ({stock_code}): {e}")
        return None


def get_macro_indicators() -> dict:
    """
    한국은행 ECOS API에서 최신 거시 지표 조회.
    - 국고채 10년물 수익률 (817Y002/010210000, 일별) → CAPM Rf
    - 한은 기준금리  (722Y001/0101000, 월별)
    - USD/KRW 환율  (731Y001/0000001, 일별)
    ECOS_API_KEY 없거나 API 실패 시 고정 기본값으로 fallback.
    """
    api_key = os.environ.get("ECOS_API_KEY")
    if not api_key:
        return {"risk_free_rate": 0.042, "base_rate": None, "usd_krw": None, "source": "default_fallback"}

    now = datetime.now()

    def _fetch_daily(stat_code: str, item_code: str) -> float | None:
        # 최근 30일 범위로 일별 조회 → 마지막 값
        end_d = now.strftime("%Y%m%d")
        m, y = now.month - 1, now.year
        if m <= 0:
            m, y = 12, y - 1
        start_d = f"{y}{m:02d}01"
        url = (
            f"https://ecos.bok.or.kr/api/StatisticSearch/{api_key}"
            f"/json/kr/1/30/{stat_code}/D/{start_d}/{end_d}/{item_code}"
        )
        try:
            rows = requests.get(url, timeout=8).json().get("StatisticSearch", {}).get("row", [])
            val = rows[-1].get("DATA_VALUE", "") if rows else ""
            return float(val) / 100 if val else None
        except Exception:
            return None

    def _fetch_monthly(stat_code: str, item_code: str) -> float | None:
        # 최근 6개월 범위로 월별 조회 → 마지막 값
        end_m = now.strftime("%Y%m")
        m, y = now.month - 6, now.year
        if m <= 0:
            m += 12; y -= 1
        start_m = f"{y}{m:02d}"
        url = (
            f"https://ecos.bok.or.kr/api/StatisticSearch/{api_key}"
            f"/json/kr/1/6/{stat_code}/M/{start_m}/{end_m}/{item_code}"
        )
        try:
            rows = requests.get(url, timeout=8).json().get("StatisticSearch", {}).get("row", [])
            val = rows[-1].get("DATA_VALUE", "") if rows else ""
            return float(val) / 100 if val else None
        except Exception:
            return None

    def _fetch_daily_raw(stat_code: str, item_code: str) -> float | None:
        end_d = now.strftime("%Y%m%d")
        m, y = now.month - 1, now.year
        if m <= 0:
            m, y = 12, y - 1
        start_d = f"{y}{m:02d}01"
        url = (
            f"https://ecos.bok.or.kr/api/StatisticSearch/{api_key}"
            f"/json/kr/1/30/{stat_code}/D/{start_d}/{end_d}/{item_code}"
        )
        try:
            rows = requests.get(url, timeout=8).json().get("StatisticSearch", {}).get("row", [])
            val = rows[-1].get("DATA_VALUE", "") if rows else ""
            return float(val) if val else None
        except Exception:
            return None

    rf_live   = _fetch_daily("817Y002", "010210000")   # 국고채 10년물 (연%, /100)
    base_live = _fetch_monthly("722Y001", "0101000")   # 한은 기준금리 (연%, /100)
    usd_krw   = _fetch_daily_raw("731Y001", "0000001") # USD/KRW (원, 그대로)

    risk_free_rate = rf_live if rf_live and 0.01 <= rf_live <= 0.15 else 0.042

    return {
        "risk_free_rate": round(risk_free_rate, 4),
        "base_rate":      round(base_live, 4) if base_live else None,
        "usd_krw":        round(usd_krw, 1)   if usd_krw  else None,
        "source":         "BOK ECOS" if rf_live else "default_fallback",
    }


def calculate_capm_discount_rate(
    stock_code: str,
    risk_free_rate: float = 0.042,
    equity_risk_premium: float = 0.055,
) -> dict | None:
    """
    CAPM 기반 자기자본비용 proxy 계산.
    정식 WACC(부채비용·자본구조 가중평균) 아님.

    Args:
        stock_code: KRX 종목코드
        risk_free_rate: 무위험수익률 (기본 4.2% — ECOS 국고채 10년물 또는 고정 근사값)
        equity_risk_premium: 시장 위험 프리미엄 (기본 5.5% 고정 가정)
    Returns:
        {"discount_rate", "beta", "risk_free_rate", "equity_risk_premium", "method", "source_note"} or None
    """
    beta_result = calculate_beta(stock_code)
    if beta_result is None:
        return None

    beta = beta_result["beta"]
    discount_rate = risk_free_rate + beta * equity_risk_premium

    return {
        "discount_rate":        round(discount_rate, 4),
        "beta":                 beta,
        "risk_free_rate":       risk_free_rate,
        "equity_risk_premium":  equity_risk_premium,
        "method":               "CAPM cost of equity proxy",
        "source_note":          "Rf and ERP are fixed assumptions, not automatically updated market data.",
    }


def _search_dart_disclosures(corp_code: str, year: int) -> list[dict]:
    """
    DART 공시검색 API로 해당 연도 실적 관련 유의미한 공시 목록 반환.
    노이즈(임원·특수관계인·보험·의결권 등) 제거 후 반환.
    """
    # 제외: 실적과 무관한 반복적 행정 공시
    _SKIP = (
        "임원", "주요주주", "소유상황", "소유주식", "소유변동",
        "특수관계인", "보험거래", "의결권", "주주총회소집",
        "기타경영사항",   # 자율공시는 내용 불명확
        "최대주주등소유",  # 최대주주 지분 변동 (경영 이벤트 아님)
    )
    # 우선 포함: 실적에 직접 영향을 주는 공시 유형
    _KEEP = (
        "합병", "분할", "영업양수", "영업양도",
        "유상증자", "무상증자", "전환사채", "신주인수권",
        "자기주식취득", "자기주식처분",  # 단순 '자기주식'은 오탐 가능
        "소송", "손상차손",               # '손상' 단독은 오탐 가능
        "시설투자", "공장", "생산능력",
        "사업보고서", "반기보고서", "분기보고서",
        "주요사항보고",
    )

    bgn = f"{year}0101"
    end = f"{year}1231"
    results: list[dict] = []
    try:
        resp = requests.get(
            "https://opendart.fss.or.kr/api/list.json",
            params={
                "crtfc_key":  DART_API_KEY,
                "corp_code":  corp_code,
                "bgn_de":     bgn,
                "end_de":     end,
                "page_count": 40,
            },
            timeout=10,
        )
        data = resp.json()
        if data.get("status") == "000":
            for item in data.get("list", []):
                name = item.get("report_nm", "")
                if any(k in name for k in _SKIP):
                    continue
                if any(k in name for k in _KEEP):
                    results.append({
                        "date":        item.get("rcept_dt", ""),
                        "report_name": name,
                        "source":      "OpenDART",
                        "signal":      "keep",   # 명시적 매칭
                    })
    except Exception:
        pass
    return results


def _clean_html(text: str) -> str:
    """HTML 태그 및 엔티티 제거."""
    import html as _html
    cleaned = BeautifulSoup(text, "html.parser").get_text()
    return _html.unescape(cleaned).strip()


def _search_naver_news(company_name: str, year: int, max_results: int = 6) -> list[dict]:
    """
    Naver News Search API로 해당 연도 기업 실적 관련 뉴스 검색.

    개선 사항:
    - 쿼리에 '{year}년' 포함 → 연도 맥락 명확화
    - 제목에 회사명 + '{year}년' 동시 포함 기사만 수집 (관련 없는 기사 차단)
    - description 반환으로 Claude 요약 품질 향상
    """
    client_id     = os.environ.get("NAVER_CLIENT_ID")
    client_secret = os.environ.get("NAVER_CLIENT_SECRET")
    if not client_id or not client_secret:
        return []

    year_tag = f"{year}년"   # "2023년" 패턴으로 엄격하게 필터

    queries = [
        f"{company_name} {year_tag} 영업이익 실적",
        f"{company_name} {year_tag} 매출 성장",
        f"{company_name} {year_tag} 업황 시장",
        f"{company_name} {year_tag} 손실 부진",
    ]
    seen: set[str] = set()
    news: list[dict] = []

    for q in queries:
        if len(news) >= max_results:
            break
        try:
            resp = requests.get(
                "https://openapi.naver.com/v1/search/news.json",
                headers={
                    "X-Naver-Client-Id":     client_id,
                    "X-Naver-Client-Secret": client_secret,
                },
                params={"query": q, "display": 5, "sort": "sim"},
                timeout=10,
            )
            for item in resp.json().get("items", []):
                title = _clean_html(item.get("title", ""))
                desc  = _clean_html(item.get("description", ""))
                if not title or title in seen:
                    continue

                # 엄격한 연도 필터: 제목에 '{year}년' 포함 필수
                # (Naver 무료 API는 날짜 범위 필터 미지원 → 텍스트 필터로 대체)
                if year_tag not in title:
                    continue

                # 회사명이 제목에 없으면 관련 없는 기사일 가능성 높음
                company_short = company_name[:2]  # "삼성전자" → "삼성"
                if company_short not in title:
                    continue

                seen.add(title)
                news.append({
                    "date":        item.get("pubDate", ""),
                    "title":       title,
                    "description": desc[:120] if desc else "",
                    "link":        item.get("link", ""),
                    "source":      "Naver News",
                })
                if len(news) >= max_results:
                    break
        except Exception:
            pass

    return news


_DART_EVENT_TAG_MAP = {
    "합병":           "합병/분할",
    "분할":           "합병/분할",
    "영업양수":       "영업양수도",
    "영업양도":       "영업양수도",
    "유상증자":       "유상증자",
    "전환사채":       "전환사채/신주인수권",
    "자기주식취득":   "자기주식 취득/처분",
    "자기주식처분":   "자기주식 취득/처분",
    "소송":           "소송/분쟁",
    "손상차손":       "자산손상차손",
    "시설투자":       "대규모 시설투자",
    "공장":           "대규모 시설투자",
    "주요사항보고":   "주요사항보고서 제출",
}

# 뉴스 본문 키워드 → 업황/이벤트 태그
_NEWS_KEYWORD_TAG_MAP = {
    "반도체": "반도체 업황",
    "메모리": "메모리 업황",
    "HBM":    "AI/HBM 수요",
    "AI":     "AI/HBM 수요",
    "구조조정": "구조조정",
    "적자":   "적자 전환",
    "흑자":   "흑자 전환",
    "환율":   "환율 영향",
    "원자재": "원자재 비용",
    "파업":   "노사 분쟁",
    "화재":   "생산 차질",
    "공급과잉": "공급 과잉",
    "수요 부진": "수요 부진",
    "해외 확장": "해외 성장",
    "수출":   "수출 호조",
}


def detect_company_events(company_name: str, corp_code: str, year: int) -> dict:
    """
    특정 연도 실적 이상치의 보조 설명 근거 탐색 (DART 공시 + Naver News).
    반환값은 note/tag 용도이며 DCF 수치에 자동 반영하지 말 것.
    """
    dart_events = _search_dart_disclosures(corp_code, year)
    news_events = _search_naver_news(company_name, year)

    # ── 태그 추출 ────────────────────────────────────────────────────────
    tags: set[str] = set()

    # DART 공시 기반
    for ev in dart_events:
        for kw, tag in _DART_EVENT_TAG_MAP.items():
            if kw in ev.get("report_name", ""):
                tags.add(tag)

    # 뉴스 본문 기반 업황/이벤트 태그
    for ev in news_events:
        text = ev.get("title", "") + " " + ev.get("description", "")
        for kw, tag in _NEWS_KEYWORD_TAG_MAP.items():
            if kw in text:
                tags.add(tag)

    # ── 신뢰도 판단 (노이즈 제거 후 실질 근거 수 기준) ────────────────────
    # dart_events는 이미 _KEEP 키워드 매칭된 것만 반환됨
    # news_events는 '{year}년' + 회사명 필터 통과한 것만 반환됨
    meaningful = len(dart_events) + len(news_events)
    if meaningful >= 4:
        confidence = "high"
    elif meaningful >= 2:
        confidence = "medium"
    elif meaningful == 1:
        confidence = "low"
    else:
        confidence = "none"

    # ── Claude 요약 (근거 있을 때만) ─────────────────────────────────────
    event_note = ""
    if dart_events or news_events:
        dart_text = "\n".join(
            f"- [{e['date']}] {e['report_name']}" for e in dart_events[:6]
        )
        news_text = "\n".join(
            f"- {e['title']} / {e.get('description', '')[:80]}"
            for e in news_events[:4]
        )
        prompt = (
            f"아래는 {company_name}의 {year}년 실적 이상치를 설명하는 데 활용할 공시·뉴스 목록입니다.\n\n"
            f"[DART 공시 — {len(dart_events)}건]\n{dart_text or '없음'}\n\n"
            f"[뉴스 — {len(news_events)}건]\n{news_text or '없음'}\n\n"
            f"요청:\n"
            f"- {year}년 영업이익 또는 매출에 영향을 줬을 만한 사실만 1~2문장으로 서술\n"
            f"- 마크다운(**, #, - 등) 사용 금지\n"
            f"- 투자의견·DCF 수치 변경·결론 제시 금지\n"
            f"- 공시·뉴스에 없는 내용은 추정하지 말 것\n"
            f"- 근거가 불충분하면 '명확한 이벤트 근거를 찾지 못했습니다.'라고만 답할 것"
        )
        try:
            event_note = ask(prompt, max_tokens=180).strip()
        except Exception:
            event_note = ""

    # 근거 없음 fallback — confidence와 일관성 유지
    if not event_note:
        if confidence == "none":
            event_note = f"{year}년 실적 이상치에 대한 공시·뉴스 근거를 찾지 못했습니다. 통계(MAD)로만 처리됩니다."
        else:
            event_note = f"{year}년 관련 근거가 수집됐으나 실적 영향 설명을 생성하지 못했습니다."

    return {
        "company_name": company_name,
        "corp_code":    corp_code,
        "year":         year,
        "event_tags":   sorted(tags),
        "dart_events":  dart_events,
        "news_events":  news_events,
        "event_note":   event_note,
        "confidence":   confidence,
    }


def _find_anomaly_years(income_statement: dict) -> list[int]:
    """
    OPM 급락·급등 또는 매출 급변 연도를 이상치 후보로 반환.
    detect_company_events 호출 대상 연도 선별에 사용.
    """
    years = sorted(income_statement.keys())
    margins: dict[int, float] = {}
    for yr in years:
        rev = income_statement[yr].get("revenue")
        op  = income_statement[yr].get("operating_profit")
        if rev and rev > 0 and op is not None:
            margins[yr] = op / rev

    anomalies: set[int] = set()

    # OPM 이상치: 중앙값 기준 ±10pp 초과 (최소 3개년 필요)
    if len(margins) >= 3:
        import statistics as _st
        med = _st.median(margins.values())
        for yr, m in margins.items():
            if abs(m - med) > 0.10:
                anomalies.add(yr)

    # 매출 YoY 이상치: -10% 미만 또는 +40% 초과
    for i in range(1, len(years)):
        r0 = income_statement[years[i - 1]].get("revenue")
        r1 = income_statement[years[i]].get("revenue")
        if r0 and r1 and r0 > 0:
            yoy = (r1 - r0) / r0
            if yoy < -0.10 or yoy > 0.40:
                anomalies.add(years[i])

    return sorted(anomalies)


def get_dcf_inputs(company_name: str) -> dict:
    """
    DCF 시뮬레이션용 DART 재무 데이터 수집.

    반환 구조:
        company_info / income_statement / balance_sheet / cash_flow / shares / market_metrics
    단위: 억원 (shares·market_metrics 제외, market_metrics는 원 단위).
    계정 누락 시 None 반환, 예외 발생 시 빈 dict 반환.
    """
    try:
        corp_obj = _find_corp_obj(company_name)
        if corp_obj is None:
            print(f"[get_dcf_inputs] 기업 미발견: {company_name}")
            return {}

        corp_code  = corp_obj.corp_code
        stock_code = getattr(corp_obj, "stock_code", "") or ""
        corp_name  = getattr(corp_obj, "corp_name", company_name)
        base_year  = datetime.now().year - 1  # 전년도 = 최신 사업연도

        # ── 연도별 원시 데이터 수집 (5개년, API 호출 최소화) ──────────────
        year_items: dict[int, list] = {}
        for year in range(base_year - 4, base_year + 1):
            items = _fetch_statements_raw(corp_code, year, "CFS")
            if not items:
                items = _fetch_statements_raw(corp_code, year, "OFS")
            if items:
                year_items[year] = items

        # ── 손익계산서 (IS/CIS) ──────────────────────────────────────────
        income_statement: dict[int, dict] = {}
        for year, items in year_items.items():
            rev = _match_account(items, ("IS", "CIS"),
                                 ["매출액", "수익(매출액)", "영업수익"])
            op  = _match_account(items, ("IS", "CIS"),
                                 ["영업이익", "영업손익", "영업이익(손실)"])
            net = _match_account(items, ("IS", "CIS"),
                                 ["당기순이익", "당기순손익", "당기순이익(손실)", "연결당기순이익"])
            tax = _match_account(items, ("IS", "CIS"),
                                 ["법인세비용", "법인세비용(수익)"])
            int_exp = _match_account(items, ("IS", "CIS"),
                                 ["이자비용", "금융비용", "이자원가"])
            if rev is not None or op is not None:
                income_statement[year] = {
                    "revenue":          rev,
                    "operating_profit": op,
                    "net_income":       net,
                    "tax_expense":      tax,
                    "interest_expense": int_exp,
                }

        # ── 재무상태표 (BS) — 최신 연도 ─────────────────────────────────
        latest_items = year_items.get(base_year, [])

        # 리스부채: 유동 + 비유동 합산 (부분 매칭으로 한쪽만 잡히는 문제 방지)
        _lease_c  = _match_account(latest_items, ("BS",), ["유동리스부채", "유동성리스부채"])
        _lease_nc = _match_account(latest_items, ("BS",), ["비유동리스부채", "장기리스부채"])
        if _lease_c is not None or _lease_nc is not None:
            _lease_total: int | None = (_lease_c or 0) + (_lease_nc or 0)
        else:
            # 일부 회사는 단일 "리스부채" 계정 사용
            _lease_total = _match_account(latest_items, ("BS",), ["리스부채"])

        balance_sheet = {
            base_year: {
                "cash_and_cash_equivalents":         _match_account(latest_items, ("BS",), ["현금및현금성자산"]),
                "current_assets":                    _match_account(latest_items, ("BS",), ["유동자산"]),
                "current_liabilities":               _match_account(latest_items, ("BS",), ["유동부채"]),
                "short_term_borrowings":             _match_account(latest_items, ("BS",), ["단기차입금"]),
                "current_portion_of_long_term_debt": _match_account(latest_items, ("BS",), ["유동성장기부채", "유동성장기차입금"]),
                "long_term_borrowings":              _match_account(latest_items, ("BS",), ["장기차입금"]),
                "bonds_payable":                     _match_account(latest_items, ("BS",), ["사채", "회사채"]),
                "lease_liabilities":                 _lease_total,
                "total_assets":                      _match_account(latest_items, ("BS",), ["자산총계"]),
                "total_liabilities":                 _match_account(latest_items, ("BS",), ["부채총계"]),
                "total_equity":                      _match_account(latest_items, ("BS",), ["자본총계"]),
            }
        }

        # ── 현금흐름표 (CF) — 최신 연도 ─────────────────────────────────
        # CAPEX는 지출(음수)이므로 abs 처리
        def _abs_account(items, divs, cands):
            val = _match_account(items, divs, cands)
            return abs(val) if val is not None else None

        # DART XBRL 표준 태그에 따라 회사별 표기가 다름:
        # ifrs-full_AdjustmentsForDepreciationExpense → "유형자산상각비" (APR 등)
        # 자체 태그 → "감가상각비" / "유형자산감가상각비" 등
        _dep  = _match_account(latest_items, ("CF",),
                               ["유형자산상각비",      # IFRS XBRL 표준 (APR, 다수)
                                "감가상각비",          # 일반적 표현
                                "유형자산감가상각비",
                                "감가상각비및상각비",   # 유형+무형 합산
                                "감가상각및상각비"])
        _amor = _match_account(latest_items, ("CF",), ["무형자산상각비", "무형자산상각"])
        _roua = _match_account(latest_items, ("CF",), ["사용권자산상각비", "사용권자산상각"])

        # 합산 계정이 있는지 확인 — 있으면 그것만, 없으면 유형+무형 합산
        _dep_combined_nm = ["감가상각비및상각비", "감가상각및상각비"]
        _is_combined = any(
            it.get("account_nm", "").strip().replace(" ", "") in
            [c.replace(" ", "") for c in _dep_combined_nm]
            for it in latest_items if it.get("sj_div") == "CF"
        )
        if _is_combined:
            _pp_amor = _dep                          # 합산 계정 그대로
        else:
            _dep_t  = _dep  or 0
            _amor_t = _amor or 0
            _pp_amor = (_dep_t + _amor_t) if (_dep is not None or _amor is not None) else None

        # IFRS 16 일관성: ROUA상각비 별도 보관 → valuation에서 D&A에 합산
        # (영업이익이 이미 ROUA상각비를 차감했으므로 FCF 계산 시 다시 더해야 함)
        if _pp_amor is not None or _roua is not None:
            _dep_total: int | None = (_pp_amor or 0) + (_roua or 0)
        else:
            _dep_total = None
        # BS 역산 미사용: PPE 변동에 M&A·자산처분·환율·손상 등이 섞여
        # 기업별로 오차 방향이 달라 모델 왜곡 위험이 크다.
        # CF 직접 추출 실패 시 None으로 남겨두고 valuation에서 기본 ratio 사용.

        _capex_t = _abs_account(latest_items, ("CF",),
                                ["유형자산의 취득", "유형자산 취득",
                                 "유형자산취득", "유형자산의취득", "유형자산구입",
                                 "유형자산의 증가", "유형자산증가"])
        _capex_i = _abs_account(latest_items, ("CF",),
                                ["무형자산의 취득", "무형자산 취득",
                                 "무형자산취득", "무형자산의취득",
                                 "무형자산의 증가", "무형자산증가"])

        # 비현금조정 합계 — 참고용. D&A proxy로 사용하지 않음
        # (외환손익·평가손익·충당금·법인세/이자 조정 등이 혼입되어 D&A와 다름)
        _noncash_adj = _match_account(latest_items, ("CF",),
                                      ["당기순이익조정을 위한 가감",
                                       "당기순손익조정을 위한 가감",
                                       "비현금항목조정"])

        cf_direct_total = _dep_total  # CF 직접 추출값 (없으면 None)

        # ── XBRL D&A fallback (환경변수 ENABLE_XBRL_DA_FALLBACK=true 시 활성) ──
        # CF 직접 추출 실패 시에만 호출. CF 직접값이 있으면 XBRL 호출 생략.
        # noncash_adjustments × 70% proxy는 절대 사용하지 않음.
        xbrl_da: dict = {}
        _xbrl_enabled = os.environ.get("ENABLE_XBRL_DA_FALLBACK", "false").lower() == "true"
        if _xbrl_enabled and cf_direct_total is None:
            try:
                xbrl_res = get_depreciation_from_xbrl_notes(corp_code, base_year)
                if xbrl_res and xbrl_res.get("confidence") in ("high", "medium"):
                    xbrl_da = {
                        "xbrl_depreciation_total": xbrl_res.get("depreciation_total"),
                        "xbrl_depreciation":       xbrl_res.get("depreciation"),
                        "xbrl_amortization":       xbrl_res.get("amortization"),
                        "xbrl_roua_depreciation":  xbrl_res.get("roua_depreciation"),
                        "xbrl_impairment_loss":    xbrl_res.get("impairment_loss"),
                        "xbrl_da_confidence":      xbrl_res.get("confidence"),
                        "xbrl_da_source":          "separate" if xbrl_res.get("separate_fallback") else "consolidated",
                        "xbrl_da_note":            xbrl_res.get("note", ""),
                    }
            except Exception as _xbrl_err:
                xbrl_da = {"xbrl_da_note": f"XBRL 조회 실패: {_xbrl_err}"}

        cash_flow = {
            base_year: {
                "cash_flow_from_operations": _match_account(latest_items, ("CF",),
                                             ["영업활동현금흐름", "영업활동으로 인한 현금흐름", "영업활동으로인한현금흐름"]),
                "capex_tangible":            _capex_t,
                "capex_intangible":          _capex_i,
                "depreciation":              _dep,
                "amortization":              _amor,
                "roua_depreciation":         _roua,
                "depreciation_total":        _dep_total,   # CF 직접 추출 (우선)
                "depreciation_source":       "cf_direct" if _dep_total is not None else None,
                "noncash_adjustments":       _noncash_adj, # 참고용 비현금조정 합계. D&A proxy로 사용하지 않음
                **xbrl_da,                                 # XBRL fallback (활성 시)
            }
        }

        # ── 주식 수 ───────────────────────────────────────────────────────
        shares = _fetch_shares(corp_code)

        # ── 시장 지표 (PER/PBR/Beta/CAPM) ────────────────────────────────
        macro        = get_macro_indicators()
        price_data   = get_current_price(stock_code)
        capm_data    = calculate_capm_discount_rate(stock_code, risk_free_rate=macro["risk_free_rate"])
        shares_out   = shares.get("shares_outstanding")

        current_price = price_data.get("current_price") if price_data else None
        price_date    = price_data.get("date")          if price_data else None

        latest_inc = income_statement.get(base_year, {})
        net_income = latest_inc.get("net_income")
        total_eq   = balance_sheet.get(base_year, {}).get("total_equity")

        # EPS/BPS: 억원 → 원 변환 후 주식수로 나눔
        eps = round(net_income * 100_000_000 / shares_out) if (net_income and shares_out) else None
        bps = round(total_eq  * 100_000_000 / shares_out) if (total_eq  and shares_out) else None
        per = round(current_price / eps, 2) if (current_price and eps and eps > 0) else None
        pbr = round(current_price / bps, 2) if (current_price and bps and bps > 0) else None

        rf_source = macro.get("source", "default_fallback")
        market_metrics = {
            "current_price":        current_price,
            "price_date":           price_date,
            "eps":                  eps,
            "bps":                  bps,
            "per":                  per,
            "pbr":                  pbr,
            "beta":                 capm_data.get("beta")                if capm_data else None,
            "capm_discount_rate":   capm_data.get("discount_rate")       if capm_data else None,
            "risk_free_rate":       capm_data.get("risk_free_rate")      if capm_data else macro["risk_free_rate"],
            "equity_risk_premium":  capm_data.get("equity_risk_premium") if capm_data else 0.055,
            "discount_rate_method": "CAPM cost of equity proxy",
            "source_note": (
                f"Rf={macro['risk_free_rate']:.2%} (BOK ECOS 국고채 10년물 실시간). ERP 5.5% 고정 가정."
                if rf_source == "BOK ECOS"
                else "Rf=4.2% 고정 근사값 (ECOS 조회 실패). ERP 5.5% 고정 가정."
            ),
            "macro": {
                "risk_free_rate": macro["risk_free_rate"],
                "base_rate":      macro.get("base_rate"),
                "usd_krw":        macro.get("usd_krw"),
                "source":         rf_source,
            },
        }

        # ── 이상치 연도 이벤트 탐색 (전체 이상치 연도, 설명 노트용) ──────────────
        # 이벤트 미발견 시에도 통계 이상치 판단은 유효 — 이벤트는 보조 설명일 뿐
        anomaly_years = _find_anomaly_years(income_statement)
        company_events: dict[int, dict] = {}
        for yr in anomaly_years:
            print(f"[get_dcf_inputs] {yr}년 이벤트 탐색 중...")
            company_events[yr] = detect_company_events(corp_name, corp_code, yr)

        return {
            "company_info": {
                "corp_name":  corp_name,
                "corp_code":  corp_code,
                "stock_code": stock_code,
                "base_year":  base_year,
            },
            "income_statement": income_statement,
            "balance_sheet":    balance_sheet,
            "cash_flow":        cash_flow,
            "shares":           shares,
            "market_metrics":   market_metrics,
            "company_events":   company_events,  # {year: detect_company_events 결과}
        }

    except Exception as e:
        print(f"[get_dcf_inputs] {company_name} 오류: {e}")
        return {}


if __name__ == "__main__":
    import sys
    import time
    sys.stdout.reconfigure(encoding="utf-8")

    # ── 기존 get_financials 확인 ─────────────────────────────────────────
    print("=" * 55)
    print("[ 1 ] get_financials() 기존 함수 확인")
    print("=" * 55)
    for name in ["에이피알", "asdfasdf"]:
        t0 = time.time()
        d = get_financials(name)
        print(f"  {name}: {len(d)}개년 ({time.time()-t0:.1f}s)" if d else f"  {name}: no data")

    # ── get_dcf_inputs 테스트 ────────────────────────────────────────────
    print()
    print("=" * 55)
    print("[ 2 ] get_dcf_inputs('에이피알') 테스트")
    print("=" * 55)
    t0 = time.time()
    result = get_dcf_inputs("에이피알")
    elapsed = time.time() - t0

    if not result:
        print("  결과 없음")
    else:
        ci = result["company_info"]
        print(f"\n  [company_info]")
        print(f"    corp_name : {ci['corp_name']}")
        print(f"    corp_code : {ci['corp_code']}")
        print(f"    stock_code: {ci['stock_code']}")
        print(f"    base_year : {ci['base_year']}")

        print(f"\n  [income_statement] ({len(result['income_statement'])}개년)")
        for yr, d in sorted(result["income_statement"].items()):
            print(f"    {yr}: revenue={d['revenue']}억 | op_profit={d['operating_profit']}억 | net={d['net_income']}억")

        bs = result["balance_sheet"].get(ci["base_year"], {})
        print(f"\n  [balance_sheet] {ci['base_year']}년")
        print(f"    현금               : {bs.get('cash_and_cash_equivalents')}억")
        print(f"    단기차입금         : {bs.get('short_term_borrowings')}억")
        print(f"    장기차입금         : {bs.get('long_term_borrowings')}억")
        print(f"    리스부채(유동+비유동): {bs.get('lease_liabilities')}억")
        print(f"    자산총계           : {bs.get('total_assets')}억")
        print(f"    자본총계           : {bs.get('total_equity')}억")

        cf = result["cash_flow"].get(ci["base_year"], {})
        print(f"\n  [cash_flow] {ci['base_year']}년")
        print(f"    영업활동현금흐름   : {cf.get('cash_flow_from_operations')}억")
        print(f"    CAPEX(유형)        : {cf.get('capex_tangible')}억")
        print(f"    CAPEX(무형)        : {cf.get('capex_intangible')}억")
        print(f"    감가상각비(유형)   : {cf.get('depreciation')}억")
        print(f"    상각비(무형)       : {cf.get('amortization')}억")
        print(f"    사용권자산상각비   : {cf.get('roua_depreciation')}억  (IFRS 16)")
        print(f"    D&A 합계(DCF용)    : {cf.get('depreciation_total')}억")

        sh = result["shares"]
        print(f"\n  [shares]")
        print(f"    유통주식수(보통주) : {sh.get('shares_outstanding')}")
        print(f"    자기주식수         : {sh.get('treasury_shares')}")
        print(f"    출처               : {sh.get('source_note')}")

    print(f"\n  소요시간: {elapsed:.1f}s")
    print("=" * 55)


# ── XBRL D&A 추출 PoC ────────────────────────────────────────────────────────
# PoC 단계. get_dcf_inputs()에 자동 연결하지 않음.
# 결과는 기존 CF 직접 추출값 확인/보완용으로만 사용할 것.

def get_depreciation_from_xbrl_notes(corp_code: str, year: int) -> dict | None:
    """
    OpenDART XBRL instance document에서 D&A 관련 항목 추출 (PoC).

    전략:
      1. 사업보고서 접수번호(rcept_no) 조회
      2. fnlttXbrl.xml로 XBRL ZIP 다운로드
      3. ifrs-full D&A 태그 탐색 + "전사·연결·당기" 컨텍스트 필터
      4. 결과 반환 + confidence 표시

    중요:
      - 기존 CF 직접 추출값(depreciation_total)이 있으면 해당 값이 우선.
      - 이 함수 결과만으로 FCF Method A 전환 금지.
      - 회사별 XBRL 구조 차이로 confidence가 "high"가 아닐 수 있음.
    """
    import io, zipfile
    import xml.etree.ElementTree as ET

    result: dict = {
        "source":            "OpenDART XBRL",
        "year":              year,
        "corp_code":         corp_code,
        "depreciation":      None,   # 유형자산 감가상각비 (억원)
        "amortization":      None,   # 무형자산 상각비 (억원)
        "roua_depreciation": None,   # 사용권자산 상각비 (억원)
        "depreciation_total": None,  # 합산 (억원)
        "impairment_loss":   None,   # 손상차손 (억원)
        "matched_tags":      [],
        "confidence":        "low",
        "note":              "",
    }

    # ── 1. 사업보고서 rcept_no 조회 ─────────────────────────────────────
    try:
        r_list = requests.get(
            "https://opendart.fss.or.kr/api/list.json",
            params={
                "crtfc_key":    DART_API_KEY,
                "corp_code":    corp_code,
                "bgn_de":       f"{year}0101",
                "end_de":       f"{year + 1}0430",
                "pblntf_ty":    "A",           # 사업보고서
                "last_reprt_at": "Y",
            },
            timeout=15,
        )
        items = r_list.json().get("list", [])
        rcept_no = next(
            (it["rcept_no"] for it in items if f"{year}.12" in it.get("report_nm", "")),
            None,
        )
        if not rcept_no:
            result["note"] = f"{year}년 사업보고서 rcept_no를 찾지 못했습니다."
            return result
    except Exception as e:
        result["note"] = f"rcept_no 조회 실패: {e}"
        return result

    # ── 2. XBRL ZIP 다운로드 ────────────────────────────────────────────
    try:
        r_xbrl = requests.get(
            "https://opendart.fss.or.kr/api/fnlttXbrl.xml",
            params={
                "crtfc_key":  DART_API_KEY,
                "rcept_no":   rcept_no,
                "reprt_code": "11011",   # 사업보고서
                "repTp":      "3",       # 현금흐름표 기준 (D&A 주석 포함)
            },
            timeout=40,
        )
        if r_xbrl.content[:2] != b"PK":
            result["note"] = "XBRL ZIP 수신 실패 (응답이 ZIP이 아님)"
            return result

        with zipfile.ZipFile(io.BytesIO(r_xbrl.content)) as z:
            xbrl_name = next((n for n in z.namelist() if n.endswith(".xbrl")), None)
            if not xbrl_name:
                result["note"] = "ZIP 내 .xbrl 파일 없음"
                return result
            xbrl_data = z.read(xbrl_name)
    except Exception as e:
        result["note"] = f"XBRL 다운로드 실패: {e}"
        return result

    # ── 3. XBRL 파싱 + D&A 태그 탐색 ────────────────────────────────────
    # 탐색 태그: ifrs-full 표준 D&A 태그 (회사별 사용 태그 다름 — 우선순위 순)
    # 유형: DepreciationExpense(삼성) > DepreciationPropertyPlantAndEquipment(SK하이닉스)
    #       > DepreciationAndAmortisationExpense(합산 fallback)
    # 무형: AmortisationIntangibleAssetsOtherThanGoodwill > AmortisationExpense
    # CF조정: AdjustmentsForDepreciation... (CF간접법 표시 기업용)
    _TARGET_TAGS: dict[str, tuple[str, int]] = {
        # 태그명: (field, 우선순위)  — 숫자 낮을수록 우선
        "DepreciationExpense":                              ("depreciation",      1),
        "DepreciationPropertyPlantAndEquipment":            ("depreciation",      2),
        "DepreciationAndAmortisationExpense":               ("depreciation",      3),  # 합산 fallback
        "AdjustmentsForDepreciationExpense":                ("depreciation",      4),
        "AmortisationIntangibleAssetsOtherThanGoodwill":    ("amortization",      1),
        "AmortisationExpense":                              ("amortization",      2),
        "AdjustmentsForAmortisationExpense":                ("amortization",      3),
        "DepreciationRightofuseAssets":                     ("roua_depreciation", 1),
        "DepreciationOperatingLeaseAssets":                 ("roua_depreciation", 2),
        "ImpairmentLossRecognisedInProfitOrLoss":           ("impairment_loss",   1),
        "ImpairmentLossRecognisedInProfitOrLossPropertyPlantAndEquipment": ("impairment_loss", 2),
    }

    # 컨텍스트 선택 원칙:
    # Pass 1: 연결(ConsolidatedMember) + 당기(CFY{year}) + 추가 axis 없음
    # Pass 2: 연결 없을 경우 개별(SeparateMember) fallback (연결 종속기업 없는 기업)
    _year_tag = f"CFY{year}"

    try:
        root = ET.fromstring(xbrl_data)
    except ET.ParseError as e:
        result["note"] = f"XBRL XML 파싱 실패: {e}"
        return result

    def _extract_da(root_elem: ET.Element, member_type: str) -> tuple[dict, list[str]]:
        """member_type: 'ConsolidatedMember' 또는 'SeparateMember'"""
        cands: dict[str, list[tuple[int, int]]] = {}  # field → [(priority, value)]
        tags_found: list[str] = []

        for elem in root_elem.iter():
            local = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if local not in _TARGET_TAGS:
                continue
            ctx = elem.get("contextRef", "")
            val_str = elem.text
            if val_str is None:
                continue

            is_current = _year_tag in ctx
            has_member = member_type in ctx
            # 반대 member 제외 (SeparateMember 패스면 ConsolidatedMember 제외 등)
            other = "SeparateMember" if member_type == "ConsolidatedMember" else "ConsolidatedMember"
            has_other = other in ctx
            # 총액 컨텍스트: member 이후 추가 axis 없음
            after_member = ctx.split(member_type)[-1] if member_type in ctx else ""
            is_total = after_member == ""

            if not (is_current and has_member and not has_other and is_total):
                continue

            try:
                val_eok = int(val_str) // 100_000_000
            except ValueError:
                continue

            field, priority = _TARGET_TAGS[local]
            cands.setdefault(field, []).append((priority, val_eok))
            if local not in tags_found:
                tags_found.append(local)

        # 필드별로 가장 높은 우선순위(낮은 숫자) 값 선택
        chosen: dict[str, int] = {}
        for field, pv_list in cands.items():
            best = min(pv_list, key=lambda x: x[0])
            chosen[field] = best[1]

        return chosen, tags_found

    # Pass 1: 연결재무제표
    chosen, matched_tags = _extract_da(root, "ConsolidatedMember")
    is_separate_fallback = False

    # Pass 2: 연결 없으면 개별재무제표로 재시도
    if not chosen:
        chosen, matched_tags = _extract_da(root, "SeparateMember")
        if chosen:
            is_separate_fallback = True

    for field, val in chosen.items():
        result[field] = val

    result["matched_tags"] = matched_tags

    # D&A 합산: 유형 + 무형 + ROU (손상차손 제외)
    dep   = result["depreciation"]     or 0
    amor  = result["amortization"]     or 0
    roua  = result["roua_depreciation"] or 0

    if dep > 0 or amor > 0 or roua > 0:
        result["depreciation_total"] = dep + amor + roua

    # ── confidence 판단 ────────────────────────────────────────────────
    if dep > 0 and amor > 0:
        confidence = "high"
    elif dep > 0 or amor > 0:
        confidence = "medium"
    else:
        confidence = "low"

    member_label = "개별재무제표(SeparateMember)" if is_separate_fallback else "연결재무제표(ConsolidatedMember)"
    result["confidence"] = confidence
    result["separate_fallback"] = is_separate_fallback
    result["note"] = (
        f"XBRL({xbrl_name})에서 D&A 탐색 완료. "
        f"기준: {member_label}. rcept_no={rcept_no}. "
        f"매칭 태그: {matched_tags}. "
        f"감가상각: {dep:,}억, 무형상각: {amor:,}억, ROU상각: {roua:,}억. "
        "PoC 단계 — get_dcf_inputs() 자동 연결 전 검증 권장. "
        "CF 직접 추출값 있으면 CF 값 우선 적용."
    )

    return result
