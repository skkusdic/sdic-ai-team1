# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **🇰🇷 필수: 이 프로젝트의 모든 응답과 설명은 반드시 한국어로 해주세요.**
> 코드 변수명·함수명은 영어 snake_case, UI 텍스트와 모든 설명은 한국어.

---

## 자주 쓰는 명령어

```bash
# 패키지 설치
pip install -r requirements.txt

# 앱 실행
streamlit run app.py

# data.py 단독 테스트 (재무 데이터 출력 확인)
python data.py
```

---

## 처음 시작하는 분들께 — 이 문장들을 채팅창에 그대로 입력하세요

**📌 첫 번째 — 프로젝트 현황 파악:**
```
이 프로젝트가 어떻게 구성되어 있는지 한국어로 설명해줘. 내 역할은 [역할명]이고 담당 파일은 [파일명]이야.
```

**📌 두 번째 — 첫 commit (이름, 역할 바꿔서 입력):**
```
[이름].txt 파일을 만들고 "역할: [역할], 팀: Team [N]" 이라고 적은 다음 'week1: [이름] 온보딩' 메시지로 commit하고 push해줘.
```

**📌 앱 실행:**
```
requirements.txt 설치하고 streamlit run app.py 실행해줘.
```

**📌 파일 올릴 때 (push):**
```
내 [파일명] GitHub에 올려줘. push 전에 git pull --rebase origin main 먼저 실행해줘. 커밋 메시지는 "week[N]: [역할] 완성"으로 해줘.
```

**📌 막혔을 때:**
```
[에러 메시지 붙여넣기] 이 에러 해결해줘.
```

---

## 팀 구성

| 역할 | 이름 | 담당 파일 |
|---|---|---|
| Pipeline Lead | 이수빈 | graph.py |
| Data Lead | 김나은 | data.py |
| UI Lead | 권지연 | app.py |
| Report Lead | 성한동 | report.py |

> 3인 팀의 경우 Pipeline Lead가 report.py도 담당.

## 분석 대상 기업
팀에서 합의한 기업: APR (에이피알)

---

## 프로젝트 구조

**데이터 흐름:**
```
기업명 입력 (app.py)
  → LangGraph Supervisor (graph.py)
    → Data Agent (data.py): DART-FSS API → SQLite
    → Report Agent (report.py): RAG + Claude API → PDF
  → 결과 출력 (app.py)
```

**파일별 담당:**
- `app.py` — Streamlit UI (UI Lead)
- `graph.py` — LangGraph Supervisor 파이프라인 (Pipeline Lead)
- `data.py` — DART API + SQLite + Text2SQL (Data Lead)
- `report.py` — RAG 인덱스 + fpdf2 PDF 생성 (Report Lead)

---

## 현재 구현 상태 (2주차 기준)

| 파일 | 상태 | 비고 |
|---|---|---|
| `app.py` | 골격 완성 | 버튼·입력창만 있음, graph.py 연결 예정 |
| `data.py` | Mock 데이터로 동작 중 | `get_financials()` 구현됨, DART 실연동 TODO |
| `graph.py` | 골격만 있음 | `AnalysisState` TypedDict 정의됨, 노드 연결 TODO |
| `report.py` | 골격만 있음 | `generate_report()` 시그니처만 있음 |

### 파일 간 인터페이스 계약

`data.py`의 `get_financials(company: str) -> dict` 가 반환하는 구조:
```python
{
    2022: {"매출액": int, "영업이익": int, "순이익": int},  # 단위: 백만 원
    2023: {...},
    2024: {...},
}
# 기업명이 없으면 빈 dict {} 반환
```

`graph.py`의 `AnalysisState` 공유 상태:
```python
class AnalysisState(TypedDict):
    company: str       # 기업명
    corp_code: str     # DART 기업 코드
    financials: list   # 재무 데이터
    report: str        # 생성된 리포트 텍스트
```

---

## 기술 스택
- Python 3.11, LangGraph, Claude API (claude-haiku-4-5)
- DART-FSS API, OpenAI Embeddings, NumPy (코사인 유사도)
- SQLite, fpdf2, Streamlit

## 환경 변수 (.env 파일에만, 절대 코드에 직접 X)
- `DART_API_KEY` — https://opendart.fss.or.kr
- `ANTHROPIC_API_KEY` — https://console.anthropic.com

---

## 절대 규칙

- **1인 1파일:** 자기 담당 파일 외 절대 수정 금지. 충돌의 99%는 여기서 발생
- **Push 전 반드시 rebase pull:** `git pull --rebase origin main` 먼저, 그 다음 push. 머지 커밋 방지
- **API 키 하드코딩 금지:** .env 파일에서만 불러오기
- **.env를 git에 커밋 금지**
- **모델 잠금 (학회 비용 정책):** Anthropic API 호출 시 모델은 반드시 `claude-haiku-4-5`만 사용. Sonnet/Opus/이전 Haiku/Claude-3 절대 금지. 직접 `from anthropic import Anthropic` 사용 가능하나 `model="claude-haiku-4-5"` 필수. 편의를 위해 `claude_client.py` 헬퍼 제공 (`from claude_client import ask` — 모델 자동 적용). **CI(`.github/workflows/model-check.yml`)가 push마다 자동 검증** — 코드/문서 어디든 `claude-*` 문자열이 `claude-haiku-4-5`가 아니면 빌드 실패.
- **UI 텍스트:** 전부 한국어

---

## 6주 일정

| 주차 | 목표 |
|---|---|
| 1주차 | 환경 설정 + 첫 commit + 팀 역할 배정 |
| 2주차 | data.py — DART API 연결 + SQLite 저장 |
| 3주차 | graph.py — LangGraph Supervisor 아키텍처 |
| 4주차 | report.py — RAG + fpdf2 PDF 생성 |
| 5주차 | app.py — Plotly 시각화 + LLM 평가 |
| 6주차 | Streamlit Cloud 배포 + 팀 데모 |

---

## 왜 DART API를 코드 스크립트로 짜는가

각 단계의 정확도가 90%라면 → 5단계 후 전체 정확도는 59%로 떨어집니다.

- **DART API 호출, SQLite 저장** → `data.py` 스크립트 (결정론적, 항상 같은 결과)
- **분석, 판단, 자연어 생성** → Claude API (claude-haiku-4-5)
