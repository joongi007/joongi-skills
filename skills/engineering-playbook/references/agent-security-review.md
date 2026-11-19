# 에이전트 개발 결과의 보안 검수

코드·권한·배포·실행 설정을 에이전트로 변경하면 완료 전에 별도 보안 검수 단계를 거친다.
이 플레이북에서 **Codex 개발의 최소 검수는 Codex Security**다. 일반 `/review`·자가 검토·단위 테스트를
Codex Security 실행으로 대체하거나, 실행하지 않은 검사를 통과했다고 기록하지 않는다.
문구만 수정하는 작업에는 코드 스캔을 강제하지 않는다.

## 에이전트별 실행 경로

공식 기능 확인일: 2026-11-19. 제품 이름·이용 조건·현재 노출된 도구를 실행 시 다시 확인한다.

| 개발 도구 | 보안 검수 경로 | 접근할 수 없을 때 |
|---|---|---|
| Codex | Codex Security의 공식 CLI·SDK 또는 연결된 클라우드 저장소/커밋 scan. 연결된 공식 플러그인이 해당 diff/working tree scan을 지원하면 그 범위를 사용한다. | 미실행 사유와 필요한 연결을 기록한다. 대체 검수는 별도로 실행하되 필수 검수 완료로 처리하지 않는다. |
| Claude Code | 프로젝트에서 `/security-review`; 공식 GitHub Action으로 PR 검수를 자동화할 수도 있다. | 지원 버전·계정·명령 접근을 확인하고 미실행을 기록한다. |
| 그 외 | 공급사가 제공하는 보안 전용 검수 기능이 실제로 있으면 사용한다. 없으면 지원 scanner와 별도 보안 리뷰를 조합한다. | 존재하지 않는 명령·MCP·동등한 검수 성능을 만들어내지 않는다. |

Codex Security의 공식 CLI·SDK도 사용할 수 있다. 실제 설치 버전을 고정하고 스캔 권한·인증·소스 전송 범위를 확인한다.
CLI의 공식 MCP는 현재 `info`만 제공하므로 MCP 등록이나 `info` 성공은 스캔 완료가 아니다.
Codex Security는 별도 제품/연동이며 일반 Codex 세션만으로 접근이 보장되지 않는다.
Claude Code의 `/security-review`와 별도 Claude Code Security 서비스도 같은 기능으로 취급하지 않는다.
유료 실행·저장소 연결·외부 업로드가 필요하면 기존 승인 범위와 조직 정책을 확인한다.
필수 기능이 없다는 이유로 승인되지 않은 소스 전송이나 결제를 진행하지 않는다.

## 로컬 실행의 권한 경계

공식 CLI는 로컬 OS 권한으로 실행하며 환경변수를 상속할 수 있고, 스캔 중 사람에게 승인을 묻지 않는다.
비밀 없는 별도 workspace에서 최소 권한으로 실행하고 무관한 API·클라우드 자격증명을 환경에서 제거한다.
scanner 설정은 신뢰한 파일을 명시적으로 선택한다. 특히 CI에서는 검사할 PR checkout 밖에 두어
MCP 실행 명령·모델 제공자·전송 목적지를 비신뢰 저장소가 바꾸지 못하게 한다.
실행 중 자동 권한 심사가 있다는 이유로 OS sandbox나 데이터 반출 통제가 제공된다고 해석하지 않는다.
허브 통합도 같은 경계를 검증해야 한다. 원본 프로젝트 전체와 사용자 홈을 그대로 mount하지 않는다.

## 실행·수정·재검증

1. 변경 범위와 위협 모델을 정한다. 인증·인가·입력·비밀·네트워크·공급망·실행 권한·DoS를 해당 기능에 맞춰 검토한다.
2. 검수할 commit SHA, base/head 또는 patch digest를 고정한다. 클라우드가 저장소에 없는 로컬 수정까지 읽었다고 가정하지 않는다.
3. 사용 가능한 공식 보안 기능으로 검수를 실행하고 완료될 때까지 결과를 확인한다. 시작·대기·실패를 통과로 처리하지 않는다.
4. 발견 사항마다 재현·영향·도달 조건·오탐 근거를 검토한다. scanner의 자동 패치를 바로 운영에 배포하지 않는다.
5. 확인된 중대 취약점을 수정하고 관련 회귀 검사와 보안 검수를 다시 수행한다. 이후의 보안 관련 수정도 검수 범위에 포함한다.
6. 최종 기록에 도구·버전/서비스·대상 SHA·시각·실행 ID/보고서·발견 사항·수정·재검증·미해결 위험을 남긴다.

보안 전용 검수를 실행할 수 없으면 자체 리뷰·SAST·비밀 탐지·의존성/이미지 점검으로 가능한 위험을 줄이고,
**Codex Security 미검수**처럼 남은 단계를 명시한다. 필수 검수 미충족 상태를 출시 완료라고 선언하지 않는다.
예외가 필요한 운영 결정을 에이전트가 임의 승인하지 않는다. 프로젝트 담당자의 사유·범위·만료일을 기록한다.
도구가 통과해도 안전 보증은 아니다. 운영 감지·대응과 [취약점 재점검](vulnerability-management.md)을 함께 유지한다.

## 공식 자료

- [Codex Security 안내](https://help.openai.com/en/articles/20001107-codex-security)
- [공식 CLI와 MCP 범위](https://learn.chatgpt.com/docs/security/cli/reference)
- [공식 SDK](https://learn.chatgpt.com/docs/security/sdk)
- [Codex Security 플러그인](https://openai.com/business/plugins/codex-security/)
- [Claude Code 자동 보안 검수](https://support.anthropic.com/en/articles/11932705-automated-security-reviews-in-claude-code/)
- [Claude Code Security 소개](https://www.anthropic.com/news/claude-code-security)
