# Codex Security와 Hub 연동 검토

문서 ID: OPS-CODEX-SECURITY · 확인일: 2026-11-19

**현재 Hub에 Codex Security 스캔 실행기를 추가하지 않았다.** 엔지니어링 플레이북을 Hub 스킬로 읽어
검수 절차를 따를 수 있다. 아래는 공식 기능과 추가 실행 어댑터의 도입 조건을 구분한 검토다.

## 공식 지원 범위

| 경로 | 가능 범위 | Hub에서의 의미 |
|---|---|---|
| 공식 CLI MCP | 읽기 전용 `info` | 설치·메타데이터 확인. 실제 스캔 기능으로 표시하면 안 된다. |
| 공식 CLI·TypeScript SDK | 저장소·경로·변경분 스캔 | 별도 로컬 실행기 구축은 가능하지만 권한·격리·작업 수명 관리가 필요하다. |
| 공식 클라우드 서비스·플러그인 | 연결한 저장소 검수 | 계정 권한과 저장소 연결이 필요하다. ChatGPT 플러그인 연결이 Hub에 자동 이전되지는 않는다. |
| Hub의 engineering-playbook 스킬 | 공식 검수 경로와 완료 기준 안내 | 현재 제공 경로. 스캔을 대신 실행하거나 통과 여부를 보증하지 않는다. |

공식 CLI의 `mcp add`는 에이전트 설정을 변경하는 등록 명령이다. 이를 stdio MCP 서버 실행 명령으로
추측해 Hub에 넣지 않는다. 공식 CLI MCP는 현재 스캔·인증·export·patch를 제공하지 않는다.
직접 보안 검수를 실행할 때는 [공식 quickstart](https://learn.chatgpt.com/docs/security/cli)를 따라
접근 권한·인증·설치 버전을 확인한다. `npx`를 기본 도구 호출에서 자동 설치·업데이트하는 동작은 추가하지 않았다.

## 적합성 판단

개인/조직 내부의 승인된 프로젝트를 반복 검수하는 **선택 통합**으로는 적합하다.
현재의 검색 중심 Hub에 기본 실행 도구로 넣기에는 스캔 범위와 자원·비밀 노출 위험이 크다.
단순 조회 MCP는 이 요구를 해결하지 못하므로 무의미하게 기본 등록 수를 늘리지 않았다.

실행 어댑터가 필요하면 공식 SDK를 고정한 별도 worker가 scan을 수행하고, Hub는 승인·작업 식별자·상태·취소를 맡는다.
공식 MCP가 스캔을 제공하지 않는다는 사실을 우회해서 비공개 웹 API·브라우저 쿠키를 재사용하지 않는다.
허브가 자체 스캔 기능을 만들 경우에도 OpenAI 공식 MCP라고 부르지 않는다.

## 실행 어댑터를 추가하기 전 충족할 조건

| 위험 | 필요한 제어·검증 |
|---|---|
| 다른 프로젝트·홈·키 파일 읽기 | 소유자가 고정한 프로젝트 ID만 입력으로 받는다. 실제 경로·symlink·중첩 경계를 검증하고 지정 snapshot만 별도 실행 환경에 전달한다. |
| 소스·비밀 외부 전송 | 제공자·조직·저장소·대상 SHA/patch·전송 범위·결과 보관·비용을 승인 화면에 표시한다. 스캔 승인을 일반 읽기 세션 허용으로 대체하지 않는다. |
| 검사 과정의 코드 실행 | scanner는 OS 권한으로 동작하고 중간 승인을 묻지 않는다. 허브와 분리한 계정/컨테이너/VM, 최소 mount·네트워크·credential을 적용한다. Hub의 upstream 프로세스 제한만으로 자식 scanner의 안전성을 주장하지 않는다. |
| 설정·prompt injection | 신뢰된 scanner 설정은 검사 대상 checkout 밖에 둔다. repo/PR의 설정으로 MCP·provider·명령을 바꾸지 않는다. 임의 CLI 인자·프롬프트·URL·환경변수를 도구 입력으로 받지 않는다. |
| 토큰 유출·사용자 혼합 | 사용자/조직별 credential을 분리한다. Hub 토큰·GitHub 전체 권한·기존 upstream OAuth를 scanner에 넘기지 않는다. 검색·결과·로그에도 토큰을 넣지 않는다. |
| 비용·시간·동시 실행 | 허용 예산·동시 작업·실행 시간·출력 크기에 상한을 둔다. 취소 시 자식 프로세스까지 종료하고 실제 과금 상한 특성을 검증한다. |
| 긴 실행·중복 과금 | 영속적인 job ID·멱등키·대기/실행/성공/실패/취소 상태를 둔다. MCP Task 기능은 양쪽 지원을 확인하며, 지원하지 않는 클라이언트에는 상태 조회를 제공한다. timeout 뒤 자동 재실행하지 않는다. |
| 민감한 보안 보고서 | 결과를 인증된 프로젝트 소유자에게만 제공한다. 원문 코드는 검색 index·사용 통계에 넣지 않고 크기·보관·삭제·UI escape를 검증한다. |
| 자동 수정·외부 쓰기 | scan 전용으로 시작한다. patch·PR 게시·이슈 생성·운영 배포는 별도 권한과 승인으로 분리한다. |
| 권한 우회·검수 오인 | API key·유료 플랜이 기능 접근을 보장하지 않는다. 시작·dry-run·mock·`info`·자가 리뷰를 실제 보안 검수 통과로 표시하지 않는다. |

위 표는 구현 완료된 보안 보장이 아니라 **향후 실행 어댑터의 수용 조건**이다.
Daybreak의 고급 접근 권한을 사용한다면 승인된 내부 사용자/프로젝트 범위를 지키고,
공개 Hub를 통한 제3자 접근 재판매·공유 기능으로 확장하지 않는다.

## 현재 검수 상태

이번 환경에는 Codex Security CLI와 연결된 보안 스캔 도구가 확인되지 않았다.
플러그인 검색에서도 연결 가능한 Codex Security/Daybreak Defense Factory 항목을 찾지 못했다.
따라서 이 변경을 **Codex Security 검수 완료**로 표시하지 않는다. 저장소의 회귀 검사·독립 리뷰는 별도 검증이다.
CLI가 없거나 인증되지 않았다는 사실은 소스가 안전하다는 근거도, 접근 승인이 영구 불가능하다는 의미도 아니다.

실행 절차와 필수 검수 미충족 시 기록은
[에이전트 보안 검수 가이드](../../skills/engineering-playbook/references/agent-security-review.md)를 따른다.

## 공식 근거

- [CLI 명세·MCP 범위·로컬 실행 권한](https://learn.chatgpt.com/docs/security/cli/reference)
- [TypeScript SDK·진행·취소·출력](https://learn.chatgpt.com/docs/security/sdk)
- [공식 공개 소스](https://github.com/openai/codex-security)
- [클라우드 Codex Security](https://help.openai.com/en/articles/20001107-codex-security)
- [Daybreak 승인 범위](https://help.openai.com/en/articles/20001258-openai-daybreak-trusted-access-for-cyber-overview)
