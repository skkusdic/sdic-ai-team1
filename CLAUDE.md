# SDIC AI 기업 분석 에이전트 — Team [N]

> **🇰🇷 필수: 이 프로젝트의 모든 응답과 설명은 반드시 한국어로 해주세요.**
> 코드 변수명·함수명은 영어 snake_case, UI 텍스트와 모든 설명은 한국어.

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

**📌 막혔을 때:**
```
[에러 메시지 붙여넣기] 이 에러 해결해줘.
```

---

## 팀 구성 (세션에서 이름 채워넣기)

| 역할 | 이름 | 담당 파일 |
|---|---|---|
| Pipeline Lead | 이수빈 | graph.py |
| Data Lead | 김나은 | data.py |
| UI Lead | 권지연 | app.py |
| Report Lead | [이름] | report.py |

> 3인 팀의 경우 Pipeline Lead가 report.py도 담당.

## 분석 대상 기업
팀에서 합의한 기업: [기업명]

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
- **API 키 하드코딩 금지:** .env 파일에서만 불러오기
- **.env를 git에 커밋 금지**
- **모델 고정:** claude-haiku-4-5만 사용. Sonnet/Opus 호출 금지
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

## 에러가 났을 때 — 개선 루프

에러는 시스템을 더 강하게 만들 기회입니다. 두려워하지 마세요.

1. **파악** — 에러 메시지 전체를 읽는다
2. **붙여넣기** — Claude Code 채팅창에 에러 메시지 그대로 붙여넣기
3. **수정** — Claude가 제안한 수정을 적용한다
4. **확인** — 실제로 작동하는지 확인한다
5. **계속** — 더 강해진 코드로 다음 단계로

> 에러 메시지는 Claude Code의 입력값입니다. 에러가 날수록 코드가 단단해집니다.

---

## 왜 DART API를 코드 스크립트로 짜는가

AI가 모든 걸 직접 처리하려 하면 정확도가 빠르게 떨어집니다.
각 단계의 정확도가 90%라면 → 5단계 후 전체 정확도는 59%로 떨어집니다.

그래서 우리 프로젝트는:
- **DART API 호출, SQLite 저장** → `data.py` 스크립트 (결정론적, 항상 같은 결과)
- **분석, 판단, 자연어 생성** → Claude API (claude-haiku-4-5)

Claude는 판단에 집중하고, 반복 실행은 코드 스크립트에 맡깁니다.
이게 6주 프로젝트 아키텍처의 핵심 원리입니다.
