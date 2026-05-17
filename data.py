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

_REVENUE_LABELS = {"매출액", "영업수익", "수익(매출액)", "매출"}
_OPERATING_LABELS = {"영업이익", "영업이익(손실)", "영업손실"}
_NET_LABELS = {"당기순이익", "당기순이익(손실)", "당기순손실"}


def _get_corp_list():
    global _corp_list_cache
    if _corp_list_cache is None:
        _corp_list_cache = dart.get_corp_list()
    return _corp_list_cache


def _is_english(text: str) -> bool:
    alpha = sum(1 for c in text if c.isascii() and c.isalpha())
    return alpha / max(len(text), 1) >= 0.5


def _normalize_name(company_name: str) -> str:
    """영문 입력이면 Claude로 DART 등록 회사명으로 변환, 한국어면 그대로 반환."""
    if not _is_english(company_name):
        return company_name
    from claude_client import ask
    result = ask(
        f"'{company_name}'은 한국 어느 기업입니까? "
        "DART(금융감독원 전자공시시스템)에 등록된 정식 회사명만 답하세요. "
        "회사명 외 다른 말은 절대 쓰지 마세요.",
        max_tokens=30,
    ).strip()
    return result if result else company_name


def _find_corp_code(company_name: str) -> str:
    corp_list = _get_corp_list()
    raw = company_name.strip()
    normalized = _normalize_name(raw)

    candidates = list(dict.fromkeys([normalized, raw, normalized.replace(" ", ""), raw.replace(" ", "")]))

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
    return data


def _fetch_from_dart(company_name: str) -> dict:
    corp_code = _find_corp_code(company_name)
    if not corp_code:
        return {}

    result = {}
    for year in range(2021, 2026):
        year_data = _extract_year(corp_code, year, "OFS")
        if not year_data or not {"매출액", "영업이익", "순이익"}.issubset(year_data):
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
        str(year): {"매출액": rev, "영업이익": op, "순이익": net}
        for year, rev, op, net in rows
    }


def get_financials(company_name: str) -> dict:
    """6개년(2020~2025) 재무 데이터. 키는 문자열 연도. 단위: 백만원."""
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
            # 유통주식수(자기주식 차감) 우선; 없으면 발행주식총수
            if distb is not None:
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
        risk_free_rate: 무위험수익률 (기본 4.2% — 한국 10년물 근사)
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

        # ── CAPEX (BS 역산용 선계산) ────────────────────────────────────────
        _capex_t = _abs_account(latest_items, ("CF",),
                                ["유형자산의 취득", "유형자산 취득",
                                 "유형자산취득", "유형자산의취득", "유형자산구입",
                                 "유형자산의 증가", "유형자산증가"])
        _capex_i = _abs_account(latest_items, ("CF",),
                                ["무형자산의 취득", "무형자산 취득",
                                 "무형자산취득", "무형자산의취득",
                                 "무형자산의 증가", "무형자산증가"])

        # ── BS 역산 D&A fallback ────────────────────────────────────────────
        # 일부 기업(삼성전자 등)은 DART CF에 감가상각비가 집계 항목 하위에 숨어 있어
        # API로 직접 조회 불가. 이 경우 BS 순액 PPE 변동으로 역산:
        #   D&A ≈ PPE_전년 + CAPEX(유형) - PPE_당년
        _dep_bs_estimated: int | None = None
        if _dep_total is None:
            prev_items = year_items.get(base_year - 1, [])
            _ppe_curr = _match_account(latest_items, ("BS",), ["유형자산"])
            _ppe_prev = _match_account(prev_items,   ("BS",), ["유형자산"])
            if _ppe_curr is not None and _ppe_prev is not None and _capex_t is not None:
                _estimated = _ppe_prev + _capex_t - _ppe_curr
                if _estimated > 0:
                    _dep_bs_estimated = _estimated
                    _dep_total = _dep_bs_estimated

        cash_flow = {
            base_year: {
                "cash_flow_from_operations": _match_account(latest_items, ("CF",),
                                             ["영업활동현금흐름", "영업활동으로 인한 현금흐름", "영업활동으로인한현금흐름"]),
                "capex_tangible":            _capex_t,
                "capex_intangible":          _capex_i,
                "depreciation":             _dep,     # 유형자산감가상각비 단독
                "amortization":             _amor,    # 무형자산상각비 단독
                "roua_depreciation":        _roua,    # 사용권자산상각비(IFRS 16)
                "depreciation_total":       _dep_total,  # DCF용: 유형+무형+ROUA 합산
                "depreciation_estimated":   _dep_bs_estimated is not None,  # BS 역산 여부 플래그
            }
        }

        # ── 주식 수 ───────────────────────────────────────────────────────
        shares = _fetch_shares(corp_code)

        # ── 시장 지표 (PER/PBR/Beta/CAPM) ────────────────────────────────
        price_data   = get_current_price(stock_code)
        capm_data    = calculate_capm_discount_rate(stock_code)
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

        market_metrics = {
            "current_price":        current_price,
            "price_date":           price_date,
            "eps":                  eps,
            "bps":                  bps,
            "per":                  per,
            "pbr":                  pbr,
            "beta":                 capm_data.get("beta")                if capm_data else None,
            "capm_discount_rate":   capm_data.get("discount_rate")       if capm_data else None,
            "risk_free_rate":       capm_data.get("risk_free_rate")      if capm_data else 0.042,
            "equity_risk_premium":  capm_data.get("equity_risk_premium") if capm_data else 0.055,
            "discount_rate_method": "CAPM cost of equity proxy",
            "source_note":          "CAPM discount rate is a reference value only. Rf and ERP are fixed assumptions.",
        }

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
