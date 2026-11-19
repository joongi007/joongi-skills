# MCP 호환성 계약

문서 ID: ARCH-COMPAT · 요구사항: REQ-PROTOCOL, REQ-APPS, REQ-TASKS

V1/V2는 제품 내 별칭일 뿐이다. 지원 범위는 `2025-11-25`, `2026-07-28`처럼
정확한 규격 날짜와 기능·전송 방식으로 표현한다. 아래 표는 구현 시 검증해야 하는 계약이다.
테스트를 실행하기 전에는 지원 완료로 취급하지 않는다.

<!-- contract: protocol.versions = ["2026-07-28", "2025-11-25", "2025-06-18"] -->

| 항목 | 2025 계열 | 2026-07-28 | Hub 검증 조건 |
|---|---|---|---|
| 초기화 | initialize 기반 협상 | 요청별 version/capabilities, server/discover | 각 방식으로 발견·호출 |
| HTTP | 요청·세션 문맥 처리 | self-contained 요청 | 요청별 독립성과 잘못된 버전 오류 |
| stdio | subprocess JSON-RPC | subprocess JSON-RPC | stdout은 protocol만, stderr는 진단 |
| tools/resources | 목록·schema·호출·조회 | 해당 규격의 목록·호출·조회 | upstream 출처·결과·오류 유지 |
| Apps | 호스트 지원 기능에 의존 | 선택 확장 | metadata·ui resource 전달, 로컬 sandbox 렌더러와 출처별 callback |
| Tasks | 실험적 task 계약 | `io.modelcontextprotocol/tasks` 확장 | 버전별 method/result/state 변환 |
| Skills | resources/tools 기반 조회 | skills/list·skills/get + SHA-256 manifest·directoryRead | 안전한 YAML·text/binary 파일과 디렉터리 조회 |

## 두 연결의 버전을 따로 협상합니다

에이전트가 Hub에 붙는 연결을 downstream, Hub가 외부 MCP 서버에 붙는 연결을 upstream이라고 부릅니다.
예를 들어 에이전트가 2025 규격이어도 Hub는 외부 서버와 2026 규격으로 별도 연결할 수 있습니다.
버전 날짜를 수락하는 것과 모든 확장 기능을 변환할 수 있는 것은 다릅니다. 아래 표의 기능별 제한도 함께 확인하세요.

## 구현한 기능 범위

로컬 스킬은 `hub_search`, `hub_read_skill` 도구와 `skill://` resources로 조회한다.
2026 Skills 확장은 `skills/list`, `skills/get`과 SHA-256 resource manifest를 제공한다.
native manifest는 YAML frontmatter와 텍스트·바이너리 supporting file을 포함한다.
YAML은 SafeLoader로 파싱하며 node 수·깊이·alias 확장과 JSON으로 표현할 수 없는 값을 제한한다.
각 파일의 URI·바이트 크기·SHA-256을 유지하고 바이너리 resource는 base64 blob으로 전달한다.
`directoryRead: true`를 광고하며 `resources/directory/read`로 선택한 디렉터리의 바로 아래 파일과
하위 디렉터리를 조회한다. directory MIME은 `inode/directory`이다. 전체 manifest는 512개 파일·16 MiB,
파일 하나는 1 MiB가 현재 한도다. 경로 이탈·symlink와 내부 제외 경로는 읽지 않는다.

기본 search-first는 stdio·HTTP 공통으로 원본 App 리소스나 명시적 optional/required Task 지원이 있는
upstream 도구만 `서버ID__원래도구명`으로 native `tools/list`에 노출한다. 일반 도구는 검색·정확한 상세 조회 후
`hub_call`로 사용한다. 고급 all-native에서는 현재 선택된 서버의 모든 도구를 직접 노출한다.
원래 input/output schema·annotations·Apps metadata를 보존하며 검색과 `hub_call`도 함께 제공한다.
2025 목록에는 `execution.taskSupport`를 유지하고 Hub가 감쌀 수 있는 노출 도구에는 `optional`을 제공한다.
이 후처리는 기본 노출을 결정하는 근거가 아니다. 필터는 upstream 원본 metadata로 먼저 판정한다.
2025의 `required`·`forbidden`을 호출 시 검사한다. 2026 목록에서는 이전 규격의 `execution`을 제거하고
요청별 Tasks 확장 협상을 따른다. ADR-0005의 전체 native 기본 노출은 [ADR-0015](../adr/0015-search-first-catalog.md)의 검색 중심 정책으로 대체했다.
Apps 도구의 UI metadata는 호스트 preloading에도 사용한다.
metadata와 `ui://` 리소스 URI를 출처별로 매핑한다. 로컬 관리 화면은 공식 AppBridge를
통해 opaque-origin iframe에서 App을 렌더링한다. iframe에는 `allow-scripts`만 부여하며,
리소스가 선언한 network/resource/frame origin으로 응답 CSP를 구성한다.
로컬 App view token은 원래 서버에 묶인다. 원래 도구명으로 요청한 callback도 그 서버로만
전달하므로 다른 연결의 동일한 도구명과 혼동하지 않는다. resource·prompt 요청도 같은 서버를 따른다.
외부 MCP 클라이언트에서는 해당 호스트의 Apps 지원이 필요하다. UI 리소스는 원본 HTML을
고치지 않고 opaque-origin 하위 iframe에 넣는다. relay는 source window를 확인하고 도구명과
resource URI를 원래 서버의 namespace로 전달한다. 응답의 protocol resource URI는 view에
돌려줄 때 원래 URI로 복원한다. 같은 도구명을 가진 서버가 여러 개여도 source가 유지된다.
기존 전역 alias는 유일한 이름일 때만 제공한다.
Apps resource URI는 현재 `_meta.ui.resourceUri`와 이전 `_meta["ui/resourceUri"]`를 모두 인식한다.
로컬 AppBridge는 `tasks/get`·`tasks/result`·`tasks/list`·`tasks/cancel`도 전달하며,
Task를 요청한 App view별로 소유권을 분리한다. 다른 view나 관리 UI에서 만든 작업을
해당 App의 Task RPC로 조회·취소할 수 없다. 이 App 내부 경로는 2025 Task 계약을 검증했다.
2026 App 내부 `tasks/update` 입력 재개는 지원 범위에 포함하지 않는다.

