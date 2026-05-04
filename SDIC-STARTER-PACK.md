# SDIC AI 기업 분석 에이전트 — Starter Pack

SDIC 2026 스타터 팩입니다.

## 파일 구조

| 파일 | 담당 역할 | 설명 |
|------|-----------|------|
| `app.py` | UI Lead | Streamlit 화면 |
| `data.py` | Data Lead | DART-FSS API 데이터 수집 |
| `graph.py` | Pipeline Lead | LangGraph 에이전트 파이프라인 |
| `report.py` | Report Lead | Claude 분석 리포트 생성 (3인 팀: Pipeline Lead 겸임) |
| `requirements.txt` | 공통 | 설치 패키지 목록 |
| `CLAUDE.md` | 공통 | 팀 정보 + Claude Code 지시사항 |
| `.env` | 공통 | API 키 (김건희가 제공) |
| `.gitignore` | 공통 | Git 제외 파일 목록 |
| `.gitattributes` | 공통 | 줄바꿈 설정 (Mac/Windows 호환) |

## 1인 1파일 원칙
자기 파일만 수정합니다. 팀원 파일을 건드리면 충돌이 발생합니다.

## 파일 간 연결 구조
```
data.py → graph.py → app.py
                   ↘ report.py
```
- `data.py`의 `get_financials(company_name)` 함수를 `graph.py`가 호출합니다
- `graph.py`의 결과를 `app.py`가 화면에 표시합니다
- **Data Lead와 Pipeline Lead는 함수명을 반드시 맞춰야 합니다: `get_financials(company_name)`**

## 가이드 모음
- [팀 협업 가이드 — Git + Claude Code 워크플로우](https://www.notion.so/34c4292aa5f98165a3cbe42f51e5d09f)
- [코스 안내](https://www.notion.so/3474292aa5f98185ac0ac812d7a32123)
- [과제 2](https://www.notion.so/3524292aa5f98114979ae245f34a3e9a)
- [2주차 세션 체크리스트](https://www.notion.so/3564292aa5f9818991d3d010a3184656)

## 시작하기
1. 소스 제어 패널 → 가져오기(Pull) 클릭
2. `.env` 파일 있는지 확인
3. Claude Code 채팅창에 입력: `requirements.txt 설치하고 streamlit run app.py 실행해줘`

## 6주차 커리큘럼
| 주차 | 목표 |
|---|---|
| 1주차 | 환경 설정 + 첫 commit + 역할 배정 |
| 2주차 | data.py DART 연결 + graph.py 파이프라인 + Claude 분석 연결 |
| 3주차 | graph.py Supervisor 멀티에이전트 아키텍처 |
| 4주차 | report.py RAG + fpdf2 PDF 생성 |
| 5주차 | app.py Plotly 시각화 + LLM 평가 |
| 6주차 | Streamlit Cloud 배포 + 팀 데모 |
