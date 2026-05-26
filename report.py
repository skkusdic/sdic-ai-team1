import io
import os
import re
import tempfile
import anthropic
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from fpdf import FPDF, XPos, YPos
from dotenv import load_dotenv

matplotlib.use("Agg")  # GUI 없는 백엔드

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


# ── matplotlib 한글 폰트 설정 ─────────────────────────────────────────────────
def _setup_mpl_font():
    """matplotlib 한글 폰트 설정 (Pretendard → NanumGothic → 시스템 폴백)."""
    candidates = [
        os.path.join(_FONT_DIR, "Pretendard-Regular.ttf"),
        os.path.join(_FONT_DIR, "NanumGothic.ttf"),
    ]
    for path in candidates:
        if os.path.exists(path):
            fm.fontManager.addfont(path)
            prop = fm.FontProperties(fname=path)
            matplotlib.rcParams["font.family"] = prop.get_name()
            matplotlib.rcParams["axes.unicode_minus"] = False
            return
    # 시스템 폰트 폴백
    for name in ["Apple SD Gothic Neo", "Malgun Gothic", "DejaVu Sans"]:
        if any(name in f.name for f in fm.fontManager.ttflist):
            matplotlib.rcParams["font.family"] = name
            matplotlib.rcParams["axes.unicode_minus"] = False
            return


