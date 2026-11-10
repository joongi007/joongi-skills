# awesome-shelf 기반 스킬·MCP 도입 조사

> 성능 해석 정정: 이 초기 조사의 목록 JSON 크기는 실제 모델 토큰이 아니다.
> 클라이언트 검색·지연 로딩·캐시를 포함한 [재측정](2026-11-11-client-tool-loading-evaluation.md)을
> 우선한다. MCP 등록 수가 많다는 이유로 성능이 나쁘다고 판단하거나 CLI 전환을 강제하지 않는다.

조사일: 2026-11-11. 현재 GitHub main의 README를 API로 읽고 로컬 awesome-shelf README와
동일함을 확인했다. 후보 23개 저장소 요청에 대해 원본 README·보관 상태·라이선스 메타데이터와
일부 실제 SKILL 본문을 조회했다. rename 별칭을 포함하므로 고유 프로젝트 23개라는 뜻은 아니다.

이번 작업은 조사·격리 측정이다. 새 공용 MCP나 스킬을 설치하지 않았고 기존 등록을 지우지 않았다.

## 결론과 적용 범위

공용에는 소수의 기본 지침을 유지하고, 외부 기능은 작업·프로젝트에 맞춰 선택한다.
서버 등록 수, 살아 있는 연결 수, 모델에 노출되는 도구 수, 실제 읽은 스킬 본문은 서로 다르다.
MCP는 공통 인터페이스이고 CLI는 호출 방식이다. 어느 하나가 항상 빠르다는 전제는 두지 않는다.

| 후보 | 판단 | 권장 사용 범위·방식 |
|---|---|---|
| 기존 Code Review Graph | 유지 | 프로젝트마다 repo_root 명시, 필요한 프로젝트만 색인 |
| Impeccable·Matt Pocock의 선택 스킬 | 중복 설치 불필요 | WSL Codex·Claude와 Windows Claude에서 주요 스킬 존재 확인. Windows Codex에 모두 있는 것은 아님 |
| Context7 | 우선 검토 | 문서 조회 때만 사용. shell 가능한 코딩 에이전트는 CLI+skill, native MCP가 필요하면 HTTP 방식 중 하나 선택 |
| MarkItDown | 우선 검토 | 문서 변환 때 CLI 또는 stdio MCP. 변환 결과는 필요한 부분만 모델에 전달 |
| Playwright | 우선 검토 | 웹 프로젝트의 CLI+skill 또는 기존 테스트 코드 우선. 지속적인 브라우저 탐색에 native 도구가 유용할 때 MCP |
| diagram-design | 선택 도입 | 공유·발표용 설계도에 명시적으로 호출. 작은 내부 문서는 기존 Mermaid 지침 유지 |
| Three.js game skills | 프로젝트별 | Three.js 게임에서만 사용. Unity·Godot 등 다른 엔진의 공통 규칙으로 배포하지 않음 |
| GSAP·Remotion skills | 프로젝트별 | 해당 라이브러리를 사용하는 프로젝트에서 선택 |
| Blender MCP·Blender skills | 프로젝트별·작업별 | Blender 편집 중에만 연결. 전체 94개 스킬을 공용으로 일괄 설치하지 않음 |
| HWP MCP | 작업별 | HWP 문서 작업 때 사용. 편집은 Windows와 한글 프로그램 필요, 읽기만은 다른 OS에서도 지원 |
| Semgrep·Gitleaks | CLI 우선 | 검토·CI 단계에서 필요할 때 실행. Semgrep MCP가 필요하면 현재 공식 binary 기반 구현 사용 |
| Graphiti | 공용 도입 보류 | 장기 기억·시간 관계 검색이라는 실제 요구가 있을 때 별도 검증 |
| BMAD·Spec Kit | 공용 도입 보류 | 신규 프로젝트에서 개발 프로세스를 선택하는 결정으로 취급 |
| Ponytail·Karpathy 계열 standing prompt | 중복·충돌 평가 후 | 기존 engineering-playbook과 겹치는 원칙을 전체 추가하지 않음 |
| awesome 컬렉션 전체 | 설치 대상 아님 | 탐색용 색인으로 사용하고 개별 패키지를 검증 |

Context7와 Playwright는 awesome-mcp-servers 컬렉션 및 관련 공식 문서에서 확장 조사한 후보다.
awesome-shelf에 각 서버가 직접 등재돼 있다고 표현하지 않는다.

## 근거: 스킬·도구가 많으면 성능이 좋아지는가

