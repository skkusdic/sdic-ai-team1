import io
import os
import re
import tempfile
import anthropic
import plotly.graph_objects as go
from fpdf import FPDF, XPos, YPos
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# ── 색상 팔레트 (RGB 튜플) ────────────────────────────────────────────────────
PRIMARY    = (26,  77,  58)   # #1a4d3a 딥그린
ACCENT     = (45, 122,  87)   # #2d7a57 미디엄 그린
RED        = (192,  57,  43)  # #c0392b 적자
TEXT_COL   = (26,  26,  26)   # #1a1a1a
MUTED      = (85,  85,  85)   # #555555
BORDER     = (200, 216, 206)  # #c8d8ce
TABLE_ODD  = (255, 255, 255)  # 홀수행 흰색
TABLE_EVEN = (242, 247, 244)  # #f2f7f4
CARD_BG    = (244, 248, 246)  # #f4f8f6
TAG_BG     = (212, 232, 220)  # #d4e8dc
WHITE      = (255, 255, 255)

# ── 폰트 경로 ─────────────────────────────────────────────────────────────────
_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")




# ═══════════════════════════════════════════════════════════════════════════════
class ReportPDF(FPDF):
    """기업 분석 리포트 PDF 생성기"""

    _HEADER_H = 28
    _FOOTER_H = 14

    def __init__(self, company_name: str):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.company_name = company_name
        self.set_margins(left=16, top=self._HEADER_H, right=16)
        self.set_auto_page_break(auto=True, margin=self._FOOTER_H)
        self.eff_w = 210 - 32
        self._register_fonts()

    # ── 폰트 등록 ─────────────────────────────────────────────────────────────
    def _register_fonts(self):
        pairs = [("", "Pretendard-Regular.ttf"), ("B", "Pretendard-Bold.ttf")]
        missing = []
        for style, fname in pairs:
            path = os.path.join(_FONT_DIR, fname)
            if os.path.exists(path):
                self.add_font("Pretendard", style, path)
            else:
                missing.append(fname)

        if missing:
            fallback = os.path.join(_FONT_DIR, "NanumGothic.ttf")
            if os.path.exists(fallback):
                for style in ("", "B"):
                    self.add_font("Pretendard", style, fallback)
            else:
                raise FileNotFoundError(
                    f"폰트 파일 없음: {missing}\n"
                    "fonts/ 폴더에 Pretendard-Regular.ttf / Pretendard-Bold.ttf를 넣어주세요."
                )

    # ── 색상 단축 메서드 ──────────────────────────────────────────────────────
    def _tc(self, rgb): self.set_text_color(*rgb)
    def _fc(self, rgb): self.set_fill_color(*rgb)
    def _dc(self, rgb): self.set_draw_color(*rgb)

    def _hline(self, x1, x2, y, thickness=0.3, color=BORDER):
        self._dc(color)
        self.set_line_width(thickness)
        self.line(x1, y, x2, y)

    # ═══════════════════════════════════════════════════════════════════════════
    # 헤더 / 푸터
    # ═══════════════════════════════════════════════════════════════════════════
    def header(self):
        lm, rm = self.l_margin, self.r_margin
        pw = self.w
        y0 = 5.5

        self.set_xy(lm, y0)
        self.set_font("Pretendard", "", 9)
        self._tc(MUTED)
        self.cell(70, 4.5, "기업 분석 리포트", new_x=XPos.RIGHT, new_y=YPos.TOP)

        self.set_xy(lm, y0 + 5)
        self.set_font("Pretendard", "B", 9)
        self._tc(PRIMARY)
        self.cell(70, 4.5, self.company_name, new_x=XPos.RIGHT, new_y=YPos.TOP)

        right_block_w = 62
        rx = pw - rm - right_block_w
        box_h = 4.5
        self._dc(BORDER)
        self._fc(WHITE)
        self.set_line_width(0.3)
        self.rect(rx, y0, 28, box_h, style="FD")
        self.set_xy(rx, y0)
        self.set_font("Pretendard", "", 8)
        self._tc(MUTED)
        self.cell(28, box_h, "성균관대학교", align="C")

        sdic_x = rx + 30
        self.rect(sdic_x, y0, 16, box_h, style="FD")
        self.set_xy(sdic_x, y0)
        self.cell(16, box_h, "SDIC", align="C")

        self.set_xy(rx, y0 + 5)
        self.set_font("Pretendard", "B", 8)
        self._tc(PRIMARY)
        self.cell(38, 4.5, "AI 재무 컨설팅 어시스턴트", new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.set_font("Pretendard", "", 8)
        self._tc(MUTED)
        self.cell(right_block_w - 38, 4.5, "SDIC TEAM 1", new_x=XPos.RIGHT, new_y=YPos.TOP)

        line_y = y0 + 11
        self._hline(lm, pw - rm, line_y, thickness=0.8, color=PRIMARY)
        self.set_y(line_y + 3)

    def footer(self):
        lm, rm = self.l_margin, self.r_margin
        pw = self.w
        fy = self.h - 11
        self._hline(lm, pw - rm, fy - 1, thickness=0.3, color=BORDER)
        self.set_xy(lm, fy)
        self.set_font("Pretendard", "", 9)
        self._tc(MUTED)
        left_w = (pw - lm - rm) * 0.72
        self.cell(left_w, 5, "본 리포트는 AI 재무 컨설팅 어시스턴트에 의해 자동 생성된 분석 자료입니다.")
        self.cell((pw - lm - rm) * 0.28, 5, "SDIC TEAM 1 · 성균관대학교", align="R")

    # ═══════════════════════════════════════════════════════════════════════════
    # 메인 제목
    # ═══════════════════════════════════════════════════════════════════════════
    def draw_main_title(self):
        lm, rm = self.l_margin, self.r_margin
        self.ln(4)
        self.set_font("Pretendard", "B", 26)
        self._tc(PRIMARY)
        self.cell(0, 13, self.company_name, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font("Pretendard", "B", 26)
        self._tc(TEXT_COL)
        self.cell(0, 13, "기업 분석 리포트", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(3)
        self._hline(lm, self.w - rm, self.get_y(), thickness=0.3)
        self.ln(6)

    # ═══════════════════════════════════════════════════════════════════════════
    # 섹션 제목
    # ═══════════════════════════════════════════════════════════════════════════
    def draw_section_title(self, title: str):
        lm, rm = self.l_margin, self.r_margin
        self.set_font("Pretendard", "B", 13)
        self._tc(PRIMARY)
        self.cell(0, 8, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._hline(lm, self.w - rm, self.get_y(), thickness=0.3)
        self.ln(4)

    # ═══════════════════════════════════════════════════════════════════════════
    # 섹션 1-A — KPI 카드 4개 (최신연도 핵심 수치)
    # ═══════════════════════════════════════════════════════════════════════════
    def draw_kpi_cards(self, financials: dict):
        """최신연도 매출액·영업이익·순이익·영업이익률 카드 4개를 한 줄로 렌더링."""
        if not financials:
            return

        years = sorted(financials.keys(), key=lambda y: int(str(y)))
        last_year  = years[-1]
        prev_year  = years[-2] if len(years) >= 2 else None

        d  = financials[last_year]
        rev  = d.get("매출액",   0)
        op   = d.get("영업이익", 0)
        net  = d.get("순이익",   0)
        op_r = op / rev * 100 if rev else 0

        def yoy(cur, key):
            if prev_year is None:
                return None
            pd = financials[prev_year]
            prev = pd.get(key, 0)
            return (cur - prev) / abs(prev) * 100 if prev else None

        rev_yoy  = yoy(rev, "매출액")
        op_yoy   = yoy(op,  "영업이익")
        net_yoy  = yoy(net, "순이익")
        # 영업이익률 전년 차이 (p 단위)
        if prev_year:
            pd2 = financials[prev_year]
            prev_rev2 = pd2.get("매출액", 0)
            prev_op2  = pd2.get("영업이익", 0)
            prev_opr  = prev_op2 / prev_rev2 * 100 if prev_rev2 else 0
            opr_diff  = op_r - prev_opr
        else:
            opr_diff = None

        lm  = self.l_margin
        eff = self.eff_w
        gap = 4.0
        cw  = (eff - gap * 3) / 4
        card_h = 26.0
        y   = self.get_y()

        cards = [
            (f"매출액 ({last_year}년)",    f"{rev // 100:,}억",  rev_yoy,  False),
            (f"영업이익 ({last_year}년)",   f"{op  // 100:,}억",  op_yoy,   False),
            (f"순이익 ({last_year}년)",     f"{net // 100:,}억",  net_yoy,  False),
            (f"영업이익률 ({last_year}년)", f"{op_r:.1f}%",       opr_diff, True),
        ]

        for i, (label, value, change, is_pct_diff) in enumerate(cards):
            cx = lm + i * (cw + gap)

            # 카드 배경
            self._fc(WHITE)
            self._dc(BORDER)
            self.set_line_width(0.3)
            self.rect(cx, y, cw, card_h, style="FD")

            # 레이블
            self.set_font("Pretendard", "", 8)
            self._tc(MUTED)
            self.set_xy(cx + 3, y + 3)
            self.cell(cw - 6, 4.5, label, align="C")

            # 주요 수치
            self.set_font("Pretendard", "B", 13)
            self._tc(TEXT_COL)
            self.set_xy(cx + 3, y + 8.5)
            self.cell(cw - 6, 7, value, align="C")

            # 전년 대비 변화
            if change is not None:
                arrow  = "↑" if change >= 0 else "↓"
                color  = ACCENT if change >= 0 else RED
                unit   = "p" if is_pct_diff else "%"
                sign   = "+" if change >= 0 else ""
                ch_txt = f"{arrow} {sign}{change:.1f}{unit}"
                self.set_font("Pretendard", "", 8)
                self._tc(color)
                self.set_xy(cx + 3, y + 17.5)
                self.cell(cw - 6, 5, ch_txt, align="C")

        self.set_y(y + card_h + 5)

    # ═══════════════════════════════════════════════════════════════════════════
    # 섹션 1-B — 5개년 재무 데이터 테이블
    # ═══════════════════════════════════════════════════════════════════════════
    def draw_financial_table(self, financials: dict):
        if not financials:
            self.set_font("Pretendard", "", 11)
            self._tc(MUTED)
            self.cell(0, 8, "재무 데이터를 불러올 수 없습니다.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(4)
            return

        lm  = self.l_margin
        eff = self.eff_w
        row_h = 8.5

        cw = [
            eff * 0.09,
            eff * 0.18,
            eff * 0.18,
            eff * 0.18,
            eff * 0.185,
            eff * 0.185,
        ]
        headers = ["연도", "매출액(억원)", "영업이익(억원)", "순이익(억원)", "영업이익률", "순이익률"]

        # ── 헤더행 ─────────────────────────────────────────────────────────
        self._fc(PRIMARY)
        self._dc(PRIMARY)
        self.set_line_width(0)
        self.set_font("Pretendard", "B", 10)
        self._tc(WHITE)
        x = lm
        y = self.get_y()
        for h_txt, w in zip(headers, cw):
            self.rect(x, y, w, row_h, style="F")
            self.set_xy(x, y)
            self.cell(w, row_h, h_txt, align="C")
            x += w
        self.set_y(y + row_h)

        # ── 데이터행 ────────────────────────────────────────────────────────
        years = sorted(financials.keys(), key=lambda y: int(str(y)))
        for idx, year in enumerate(years):
            d   = financials[year]
            rev = d.get("매출액",   0)
            op  = d.get("영업이익", 0)
            net = d.get("순이익",   0)
            try:
                op_rate  = float(op)  / float(rev) * 100 if rev else 0
                net_rate = float(net) / float(rev) * 100 if rev else 0
            except Exception:
                op_rate = net_rate = 0

            def fmt_val(v):
                try:
                    vi  = int(v)
                    neg = vi < 0
                    s   = f"{abs(vi) // 100:,}"
                    return (f"△{s}", True) if neg else (s, False)
                except Exception:
                    return (str(v), False)

            def fmt_rate(r):
                neg = r < 0
                s   = f"{abs(r):.1f}%"
                return (f"△{s}", True) if neg else (s, False)

            rev_s,  rev_n  = fmt_val(rev)
            op_s,   op_n   = fmt_val(op)
            net_s,  net_n  = fmt_val(net)
            opr_s,  opr_n  = fmt_rate(op_rate)
            netr_s, netr_n = fmt_rate(net_rate)

            fill = TABLE_EVEN if idx % 2 == 1 else TABLE_ODD
            x = lm
            y = self.get_y()

            cells_data = [
                (str(year), "C", False, True),
                (rev_s,  "R", rev_n,  False),
                (op_s,   "R", op_n,   False),
                (net_s,  "R", net_n,  False),
                (opr_s,  "R", opr_n,  False),
                (netr_s, "R", netr_n, False),
            ]
            for (txt, align, is_neg, is_year), w in zip(cells_data, cw):
                self._fc(fill)
                self._dc(fill)
                self.rect(x, y, w, row_h, style="F")
                self._dc(BORDER)
                self.set_line_width(0.2)
                self.line(x, y + row_h, x + w, y + row_h)
                if is_neg:
                    self.set_font("Pretendard", "B", 10)
                    self._tc(RED)
                elif is_year:
                    self.set_font("Pretendard", "B", 10)
                    self._tc(PRIMARY)
                else:
                    self.set_font("Pretendard", "", 10)
                    self._tc(TEXT_COL)
                self.set_xy(x + 1, y)
                self.cell(w - 2, row_h, txt, align=align)
                x += w
            self.set_y(y + row_h)

        self.ln(2)
        self.set_font("Pretendard", "", 9)
        self._tc(MUTED)
        self.cell(0, 5, "※ 단위: 억원 / 영업이익률·순이익률은 분석 목적으로 산출한 참고 수치임",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(6)

    # ═══════════════════════════════════════════════════════════════════════════
    # 섹션 2 — 매출액·영업이익·순이익 추이 그래프
    # ═══════════════════════════════════════════════════════════════════════════
    def draw_trend_chart(self, financials: dict):
        """app.py 재무 데이터 탭과 동일한 Plotly 차트를 PNG로 내보내 PDF에 삽입."""
        if not financials:
            return

        years     = sorted(financials.keys(), key=lambda y: int(str(y)))
        yr_labels = [str(y) for y in years]
        rev_vals  = [financials[y].get("매출액",   0) for y in years]
        op_vals   = [financials[y].get("영업이익", 0) for y in years]
        net_vals  = [financials[y].get("순이익",   0) for y in years]

        _bar_w = 0.2
        _bar_clrs = ["#1b5e20", "#4caf50", "#aed581"]

        # ── app.py 와 동일한 Plotly 트레이스 구성 ────────────────────────────
        bar_traces = [
            go.Bar(name="매출액",   x=yr_labels, y=rev_vals, marker_color="#1b5e20", width=_bar_w, showlegend=True),
            go.Bar(name="영업이익", x=yr_labels, y=op_vals,  marker_color="#4caf50", width=_bar_w, showlegend=True),
            go.Bar(name="순이익",   x=yr_labels, y=net_vals, marker_color="#aed581", width=_bar_w, showlegend=True),
        ]
        trend_lines = [
            go.Scatter(name="매출액 추이선",   x=yr_labels, y=rev_vals,
                       mode="lines+markers",
                       line=dict(color="#1b5e20", width=2.5),
                       marker=dict(size=10, color="#1b5e20", line=dict(width=2, color="white")),
                       showlegend=False),
            go.Scatter(name="영업이익 추이선", x=yr_labels, y=op_vals,
                       mode="lines+markers",
                       line=dict(color="#4caf50", width=2.5),
                       marker=dict(size=10, color="#4caf50", line=dict(width=2, color="white")),
                       showlegend=False),
            go.Scatter(name="순이익 추이선",   x=yr_labels, y=net_vals,
                       mode="lines+markers",
                       line=dict(color="#aed581", width=2.5),
                       marker=dict(size=10, color="#aed581", line=dict(width=2, color="white")),
                       showlegend=False),
        ]

        fig = go.Figure(data=bar_traces + trend_lines)
        fig.update_layout(
            barmode="overlay",
            xaxis=dict(tickmode="array", tickvals=yr_labels, ticktext=yr_labels),
            yaxis=dict(title="백만원"),
            height=500,
            width=900,
            margin=dict(l=60, r=30, t=30, b=40),
            paper_bgcolor="white",
            plot_bgcolor="white",
            font=dict(family="Arial, sans-serif", size=12),
            legend=dict(orientation="v", x=1.02, y=1),
        )
        fig.update_yaxes(gridcolor="#e8e8e8", gridwidth=1)

        # ── Plotly → PNG(BytesIO) → PDF 삽입 ────────────────────────────────
        # Windows에서 임시 파일 잠금(WinError 32) 을 피하기 위해
        # 디스크 파일 대신 메모리 버퍼(BytesIO)를 사용한다.
        img_bytes = fig.to_image(format="png", scale=2)
        buf = io.BytesIO(img_bytes)

        img_w = self.eff_w
        self.image(buf, x=self.l_margin, y=self.get_y(), w=img_w)
        # height=500, width=900 비율로 PDF 높이 계산
        img_h = img_w * (500 / 900)
        self.set_y(self.get_y() + img_h + 6)

    # ═══════════════════════════════════════════════════════════════════════════
    # 섹션 3 — Claude 기업 분석 (앱 Claude 분석 탭과 완전 동일한 파싱+스타일)
    # ═══════════════════════════════════════════════════════════════════════════
    def draw_business_analysis(self, analysis: str):
        """앱 Claude 분석 탭과 동일한 파싱 로직 + 스타일로 렌더링."""
        sections = self._parse_analysis(analysis)   # [(num, title, body), ...]

        lm     = self.l_margin
        eff    = self.eff_w
        line_h = 5.5
        indent = 5.5   # 텍스트 좌측 들여쓰기 (초록 바 공간)
        pad_v  = 3.0   # 박스 상하 내부 여백 (mm)

        for i, (num, title, body) in enumerate(sections):
            if not body:
                continue

            # 페이지 넘김 여유 확인
            if self.get_y() + 30 > self.h - self.b_margin:
                self.add_page()

            # ── 번호 + 제목 (앱 탭과 동일: 검정 굵게) ────────────────────
            if i > 0:
                self.ln(8)
            self.set_font("Pretendard", "B", 13)
            self._tc(TEXT_COL)   # #1a1a1a
            self.set_x(lm)
            self.cell(0, 8, f"{num}. {title}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(2)

            # ── 본문: 들여쓰기 후 렌더링 → 초록 왼쪽 바 + 회색 테두리 ──
            y_top = self.get_y()
            self.set_font("Pretendard", "", 10.5)
            self._tc((51, 51, 51))   # #333333
            self.set_xy(lm + indent, y_top + pad_v)
            self.multi_cell(eff - indent - 2, line_h, body,
                            new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            y_bot = self.get_y() + pad_v

            # 초록 왼쪽 굵은 세로 선 (앱: border-left:3px solid #2e7d32)
            self.set_draw_color(46, 125, 50)
            self.set_line_width(1.5)
            self.line(lm + 0.75, y_top, lm + 0.75, y_bot)

            # 회색 박스 외곽선 (앱: border:1px solid #e8e8e8)
            self._dc((232, 232, 232))
            self.set_line_width(0.3)
            self.rect(lm, y_top, eff, y_bot - y_top, style="D")

            self.set_y(y_bot + 6)

    # ═══════════════════════════════════════════════════════════════════════════
    # Claude 분석 텍스트 파싱 — app.py _parse_sections()와 동일한 로직
    # ═══════════════════════════════════════════════════════════════════════════
    _DEFAULT_TITLES = {
        "1": "주요 사업 영역",
        "2": "핵심 제품·서비스",
        "3": "고객 및 시장",
        "4": "성장 전략",
    }

    @staticmethod
    def _strip_markdown(text: str) -> str:
        """마크다운 기호(**, *, #) 제거 — app.py _inline_html과 동일."""
        t = re.sub(r'#+\s*', '', text)
        t = re.sub(r'\*+([^*\n]+)\*+', r'\1', t)
        return t.strip()

    def _parse_analysis(self, analysis: str) -> list:
        """app.py의 _parse_sections()와 완전히 동일한 로직으로 파싱.
        반환: [(num_str, title, body), ...]
        """
        t = re.sub(r'(?m)^#+\s+.+\n?', '', analysis.strip()).strip()
        t = re.sub(r'\*+([^*\n]+)\*+', r'\1', t)
        t = re.sub(r'#+', '', t)

        raw = re.split(r'(?m)^\s*(\d+)\.\s+', t)
        sections = []
        i = 1
        while i + 1 < len(raw):
            num     = raw[i].strip()
            content = raw[i + 1].strip()
            lines   = content.split('\n', 1)
            first   = lines[0].strip()
            rest    = lines[1].strip() if len(lines) > 1 else ''

            if ':' in first:
                ci   = first.index(':')
                cand = first[:ci].strip()
                if len(cand) <= 35:
                    title = cand
                    body  = (first[ci + 1:].strip() + ('\n' + rest if rest else '')).strip()
                else:
                    title = self._DEFAULT_TITLES.get(num, f"항목 {num}")
                    body  = content
            else:
                if len(first) > 40:
                    title = self._DEFAULT_TITLES.get(num, f"항목 {num}")
                    body  = content
                else:
                    title, body = first, rest

            # body가 비면 title을 body로 내리고 기본 제목 사용
            if not body.strip() and title:
                body  = title
                title = self._DEFAULT_TITLES.get(num, f"항목 {num}")

            # body 앞머리의 "제목:" 중복 레이블 제거
            _dup = re.compile(r'^' + re.escape(title) + r'\s*:\s*', re.IGNORECASE)
            body = _dup.sub('', body.lstrip(), count=1).strip()

            sections.append((num, title, self._strip_markdown(body)))
            i += 2

        # fallback: 파싱 실패 시 전체 텍스트를 1번 항목으로
        if not sections:
            clean = self._strip_markdown(analysis)
            sections = [("1", self._DEFAULT_TITLES.get("1", "분석 내용"), clean)]

        return sections


# ═══════════════════════════════════════════════════════════════════════════════
# 공개 API
# ═══════════════════════════════════════════════════════════════════════════════
def generate_report(company_name: str, financials: dict, analysis: str) -> str:
    """PDF 보고서를 생성하고 파일 경로를 반환한다."""
    pdf = ReportPDF(company_name)
    pdf.add_page()

    # 메인 제목
    pdf.draw_main_title()

    # ── 섹션 1: 재무 현황 (KPI 카드 + 연도별 테이블) ─────────────────────────
    pdf.draw_section_title(f"1. {company_name} 연도별 재무 현황")
    pdf.draw_kpi_cards(financials)
    pdf.draw_financial_table(financials)

    # ── 섹션 2: 재무 추이 그래프 ──────────────────────────────────────────────
    pdf.draw_section_title("2. 매출액·영업이익·순이익 추이")
    pdf.draw_trend_chart(financials)

    # ── 섹션 3: Claude 기업 분석 ──────────────────────────────────────────────
    pdf.draw_section_title("3. Claude 기업 분석")
    pdf.draw_business_analysis(analysis)

    output_path = f"{company_name}_report.pdf"
    pdf.output(output_path)
    return output_path


def embed_document(text: str) -> list:
    pass


def _format_report(data: dict) -> str:
    company = data.get("company", "알 수 없음")
    lines   = [f"[ {company} 재무 요약 ]"]
    for year_data in data.get("financials", []):
        year             = year_data.get("year")
        revenue          = year_data.get("revenue")
        operating_profit = year_data.get("operating_profit")
        net_income       = year_data.get("net_income")
        lines.append(
            f"{year}년: 매출 {revenue}조 / 영업이익 {operating_profit}조 / 순이익 {net_income}조"
        )
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# 단독 실행 테스트
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    from data import get_financials

    financials = get_financials("에이피알")
    mock_analysis = """\
1. 주요 사업 영역
에이피알(APR)은 뷰티·패션 브랜드 포트폴리오를 운영하는 글로벌 K뷰티 기업입니다.
피부 관리 디바이스, 스킨케어, 색조 화장품 등 다양한 카테고리를 보유하고 있습니다.

2. 핵심 제품·서비스
메디큐브, 에이프릴스킨, 포맨트, 아떼, NONFICTION 등 다수의 독립 브랜드를 운영합니다.
특히 메디큐브 AGE-R 시리즈는 홈케어 뷰티 디바이스 시장에서 높은 인지도를 확보하고 있습니다.

3. 고객 및 시장
MZ세대(20~35세)를 핵심 타깃으로 하는 글로벌 K뷰티 시장을 공략하고 있습니다.
일본, 미국, 동남아시아를 중심으로 해외 소비자 기반을 빠르게 확장 중입니다.

4. 성장 전략
글로벌 시장 확장 및 디지털 채널 강화를 통해 지속 성장을 추구합니다.
D2C(직접 판매) 비중을 높여 수익성을 개선하고 있습니다.
"""

    path = generate_report("에이피알", financials, mock_analysis)
    print(f"PDF 생성 완료: {path}")
