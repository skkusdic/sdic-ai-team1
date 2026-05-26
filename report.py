import os
import re
import anthropic
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
    """에이피알 기업 분석 리포트 PDF 생성기"""

    # ── 헤더 높이 상수 (mm) ──────────────────────────────────────────────────
    _HEADER_H = 28   # 헤더 영역 높이 (content 시작 y)
    _FOOTER_H = 14   # 푸터 영역 높이 (page bottom 기준)

    def __init__(self, company_name: str):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.company_name = company_name
        # 좌우 16mm, 상단 _HEADER_H, 하단 _FOOTER_H
        self.set_margins(left=16, top=self._HEADER_H, right=16)
        self.set_auto_page_break(auto=True, margin=self._FOOTER_H)
        self.eff_w = 210 - 32          # 178mm 유효 너비
        self._register_fonts()

    # ── 폰트 등록 ─────────────────────────────────────────────────────────────
    def _register_fonts(self):
        pairs = [
            ("",  "Pretendard-Regular.ttf"),
            ("B", "Pretendard-Bold.ttf"),
            # fpdf2는 I/B/BI 스타일만 지원 → Medium/SemiBold를 B에 합침
        ]
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
                print(f"⚠  Pretendard 없음 → NanumGothic 대체: {missing}")
            else:
                raise FileNotFoundError(
                    f"폰트 파일 없음: {missing}\n"
                    "fonts/ 폴더에 Pretendard-Regular.ttf / Pretendard-Bold.ttf를 넣어주세요.\n"
                    "다운로드: https://github.com/orioncactus/pretendard/releases"
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
    # 헤더 / 푸터  (fpdf2가 매 페이지 자동 호출)
    # ═══════════════════════════════════════════════════════════════════════════
    def header(self):
        lm, rm = self.l_margin, self.r_margin
        pw = self.w
        y0 = 5.5          # 물리적 상단에서 시작

        # ── 좌측: 레이블 + 기업명 ─────────────────────────────────────────
        self.set_xy(lm, y0)
        self.set_font("Pretendard", "", 9)
        self._tc(MUTED)
        self.cell(70, 4.5, "기업 분석 리포트", new_x=XPos.RIGHT, new_y=YPos.TOP)

        self.set_xy(lm, y0 + 5)
        self.set_font("Pretendard", "B", 9)
        self._tc(PRIMARY)
        self.cell(70, 4.5, self.company_name, new_x=XPos.RIGHT, new_y=YPos.TOP)

        # ── 우측: 로고 박스 + 소속 텍스트 ───────────────────────────────
        right_block_w = 62
        rx = pw - rm - right_block_w

        # 성균관대 텍스트 박스
        box_h = 4.5
        self._dc(BORDER)
        self._fc(WHITE)
        self.set_line_width(0.3)
        self.rect(rx, y0, 28, box_h, style="FD")
        self.set_xy(rx, y0)
        self.set_font("Pretendard", "", 8)
        self._tc(MUTED)
        self.cell(28, box_h, "성균관대학교", align="C")

        # SDIC 텍스트 박스
        sdic_x = rx + 30
        self.rect(sdic_x, y0, 16, box_h, style="FD")
        self.set_xy(sdic_x, y0)
        self.cell(16, box_h, "SDIC", align="C")

        # 두 번째 줄: AI 재무 컨설팅 어시스턴트  SDIC TEAM 1
        self.set_xy(rx, y0 + 5)
        self.set_font("Pretendard", "B", 8)
        self._tc(PRIMARY)
        self.cell(38, 4.5, "AI 재무 컨설팅 어시스턴트", new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.set_font("Pretendard", "", 8)
        self._tc(MUTED)
        self.cell(right_block_w - 38, 4.5, "SDIC TEAM 1", new_x=XPos.RIGHT, new_y=YPos.TOP)

        # ── 구분선 (굵기 0.8mm, primary색) ───────────────────────────────
        line_y = y0 + 11
        self._hline(lm, pw - rm, line_y, thickness=0.8, color=PRIMARY)

        # 다음 content 시작 위치
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
        self.cell(
            left_w, 5,
            "본 리포트는 AI 재무 컨설팅 어시스턴트에 의해 자동 생성된 분석 자료입니다."
        )
        self.cell(
            (pw - lm - rm) * 0.28, 5,
            "SDIC TEAM 1 · 성균관대학교", align="R"
        )

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
    # 섹션 1 — 5개년 재무 데이터 테이블
    # ═══════════════════════════════════════════════════════════════════════════
    def draw_financial_table(self, financials: dict):
        if not financials:
            self.set_font("Pretendard", "", 11)
            self._tc(MUTED)
            self.cell(0, 8, "재무 데이터를 불러올 수 없습니다.", ln=True)
            self.ln(4)
            return

        lm = self.l_margin
        eff = self.eff_w
        row_h = 8.5

        # 컬럼 너비 (합계 = eff_w)
        cw = [
            eff * 0.09,   # 연도
            eff * 0.18,   # 매출액
            eff * 0.18,   # 영업이익
            eff * 0.18,   # 순이익
            eff * 0.185,  # 영업이익률
            eff * 0.185,  # 순이익률
        ]
        headers = ["연도", "매출액(억원)", "영업이익(억원)", "순이익(억원)", "영업이익률", "순이익률"]

        # ── 헤더행 ────────────────────────────────────────────────────────
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

        # ── 데이터행 ──────────────────────────────────────────────────────
        years = sorted(financials.keys())
        for idx, year in enumerate(years):
            d = financials[year]
            rev    = d.get("매출액",   d.get("revenue",          0))
            op     = d.get("영업이익", d.get("operating_profit",  0))
            net    = d.get("순이익",   d.get("net_income",        0))

            try:
                op_rate  = float(op)  / float(rev) * 100 if rev else 0
                net_rate = float(net) / float(rev) * 100 if rev else 0
            except Exception:
                op_rate = net_rate = 0

            def fmt_val(v):
                try:
                    vi = int(v)
                    neg = vi < 0
                    s = f"{abs(vi) // 100:,}"
                    return (f"△{s}", True) if neg else (s, False)
                except Exception:
                    return (str(v), False)

            def fmt_rate(r):
                neg = r < 0
                s = f"{abs(r):.1f}%"
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
                (str(year), "C", False, True),   # 연도
                (rev_s,   "R", rev_n,  False),
                (op_s,    "R", op_n,   False),
                (net_s,   "R", net_n,  False),
                (opr_s,   "R", opr_n,  False),
                (netr_s,  "R", netr_n, False),
            ]
            for (txt, align, is_neg, is_year), w in zip(cells_data, cw):
                # 배경
                self._fc(fill)
                self._dc(fill)
                self.rect(x, y, w, row_h, style="F")
                # 하단 구분선
                self._dc(BORDER)
                self.set_line_width(0.2)
                self.line(x, y + row_h, x + w, y + row_h)
                # 텍스트
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

        # ── 각주 ──────────────────────────────────────────────────────────
        self.ln(2)
        self.set_font("Pretendard", "", 9)
        self._tc(MUTED)
        self.cell(0, 5, "※ 단위: 억원 / 영업이익률·순이익률은 분석 목적으로 산출한 참고 수치임", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(5)

    # ═══════════════════════════════════════════════════════════════════════════
    # 섹션 2 — 사업 분석 카드
    # ═══════════════════════════════════════════════════════════════════════════
    def draw_business_analysis(self, analysis: str):
        sections = self._parse_analysis(analysis)
        lm   = self.l_margin
        eff  = self.eff_w
        gap  = 3.0
        hw   = (eff - gap) / 2   # 절반 너비

        # 카드 메타 (인덱스, 제목, 너비종류, 엑스트라)
        meta = [
            (0, "주요 사업 영역",              "half", None),
            (1, "핵심 제품·서비스",             "half", "tags"),
            (2, "고객 및 시장",                "half", None),
            (3, "경쟁 환경",                   "half", None),
            (4, "성장 전략",                   "full", "strategy_boxes"),
            (5, "사업 전략과 재무 성과 연계 분석", "full", None),
        ]

        # 1~4번 카드: 2열 그리드
        for pair_start in range(0, 4, 2):
            left  = meta[pair_start]
            right = meta[pair_start + 1]
            lt = sections[pair_start]     if pair_start     < len(sections) else ""
            rt = sections[pair_start + 1] if pair_start + 1 < len(sections) else ""

            lh = self._calc_card_h(lt, hw, left[3])
            rh = self._calc_card_h(rt, hw, right[3])
            row_h = max(lh, rh, 35)

            if self.get_y() + row_h > self.h - self.b_margin:
                self.add_page()
            y = self.get_y()

            self._draw_card(lm,            y, hw, row_h, left[0]  + 1, left[1],  lt, left[3])
            self._draw_card(lm + hw + gap, y, hw, row_h, right[0] + 1, right[1], rt, right[3])
            self.set_y(y + row_h + gap)

        # 5~6번 카드: full-width
        for i in range(4, 6):
            m    = meta[i]
            text = sections[i] if i < len(sections) else ""
            ch   = self._calc_card_h(text, eff, m[3])
            ch   = max(ch, 35)

            if self.get_y() + ch > self.h - self.b_margin:
                self.add_page()
            y = self.get_y()
            self._draw_card(lm, y, eff, ch, m[0] + 1, m[1], text, m[3])
            self.set_y(y + ch + gap)

    # ── 카드 높이 계산 ────────────────────────────────────────────────────────
    def _calc_card_h(self, content: str, w: float, extra_type=None) -> float:
        pad      = 4.0
        badge_r  = 2.5
        title_h  = badge_r * 2 + 3.5   # 뱃지 + 제목 높이
        line_h   = 5.2
        text_w   = w - pad * 2 - 1.5

        self.set_font("Pretendard", "", 10)
        try:
            lines = self.multi_cell(text_w, line_h, content, dry_run=True, output="LINES")
            n_lines = len(lines)
        except Exception:
            n_lines = max(1, len(content) // max(1, int(text_w / 3.0)))

        extra_h = {"tags": 14, "strategy_boxes": 18}.get(extra_type, 0)
        return pad + title_h + n_lines * line_h + extra_h + pad

    # ── 카드 1개 렌더링 ───────────────────────────────────────────────────────
    def _draw_card(self, x, y, w, h, number, title, content, extra_type=None):
        pad     = 4.0
        badge_r = 2.5
        line_h  = 5.2

        # 카드 배경 + 테두리
        self._fc(CARD_BG)
        self._dc(BORDER)
        self.set_line_width(0.3)
        self.rect(x, y, w, h, style="FD")

        # 좌측 강조 세로선 (1mm, primary)
        self._fc(PRIMARY)
        self._dc(PRIMARY)
        self.set_line_width(0)
        self.rect(x, y, 1.0, h, style="F")

        # 번호 원형 뱃지
        bcx = x + pad + badge_r + 0.5
        bcy = y + pad + badge_r
        self._fc(PRIMARY)
        self._dc(PRIMARY)
        self.ellipse(bcx - badge_r, bcy - badge_r, badge_r * 2, badge_r * 2, style="F")
        self.set_font("Pretendard", "B", 7)
        self._tc(WHITE)
        self.set_xy(bcx - badge_r, bcy - badge_r)
        self.cell(badge_r * 2, badge_r * 2, str(number), align="C")

        # 카드 제목
        title_x = bcx + badge_r + 2.5
        title_y = y + pad - 0.5
        avail_w = w - (title_x - x) - pad
        self.set_font("Pretendard", "B", 12)
        self._tc(PRIMARY)
        self.set_xy(title_x, title_y)
        self.cell(avail_w, badge_r * 2, title)

        # 내용 텍스트 (multi_cell, 카드 내부 영역에서 출력)
        content_y = y + pad + badge_r * 2 + 3.5
        text_x    = x + pad + 1.5
        text_w    = w - pad * 2 - 1.5
        extra_h   = {"tags": 14, "strategy_boxes": 18}.get(extra_type, 0)
        max_text_h = h - (content_y - y) - pad - extra_h

        self.set_font("Pretendard", "", 10)
        self._tc(TEXT_COL)
        self.set_xy(text_x, content_y)

        # 줄 수 제한 (카드 영역 초과 방지)
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

        # 엑스트라 요소
        if extra_type == "tags":
            self._draw_tags(x, y, w, h, pad, content)
        elif extra_type == "strategy_boxes":
            self._draw_strategy_boxes(x, y, w, h, pad)

    # ── 태그 (핵심 제품·서비스 카드 하단) ───────────────────────────────────
    def _draw_tags(self, cx, cy, cw, ch, pad, content):
        products = [p.strip() for p in re.split(r"[,/·•\n]", content) if p.strip()][:8]
        tag_h = 5.5
        tag_y = cy + ch - tag_h - pad
        tag_x = cx + pad + 1.5

        self.set_font("Pretendard", "", 8)
        for prod in products:
            tw = min(self.get_string_width(prod) + 5, 45)
            if tag_x + tw > cx + cw - pad:
                tag_x = cx + pad + 1.5
                tag_y -= tag_h + 1
            self._fc(TAG_BG)
            self._dc(TAG_BG)
            self.set_line_width(0)
            self.rect(tag_x, tag_y, tw, tag_h, style="F")
            self._tc(PRIMARY)
            self.set_xy(tag_x, tag_y)
            self.cell(tw, tag_h, prod, align="C")
            tag_x += tw + 2.5

    # ── 전략 박스 (성장 전략 카드 하단) ──────────────────────────────────────
    def _draw_strategy_boxes(self, cx, cy, cw, ch, pad):
        strategies = [
            "비즈니스 포트폴리오\n최적화",
            "수익 구조 개선",
            "고객 관계 유지",
            "지역별 포지셔닝",
        ]
        box_h = 14
        box_y = cy + ch - box_h - pad
        g     = 2.5
        avail = cw - pad * 2
        bw    = (avail - g * 3) / 4

        for i, strat in enumerate(strategies):
            bx = cx + pad + i * (bw + g)
            self._fc(PRIMARY)
            self._dc(PRIMARY)
            self.set_line_width(0)
            self.rect(bx, box_y, bw, box_h, style="F")
            self.set_font("Pretendard", "B", 8)
            self._tc(WHITE)
            # 텍스트 2줄 중앙 정렬
            lines = strat.split("\n")
            if len(lines) == 1:
                self.set_xy(bx, box_y + (box_h - 5) / 2)
                self.cell(bw, 5, lines[0], align="C")
            else:
                self.set_xy(bx, box_y + (box_h - 10) / 2)
                self.cell(bw, 5, lines[0], align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                self.set_x(bx)
                self.cell(bw, 5, lines[1], align="C")

    # ═══════════════════════════════════════════════════════════════════════════
    # Claude 분석 텍스트 파싱 → 6개 섹션
    # ═══════════════════════════════════════════════════════════════════════════
    def _parse_analysis(self, analysis: str) -> list:
        sections = [""] * 6
        # 번호+제목 패턴으로 분리
        parts = re.split(r"\n(?=\d+[\.\)、]\s)", analysis)
        if len(parts) >= 6:
            for i, p in enumerate(parts[:6]):
                # 첫 줄(제목) 제거하고 내용만 추출
                body = re.sub(r"^\d+[\.\)、]\s.*?\n", "", p, count=1).strip()
                sections[i] = body or p.strip()
            return sections

        # 키워드 기반 파싱 (fallback)
        kw_map = [
            ["주요 사업", "사업 영역", "사업분야"],
            ["핵심 제품", "제품", "서비스"],
            ["고객", "시장", "타깃"],
            ["경쟁", "경쟁사"],
            ["성장 전략", "전략"],
            ["재무 성과", "연계 분석"],
        ]
        cur = -1
        for line in analysis.split("\n"):
            for idx, keys in enumerate(kw_map):
                if any(k in line for k in keys):
                    cur = idx
                    break
            if cur >= 0:
                sections[cur] += line + "\n"

        # 파싱 실패 시 전체를 첫 섹션에
        if all(s == "" for s in sections):
            sections[0] = analysis

        return [s.strip() for s in sections]


# ═══════════════════════════════════════════════════════════════════════════════
# 공개 API
# ═══════════════════════════════════════════════════════════════════════════════
def generate_report(company_name: str, financials: dict, analysis: str) -> str:
    """PDF 보고서를 생성하고 파일 경로를 반환한다."""
    pdf = ReportPDF(company_name)
    pdf.add_page()

    # 메인 제목
    pdf.draw_main_title()

    # 섹션 1: 5개년 재무 데이터
    pdf.draw_section_title("1. 5개년 재무 데이터")
    pdf.draw_financial_table(financials)

    # 섹션 2: 사업 분석
    pdf.draw_section_title("2. 사업 분석")
    pdf.draw_business_analysis(analysis)

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
        year            = year_data.get("year")
        revenue         = year_data.get("revenue")
        operating_profit = year_data.get("operating_profit")
        net_income      = year_data.get("net_income")
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
피부 관리 디바이스, 스킨케어, 색조 화장품 등 다양한 카테고리를 보유하며
온·오프라인 채널을 통해 국내외 소비자에게 제품을 공급하고 있습니다.

2. 핵심 제품·서비스
메디큐브, 에이프릴스킨, 포맨트, 아떼, NONFICTION 등 다수의 독립 브랜드를 운영합니다.
특히 메디큐브 AGE-R 시리즈는 홈케어 뷰티 디바이스 시장에서 높은 인지도를 확보하고 있습니다.

3. 고객 및 시장
MZ세대(20~35세)를 핵심 타깃으로 하는 글로벌 K뷰티 시장을 공략합니다.
일본, 미국, 동남아시아를 중심으로 해외 소비자 기반을 빠르게 확장 중입니다.

4. 경쟁 환경
아모레퍼시픽, LG생활건강 등 국내 대형 뷰티 기업과 경쟁하며,
글로벌 시장에서는 로레알, 에스티 로더 등과도 경쟁 관계에 있습니다.
멀티 브랜드 전략과 디지털 마케팅이 차별화 포인트입니다.

5. 성장 전략
글로벌 시장 확장 및 디지털 채널 강화를 통해 지속 성장을 추구합니다.
특히 일본·미국·동남아 시장에서 현지화 마케팅을 강화하고 있으며,
D2C(직접 판매) 비중을 높여 수익성을 개선하고 있습니다.

6. 사업 전략과 재무 성과 연계 분석
멀티 브랜드 전략과 해외 시장 다각화가 매출 성장에 긍정적으로 기여하고 있습니다.
디바이스 카테고리의 고마진 구조가 영업이익률 개선을 이끌고 있으며,
지속적인 R&D 투자가 장기 성장 동력으로 작용할 것으로 판단됩니다.
"""

    path = generate_report("에이피알", financials, mock_analysis)
    print(f"PDF 생성 완료: {path}")
