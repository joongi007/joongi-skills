# refs — 참고 라이브러리

이 폴더는 **스킬을 만들 때 근거로 삼은 외부 자료**를 담는다. 세 종류를 **명확히 구분**한다.

- **A. 참고 자료(assets)**: 구현할 때 꺼내 보는 **최소 실행 예제·코드 스니펫·문서 링크**.
  → 주제마다 폴더 하나. 폴더 안에 `README.md` + 돌려볼 수 있는 파일.
- **B. 개념 시각 설명(concepts)**: 개념을 눈으로 보게 만든 **HTML 문서**.
  → [`concepts/`](concepts/) 에만. 파일명은 `NN-` 순번(번호 클수록 최신). 자료(A)와 섞지 않는다.
- **C. 리서치(research)**: 외부 문서·논문·표준 **조사 종합 노트**.
  → [`research/`](research/) 에 `YYYY-MM-DD-주제.md`.

> 우리가 쓴 프로젝트 문서(작성 규칙·가이드)는 여기 말고 [`docs/`](../docs/) 에 둔다.
> 스킬 본문은 [`skills/`](../skills/) 에 있다. **refs/ 는 `.skill` 번들에 들어가지 않는다.**

## C. 리서치 (research/)

| 날짜 | 문서 | 주제 |
|------|------|------|
| 2026-11-07 | [research/2026-11-07-gtmux-ux-and-skill-language.md](research/2026-11-07-gtmux-ux-and-skill-language.md) | GTMUX에서 추출한 공통 UX 원칙과 스킬 작성 언어의 선택 기준 |
| 2026-11-06 | [research/2026-11-06-usual-korean.md](research/2026-11-06-usual-korean.md) | fluent-korean·im-not-ai·GeekNews를 참고한 자연스러운 한국어와 기술 용어 선택 지침 |
| 2026-11-05 | [research/2026-11-05-infrastructure-quality.md](research/2026-11-05-infrastructure-quality.md) | Valkey·Sentinel·TCP·DB 복구·Kubernetes·Helm·mutation testing과 MCP 규격의 공식 근거 |
| 2026-09-05 | [research/2026-09-05-agent-skills-best-practices.md](research/2026-09-05-agent-skills-best-practices.md) | Anthropic 공식 Skill 작성 지침 — frontmatter 하드 제약, 점진적 공개, 안티패턴 |
| 2026-09-05 | [research/2026-09-05-open-design-design-systems.md](research/2026-09-05-open-design-design-systems.md) | open-design 저장소 구조 조사. 229개 패키지가 공유하는 56개 토큰 계약을 확인 — `applying-design-systems` 스킬의 근거 |
| 2026-09-05 | [research/2026-09-05-owasp-api-top10.md](research/2026-09-05-owasp-api-top10.md) | OWASP API Top 10 2019 vs 2023 대조. 2023판에서 인젝션 항목이 사라지고 권한(API1/3/5)이 상위 — 플레이북 §24 우선순위의 근거 |

## B. 개념 시각 설명 (concepts/)

브라우저로 열어 보는 시각 자료. **같은 개념이면 기존 파일 갱신**, 새 개념이면 새 파일.

| 개념 | 파일 | 무엇 |
|------|------|------|
| 이 저장소가 무엇이고 어떻게 굴러가나 | [concepts/01-how-this-repo-works.html](concepts/01-how-this-repo-works.html) | 3단계 로딩 구조, 길이 예산(무엇이 항상 로드되나), 빌드 파이프라인, refs 규약. 게시본: https://claude.ai/code/artifact/d309e638-7c3c-4486-a70f-0f369fd441a3 |

## A. 참고 자료 (assets)

주제마다 폴더 하나. 각 폴더에 `README.md`(무엇인지 + 출처 링크 + 언제 쓰나)와
**돌려볼 수 있는 최소 예제**를 둔다.

| 주제 | 폴더 | 무엇 | 쓰이는 곳 |
|------|------|------|-----------|
| ReDoS 실측 | [redos-lab/](redos-lab/) | `re`의 파국적 백트래킹을 직접 재현하는 스크립트 + 실측 표 | `web-security.md` §3.8 |
| ASGI 바디 크기 제한 | [asgi-body-limit/](asgi-body-limit/) | Starlette에 없는 바디 크기 제한 미들웨어 최소 구현 + 왜 `BaseHTTPMiddleware`면 안 되는지 | `web-security.md` §4.1, `security-ops.md` §13.1 |

## 규칙

1. **예제는 최소로.** 우리한테 필요한 기능만 남기고 줄인다. 프레임워크 전체 튜토리얼을 복사하지 않는다.
2. **출처를 반드시 적는다.** 문서/논문/repo URL + **조회 날짜**. 원문이 바뀌면 요약은 틀린 게 된다.
3. **원문이 아니라 요약이면 그렇게 밝힌다.** 인용문과 우리 해석을 섞지 않는다.
4. **외부 코드를 가져오면 라이선스와 출처를 README에 기록한다.**
5. **측정한 값은 측정 환경을 같이 적는다.** (CPU·파이썬 버전·날짜) 숫자만 있으면 재현이 안 된다.
6. 새 폴더·문서를 추가하면 **위 색인 표에 한 줄 추가**한다. 색인에 없으면 없는 자료다.
7. 스킬 본문(`skills/`)에서 근거가 필요한 주장은 **여기를 가리킨다.** 반대로 여기 자료가
   스킬에 반영되면 그 사실을 README에 적는다. 양방향으로 연결해야 자료가 썩지 않는다.