[SkillsBench v4](https://arxiv.org/abs/2602.12670v4)는 87개 과제·18개 model-harness 조합에서
선별한 스킬이 평균 성공률을 33.9%에서 50.5%로 높였다고 보고한다. 동시에 모듈 3개 이하로
집중된 스킬이 광범위한 묶음보다 좋았다고 설명한다. 특정 전문 과제와 선별된 스킬의 결과다.

[SWE-Skills-Bench v2](https://arxiv.org/abs/2603.15401v2)는 소프트웨어 개발 과제에서 98개 스킬을
비교했고 92개에 통계적으로 유의한 효과가 없었다. 평균 통과 비율도 76.6%→76.9%였다.
두 연구는 과제·스킬·모델·검증 방식이 다르다. 한쪽의 수치를 모든 개발 작업에 일반화하지 않는다.
이번 후보들이 사용자 프로젝트의 성공률을 높인다는 직접 실험은 아직 하지 않았다.

[Anthropic의 Tool Search 실험](https://www.anthropic.com/research/advanced-tool-use)은
필요한 도구를 검색해 불러오는 방식의 토큰 감소를 보고한다. 해당 API·벤치마크의 결과이며
현재 Hub나 모든 MCP 클라이언트에 같은 감소율을 보장하는 수치는 아니다.
[Code execution with MCP](https://www.anthropic.com/research/code-execution-with-mcp)도
전체 도구 정의와 큰 중간 결과를 처음부터 모델에 넣지 않는 설계를 설명한다.

따라서 추천 기준은 개수보다 필요한 기능의 부재, 설명·출력 크기, 실제 호출 빈도,
프로젝트와 버전의 적합성이다. 작은 스킬도 강제 지침이 충돌하면 품질을 낮출 수 있고,
스킬은 프로세스를 띄우지 않아도 본문을 읽을 때 컨텍스트를 사용한다.

## 현재 Hub 실측

WSL/Linux, Python 3.10.12. 별도의 임시 registry에서 현재 graph MCP만 연결했다.
새 프로젝트 색인·유료 모델 호출은 수행하지 않았다. 기존 캐시의 통계 조회만 사용했다.

| 조건 | 노출 도구 | compact JSON UTF-8 크기 | 추가 upstream 실행 |
|---|---:|---:|---|
| 외부 MCP 없음 | 11 | 2,903 bytes | 없음 |
| MCP 10개 등록, 미연결 | 11 | 2,903 bytes | 없음 |
| Code Review Graph 1개 연결 | 20 | 10,300 bytes | adapter 1개 |
| 동일한 9도구 묶음 10개를 노출하는 합성 예 | 101 | 75,973 bytes | 실제 10개 서버를 띄운 실험은 아님 |

JSON 크기는 tokenizer 결과나 실제 청구 토큰이 아니다. 실제 클라이언트의 지연 로딩·캐시·
도구 추가 metadata에 따라 모델이 읽는 양은 달라진다. 합성 예는 목록 크기의 증가만 보여준다.
모델의 도구 선택 정확도를 측정한 결과가 아니다.

실제 서버 discovery 3회 중앙값은 80.34ms였다. 원본 분석 프로세스의 첫 통계 호출은
3회 중앙값 777.16ms, 이후 조회는 30회 중앙값 16.61ms·p95 18.63ms였다.
이 값은 현재 장비·OS 캐시·부하·선택된 저장소에 한정되며 에이전트 전체 응답 시간은 아니다.

추가 프로세스 RSS 합은 discovery 시 약 20.2MiB, 실제 분석 후 adapter+원본 서버 2개에서
약 124.4MiB였다. Hub 본체는 제외했으며 RSS 합은 공유 페이지를 중복 계산한다.
다른 MCP의 메모리 사용량이나 물리 메모리 증가를 이 수치로 추정하지 않는다.

재현 스크립트와 원자료는 로컬 `.local/integrations/measure-shelf-catalog.py`,
`shelf-catalog-measurement.json`에 있다. 개인 환경 자료이므로 공개 번들에 넣지 않는다.

## 후보별 원본 확인

### 브라우저와 문서 조회

[Playwright MCP](https://github.com/microsoft/playwright-mcp)는 코딩 에이전트에
[CLI+SKILLS](https://github.com/microsoft/playwright-cli)가 더 적합할 수 있다고 직접 안내한다.
MCP는 페이지 구조를 지속적으로 탐색하고 상태를 유지하는 워크플로에 여전히 유용하다.
CLI를 선택해도 Chromium 등 브라우저 프로세스의 메모리와 종료 관리는 별개다.

[Context7](https://github.com/upstash/context7)은 CLI+skill과 MCP 두 방식을 모두 지원한다.
CLI setup은 OAuth/API key 구성을 포함하며 HTTP MCP도 제공한다. 기존의 공식 문서 탐색으로
해결되는 과제에서 매번 강제 호출하지 않고, 버전별 문서가 필요한 때의 추가 경로로 평가한다.

### 문서 변환

[MarkItDown](https://github.com/microsoft/markitdown)의
[공식 MCP](https://github.com/microsoft/markitdown/tree/main/packages/markitdown-mcp)는
`convert_to_markdown(uri)` 한 도구를 제공한다. CLI도 있어 모든 변환에 MCP가 필요하지는 않다.
포맷별 optional dependency를 선택하고 변환 후 전체 문서를 항상 프롬프트에 넣지 않는다.

[HWP MCP](https://github.com/jkf87/hwp-mcp)는 읽기와 편집의 실행 조건을 구분한다.
서버 자체가 Linux에서도 실행된다고 Windows COM 기반 편집까지 가능하다는 뜻은 아니다.

### 스킬의 크기와 적용 조건

[diagram-design](https://github.com/cathrynlavery/diagram-design)의 실제 SKILL.md는
31,164 bytes·394줄이다. 공유용 HTML/SVG 다이어그램에는 적합한 후보지만 매 작업에
강제할 만큼 작은 기본 지침은 아니다. 최초 브랜드 설정 단계가 있고 기존 토큰과 연결해야 한다.
조사 시 skills.sh 표시는 약 26.9K installs, GitHub API는 약 66K stars였으나 효과의 증거로 쓰지 않았다.

[Three.js game skills](https://github.com/majidmanzarpour/threejs-game-skills)는 엔진에 특화된
9개 스킬과 Vite/TypeScript/Three.js 자료를 묶는다. director 본문만 8,968 bytes였다.
게임이라는 이유만으로 다른 엔진에 적용하지 않는다.

[Anthropic webapp-testing](https://github.com/anthropics/skills/tree/main/skills/webapp-testing)은
3,913 bytes의 본문과 Python Playwright 테스트·서버 수명주기 도우미를 제공한다.
이 저장소에는 이미 Node Playwright 테스트가 있으므로 기존 테스트 실행 경로 또는 공식 CLI
스킬 중 하나를 먼저 시험한다. 비슷한 브라우저 스킬을 동시에 중복 도입하지 않는다.

일부 라이선스 메타데이터는 GitHub에서 미식별이었다. 이것만으로 라이선스가 없다고 판단하지
않았다. 예를 들어 현재 Anthropic PDF·DOCX의 개별 LICENSE.txt는 Apache-2.0임을 확인했다.
실제 재배포 시에는 도입하는 파일의 라이선스와 attribution을 따로 확인한다.

### 상시 공용 도입을 보류할 것

[Graphiti](https://github.com/getzep/graphiti)는 지식 그래프·기억 관리 시스템이며
그래프 DB와 모델·임베딩 구성이 추가된다. 코드 그래프와 같은 기능이 아니다.
[BMAD](https://github.com/bmad-code-org/BMAD-METHOD)와
[Spec Kit](https://github.com/github/spec-kit)는 개발 프로세스·프로젝트 산출물을 바꾸는 선택이다.
BMAD 원본은 안정판과 preview 경로도 구분한다. 기존 프로젝트에 묶음 설치하지 않는다.

[Semgrep의 이전 MCP 저장소](https://github.com/semgrep/mcp)는 archived/deprecated이며
현재 구현은 공식 Semgrep binary 쪽으로 이동했다. 옛 저장소를 새로운 MCP 추천으로 사용하지 않는다.
기본 보안 점검은 [Semgrep](https://github.com/semgrep/semgrep)과
[Gitleaks](https://github.com/gitleaks/gitleaks)의 CLI·CI 실행을 먼저 검토한다.

## 운영 권장안

1. 현재 공용 기본 스킬 3개와 기존의 선택 스킬을 유지한다.
2. 새 후보는 하나씩 도입하고 효과가 겹치는 것은 함께 설치하지 않는다.
3. 공용 optional 후보는 등록과 연결을 구분하고 해당 작업에서만 실행한다.
4. 엔진·프레임워크·Blender/HWP 실행 환경에 의존하는 것은 프로젝트나 전용 작업 범위에 둔다.
5. 독립 stdio는 에이전트마다 원본 서버 프로세스를 가질 수 있다. 여러 에이전트를 동시에 사용하는
   시간의 리소스 공유가 필요하면 기존 hybrid/HTTP 옵션을 검토하고, 기본 stdio를 임의 변경하지 않는다.
6. Apps 도구의 native metadata를 숨기는 식으로 토큰만 줄이지 않는다. 호스트의 실제 지원을
   확인하며 현재 native tool 노출 계약을 유지한다.

현재 구현에서 hub_search는 연결된 서버의 도구만 검색한다. 등록만 된 서버의 전체 도구를
연결 없이 검색하는 기능은 구현돼 있다고 가정하지 않는다. native tools/list에도 연결된
도구가 노출되므로 허브 하나를 등록했다고 도구 비용까지 하나로 줄어드는 것은 아니다.

## 사용자 프로젝트에서 효과를 검증하는 방법

동일한 모델·에이전트 버전·프로젝트 스냅샷과 명시적인 수용 조건을 사용한다.
현재 구성과 후보 하나를 추가한 구성을 대표 과제 10~20개에서 짝지어 비교하는 방법을 제안한다.
반복 실행은 warm/cold cache를 구분하고 도입 순서도 바꾼다. 횟수는 비용·변동성을 보고 정한다.

기록할 값은 실제 과제 통과율·잘못된 도구 호출·수정 필요 횟수, 실제 input/output tokens,
전체 시간의 중앙값·p95, 초기 연결 지연, 프로세스 메모리다. 등록 수만으로 판단하지 않는다.
현재 조사는 사용자 프로젝트에서의 유료 LLM A/B 실험까지 수행한 결과는 아니다.
