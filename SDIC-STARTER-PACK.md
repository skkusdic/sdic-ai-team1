# SDIC AI 기업 분석 에이전트 — Starter Pack

SDIC 2026 1주차 세션용 스타터 팩입니다.

## 파일 구조

| 파일 | 담당 역할 | 설명 |
|------|-----------|------|
| `app.py` | UI Lead | Streamlit 화면 |
| `data.py` | Data Lead | DART-FSS API 데이터 수집 |
| `graph.py` | Pipeline Lead | LangGraph 에이전트 파이프라인 |
| `report.py` | Report Lead | Claude 분석 리포트 생성 |
| `requirements.txt` | 공통 | 설치 패키지 목록 |
| `CLAUDE.md` | 공통 | 팀 정보 + Claude Code 지시사항 |
| `.env.example` | 공통 | API 키 형식 샘플 |
| `.gitignore` | 공통 | Git 제외 파일 목록 |
| `.gitattributes` | 공통 | 줄바꿈 설정 (Mac/Windows 호환) |

## 1인 1파일 원칙
자기 파일만 수정합니다. 팀원 파일을 건드리면 충돌이 발생합니다.

## 시작하기
1. .env 파일 생성 (김건희가 제공하는 키 입력)
2. `pip install -r requirements.txt`
3. `streamlit run app.py`

## 주차별 연결 계획
- 1주차: 환경 설정 + 첫 commit
- 2주차: data.py — DART API 연결
- 3주차: graph.py — LangGraph 파이프라인
- 4주차: report.py — Claude 분석
- 5주차: app.py — Plotly 시각화
- 6주차: Streamlit Cloud 배포 + 데모