Tasks는 2025 `tasks/get`·`tasks/result`·취소와 2026 `tasks/get` 결과 포함·취소를 처리한다.
2026 remote task의 `input_required`·`inputRequests`를 로컬 작업으로 전달하고,
`tasks/update.inputResponses` 또는 관리 UI의 입력 제출을 원래 remote task로 전달한다.
2026의 MRTR(Multi-Round-Trip Requests, SEP-2322)은 `tools/call`의
`input_required`·`requestState`·`inputResponses` 재요청으로 전달하며,
로컬 UI에서는 같은 흐름을 백그라운드 task로 감싸서 입력·재개한다. 2025 upstream에는
2026 input response 계약을 임의 적용하지 않는다.
외부 서버의 독립적인 sampling·elicitation·subscriptions와 legacy HTTP+SSE 전송은 제공하지 않는다.
Hub 자체 호출 승인에는 2025-11-25 stdio의 form elicitation을 선택적으로 사용한다.
호스트 capability·일회 선택·브라우저 fallback 범위는 [호스트 승인](../operations/12-3d-and-host-consent.md)을 따른다.
작업 실행 PID가 살아 있으면 다른 Hub 프로세스 시작만으로 실패 처리하지 않는다.
실행 PID가 종료된 미완료 작업은 다음 시작 때 실패로 정리하며 실행 재개를 보장하지 않는다. 취소는 이미 수행한 외부 부작용을 되돌리지 않는다.
최대 8개 로컬 작업, upstream task polling 최대 1시간은 현재 구현 한도다.
App view는 10분 후 만료되므로 이를 넘는 작업을 계속 제어하는 기능은 보장하지 않는다.
새 MCP 연결 뒤 외부 호스트에서 native 도구를 쓰려면 `tools/list`를 다시 조회하거나
클라이언트 세션을 새로 열어야 한다. `tools/list_changed` 푸시는 아직 제공하지 않는다.

## 반드시 검증할 조합

downstream 2025 → Hub → upstream 2025와 2026,
downstream 2026 → Hub → upstream 2025와 2026을 각각 실행한다.
지원하지 않는 서버 역방향 sampling/elicitation 요청을 성공으로 숨기지 않는다.
미지원 확장을 광고하지 않고, 변환 손실이 있으면 오류·제한을 표시한다.

Tasks는 새 요청을 만든다고 기존 실행의 취소·재시작·내구성이 자동 해결되지 않는다.
request ID와 task ID를 구분하고, 취소가 실제 upstream까지 전달됐는지 확인한다.
Apps의 `ui://` URI와 CSP·metadata는 출처를 보존해야 하며, 허브의 로컬 관리 화면과
채팅 호스트 내부 App UI는 서로 다른 표면이다.

## 근거와 갱신

2026-11-05 공식 문서 조회. protocol·SDK 버전은 독립적이므로 SDK major를 MCP 규격
버전으로 부르지 않는다. 외부 클라이언트별 지원은 해당 버전의 실제 접속 시험으로 기록한다.

- [2025-11-25 공식 규격](https://modelcontextprotocol.io/specification/2025-11-25)
- [2026-07-28 공식 규격](https://modelcontextprotocol.io/specification/2026-07-28)
- [Tasks 확장](https://modelcontextprotocol.github.io/ext-tasks/specification/2026-07-28/tasks.html)
- [MCP Apps](https://modelcontextprotocol.io/extensions/apps/overview)
- [Skills 작업 그룹·확장 상태](https://modelcontextprotocol.io/community/working-groups/skills-over-mcp)