_setup_mpl_font()


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
        """matplotlib으로 추이 그래프를 그려 PNG로 저장 후 PDF에 삽입."""
        if not financials:
            return

        years = sorted(financials.keys(), key=lambda y: int(str(y)))
        rev_vals = [financials[y].get("매출액",   0) / 100 for y in years]  # 억원
        op_vals  = [financials[y].get("영업이익", 0) / 100 for y in years]
        net_vals = [financials[y].get("순이익",   0) / 100 for y in years]
        yr_labels = [str(y) for y in years]

        # ── 그래프 생성 ──────────────────────────────────────────────────────
        fig, ax = plt.subplots(figsize=(9, 3.8))
        fig.patch.set_facecolor("white")
        ax.set_facecolor("#f9fafb")

        x = range(len(yr_labels))
        bar_w = 0.28

        # 막대: 매출액
        bars1 = ax.bar(
            [i - bar_w for i in x], rev_vals, width=bar_w,
            color="#1a4d3a", alpha=0.85, label="매출액", zorder=3
        )
        # 막대: 영업이익
        bars2 = ax.bar(
            x, op_vals, width=bar_w,
            color="#2d7a57", alpha=0.85, label="영업이익", zorder=3
        )
        # 꺾은선: 순이익
        ax.plot(
            [i + bar_w / 2 for i in x], net_vals,
            color="#e07b39", marker="o", linewidth=2, markersize=5,
            label="순이익", zorder=4
        )

        ax.set_xticks(list(x))
        ax.set_xticklabels(yr_labels, fontsize=10)
        ax.yaxis.set_major_formatter(
            matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}")
        )
        ax.set_ylabel("억원", fontsize=9)
        ax.legend(fontsize=9, loc="upper left", framealpha=0.9)
        ax.grid(axis="y", linestyle="--", alpha=0.5, zorder=0)
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(labelsize=9)

        plt.tight_layout(pad=0.8)

        # ── 임시 PNG 저장 후 fpdf에 삽입 ────────────────────────────────────
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        try:
            fig.savefig(tmp.name, dpi=160, bbox_inches="tight",
                        facecolor="white")
            plt.close(fig)
            tmp.close()

            img_w = self.eff_w
            self.image(tmp.name, x=self.l_margin, y=self.get_y(), w=img_w)
            # 이미지 높이 추정 (9:3.8 비율 → A4 너비 기준)
            img_h = img_w * (3.8 / 9)
            self.set_y(self.get_y() + img_h + 6)
        finally:
            os.unlink(tmp.name)

    # ═══════════════════════════════════════════════════════════════════════════
    # 섹션 3 — Claude 기업 분석 (4섹션 카드)
    # ═══════════════════════════════════════════════════════════════════════════
    def draw_business_analysis(self, analysis: str):
        sections = self._parse_analysis(analysis)  # 최대 4개

        meta = [
            (1, "주요 사업 영역"),
            (2, "핵심 제품·서비스"),
            (3, "고객 및 시장"),
            (4, "성장 전략"),
        ]

        lm  = self.l_margin
        eff = self.eff_w
        gap = 4.0
        hw  = (eff - gap) / 2  # 2열 너비

        # 2열 × 2행 레이아웃
        for pair in range(0, min(4, len(meta)), 2):
            left_meta  = meta[pair]
            right_meta = meta[pair + 1] if pair + 1 < len(meta) else None

            lt = sections[pair]     if pair     < len(sections) else ""
            rt = sections[pair + 1] if pair + 1 < len(sections) else ""

            lh = self._calc_card_h(lt, hw)
            rh = self._calc_card_h(rt, hw) if right_meta else 0
            row_h = max(lh, rh, 32)

            if self.get_y() + row_h > self.h - self.b_margin:
                self.add_page()
            y = self.get_y()

            self._draw_card(lm,            y, hw, row_h, left_meta[0],  left_meta[1],  lt)
            if right_meta:
                self._draw_card(lm + hw + gap, y, hw, row_h, right_meta[0], right_meta[1], rt)

            self.set_y(y + row_h + gap)

    # ── 카드 높이 계산 ────────────────────────────────────────────────────────
    def _calc_card_h(self, content: str, w: float) -> float:
        pad      = 4.0
        badge_r  = 2.5
        title_h  = badge_r * 2 + 3.5
        line_h   = 5.2
        text_w   = w - pad * 2 - 1.5

        self.set_font("Pretendard", "", 10)
        try:
            lines   = self.multi_cell(text_w, line_h, content, dry_run=True, output="LINES")
            n_lines = len(lines)
        except Exception:
            n_lines = max(1, len(content) // max(1, int(text_w / 3.0)))

        return pad + title_h + n_lines * line_h + pad

    # ── 카드 1개 렌더링 ───────────────────────────────────────────────────────
    def _draw_card(self, x, y, w, h, number, title, content):
        pad    = 4.0
        badge_r = 2.5
        line_h  = 5.2

        self._fc(CARD_BG)
        self._dc(BORDER)
        self.set_line_width(0.3)
        self.rect(x, y, w, h, style="FD")

        self._fc(PRIMARY)
        self._dc(PRIMARY)
        self.set_line_width(0)
        self.rect(x, y, 1.0, h, style="F")

        bcx = x + pad + badge_r + 0.5
        bcy = y + pad + badge_r
        self._fc(PRIMARY)
        self._dc(PRIMARY)
        self.ellipse(bcx - badge_r, bcy - badge_r, badge_r * 2, badge_r * 2, style="F")
        self.set_font("Pretendard", "B", 7)
        self._tc(WHITE)
        self.set_xy(bcx - badge_r, bcy - badge_r)
        self.cell(badge_r * 2, badge_r * 2, str(number), align="C")

        title_x = bcx + badge_r + 2.5
        title_y = y + pad - 0.5
        avail_w = w - (title_x - x) - pad
        self.set_font("Pretendard", "B", 12)
        self._tc(PRIMARY)
        self.set_xy(title_x, title_y)
        self.cell(avail_w, badge_r * 2, title)

        content_y  = y + pad + badge_r * 2 + 3.5
        text_x     = x + pad + 1.5
        text_w     = w - pad * 2 - 1.5
        max_text_h = h - (content_y - y) - pad

        self.set_font("Pretendard", "", 10)
        self._tc(TEXT_COL)
        self.set_xy(text_x, content_y)

        try:
            all_lines = self.multi_cell(text_w, line_h, content, dry_run=True, output="LINES")
        except Exception:
            all_lines = content.split("\n")
        max_lines = max(1, int(max_text_h / line_h))
        for line in all_lines[:max_lines]:
            if self.get_y() >= content_y + max_text_h:
                break
            self.set_x(text_x)
            self.cell(text_w, line_h, line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # ═══════════════════════════════════════════════════════════════════════════
    # Claude 분석 텍스트 파싱 → 4개 섹션
    # ═══════════════════════════════════════════════════════════════════════════
    @staticmethod
    def _strip_markdown(text: str) -> str:
        """마크다운 기호(**, *, #) 제거"""
        t = re.sub(r'\*+([^*\n]+)\*+', r'\1', text)
        t = re.sub(r'#+\s*', '', t)
        return t.strip()

    def _parse_analysis(self, analysis: str) -> list:
        """분석 텍스트를 최대 4개 섹션으로 파싱."""
        sections = [""] * 4
        parts = re.split(r"\n(?=\d+[\.\)、]\s)", analysis)

        if len(parts) >= 2:
            for i, p in enumerate(parts[:4]):
                body = re.sub(r"^\d+[\.\)、]\s.*?\n", "", p, count=1).strip()
                sections[i] = self._strip_markdown(body or p.strip())
            return sections

        # 키워드 기반 fallback
        kw_map = [
            ["주요 사업", "사업 영역"],
            ["핵심 제품", "제품", "서비스"],
            ["고객", "시장"],
            ["성장 전략", "전략"],
        ]
        cur = -1
        for line in analysis.split("\n"):
            for idx, keys in enumerate(kw_map):
                if any(k in line for k in keys):
                    cur = idx
                    break
            if cur >= 0:
                sections[cur] += line + "\n"

        if all(s == "" for s in sections):
            sections[0] = analysis

        return [self._strip_markdown(s.strip()) for s in sections]


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
