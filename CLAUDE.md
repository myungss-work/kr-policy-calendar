# kr-policy-calendar

설계 배경과 결정 이유는 [DESIGN.md](DESIGN.md), 설치·사용은 [README.md](README.md).

한국은행·통계청·국회 등 국내 정책·경제 일정을 모아 달력과 표로 보여주는 정적 사이트.

## 구조

```
collectors/          Python 수집기 (GitHub Actions 에서 실행)
  base.py            Event 스키마 + SourceAdapter 인터페이스   ← 함부로 바꾸지 말 것
  dates.py           한글 날짜 표기 정규화                      ← 가장 잘 깨지는 곳
  http.py            robots.txt 확인 + 요청 간격
  pipeline.py        병합 / 중복제거 / 변경감지
  registry.py        어댑터 등록소
  sources/*.py       소스별 어댑터 (여기만 늘어남)
docs/                GitHub Pages 로 서빙되는 정적 사이트
  index.html app.js style.css
  data/*.json        수집 결과 (봇이 커밋함) + manual.json (사람이 편집)
.github/workflows/   cron + 수동 실행
```

## 핵심 설계 결정 (바꾸려면 먼저 상의)

- **서버가 없다.** 수집은 Actions, 저장은 git 커밋, 표시는 정적 파일. DB·백엔드를 도입하지 않는다.
- **런타임에 LLM을 쓰지 않는다.** 수집기는 순수 파서다. Actions 에서 API 호출을 넣으면 별도 과금이 생기고 결과가 비결정적이 된다.
- **소스는 서로 격리된다.** 한 어댑터가 실패해도 다른 소스의 데이터는 그대로 남는다. `optional=True` 인 소스는 실패해도 워크플로가 성공한다.
- **삭제하지 않는다.** 사라진 일정은 지우지 않고 `status=CANCELLED` 로 남긴다. 파서가 깨졌을 때 데이터가 증발하는 걸 막기 위해서다.
- **`locked=true` 는 절대 덮어쓰지 않는다.** 사람이 손으로 확정한 값이 자동 수집보다 우선한다.
- **dedupe_key 는 연-월 단위다.** 발표일이 하루 밀렸을 때 "신규+취소"가 아니라 "일정변경"으로 잡히게 하기 위해서다. 같은 달에 같은 이름 회의가 여러 번 열리는 소스는 `day_level_identity=True` 를 쓴다.

## 자주 쓰는 명령

```bash
python -m collectors.run --list                  # 등록된 소스
python -m collectors.run --only bok --dry-run    # 저장 없이 결과만
python -m collectors.run --only manual rules     # 특정 소스만 수집
python -m collectors.run                         # 전체
python -m http.server -d docs 8000               # 로컬에서 사이트 확인
node --check docs/app.js                         # JS 문법 검사
```

## 에이전트 분담

| 에이전트 | 언제 |
|---|---|
| `source-scout` | 새 기관을 추가하기 전 조사. 코드는 안 씀 |
| `adapter-dev` | 어댑터 구현·수리. 소스별로 병렬 실행 가능 |
| `data-qa` | 수집 결과 검증. 고치지 않고 문제만 보고 |
| `frontend-dev` | docs/ UI 작업 |

새 소스 추가 흐름: `source-scout` 조사 → `adapter-dev` 구현 → `data-qa` 검증 → registry 등록.
어댑터끼리는 서로 의존하지 않으므로 3~4개를 동시에 붙여도 된다.

## 절대 하지 말 것

- robots.txt 가 막은 경로를 우회하지 말 것
- API 키를 코드나 커밋에 넣지 말 것 (Actions secrets 만 사용)
- 확인 못 한 필드명을 추측으로 채우고 `optional=False` 로 바꾸지 말 것
- 검증 안 된 일정을 `status=CONFIRMED` 로 넣지 말 것 — 확신 없으면 `TENTATIVE`
