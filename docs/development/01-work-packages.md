# 병렬 작업 단위

문서 ID: DEV-WORK · 요구사항: REQ-PROCESS

각 작업의 산출물은 코드와 외부 동작 검증이다. 아래 소유 경계는 초기 분할 기준이며
실제 파일 이름은 구현 구조에 맞춰 조정하되, 동시에 같은 파일을 편집하지 않는다.

| ID | 목적·소유 경계 | 선행 | 독립 수용 테스트 |
|---|---|---|---|
| WP-01 | 스킬 catalog와 검색, 해당 단위 테스트 | 없음 | 설명 검색·본문 조회·symlink/경로 이탈 거부 |
| WP-02 | registry 저장·입력 검증 | 없음 | 저장 후 재시작·중복·잘못된 주소·원자 교체 |
| WP-03 | upstream stdio/HTTP client | WP-02 계약 | fixture 발견·호출·오류·timeout·프로세스 종료 |
| WP-04 | downstream 2025/2026 adapter | WP-01/03 계약 | 버전별 발견·호출·알 수 없는 버전·역방향 요청 |
| WP-05 | task 상태·영속 저장·취소 | WP-03/04 계약 | 정상 전이·중복 취소·오류·재시작·격리 |
| WP-06 | 로컬 UI와 JSON API | API 계약 | 로딩·empty·실패·등록·검색·호출·취소 |
| WP-07 | installer·agent config adapter | Hub CLI 계약 | 임시 HOME에서 감지·재설치·갱신·제거·충돌 |
| WP-08 | Pages·배포 산출물 | WP-07 | 정적 build·상대 경로·설치 스크립트·비밀 미포함 |
| WP-09 | 플레이북·출처·문서 | 없음 | routing·§번호·경로·정확한 조건·source 조회일 |
| WP-10 | 통합·보안·완료 증거 | WP-01~09 | 버전 교차 조합·실제 사용자 흐름·회귀 검증 |

| WP-11 | upstream 인증·discovery·토큰 보관 (`auth.py`, fixture) | WP-02/03 계약 | PKCE·issuer·resource·갱신·철회·device polling·비밀 미노출 |
| WP-12 | 프로젝트 카탈로그·상태 경계 (`profiles.py`) | WP-01/02 계약 | 선택·override·URI·경로·stdio 세션 범위 고정 |
| WP-13 | 스킬 계획·고정 (`skill_management.py`) | WP-07/12 계약 | 스냅샷·수정 보호·lockfile·재사용 거절·복구 |
| WP-14 | 인증·프로젝트·설치 UI 수용 | WP-11~13 API 계약 | 실제 OAuth popup·범위 전환·격리·설치·390px 화면 |

## 병렬 wave

wave A: WP-01, WP-02, WP-07의 감지·보존 로직, WP-09.
wave B: WP-03, WP-04, WP-05, WP-06을 확정한 계약과 fixture로 나눠 진행.
wave C: WP-07 연결 등록, WP-08, WP-10. mock 성공만으로 통합을 완료하지 않는다.

## 작업별 실패 기준

- WP-01: catalog 바깥 파일을 읽거나 이름 중복으로 임의 스킬을 선택하면 실패.
- WP-03: upstream 하나의 timeout이 모든 검색을 멈추거나 orphan process가 남으면 실패.
- WP-04: 2025 initialize만 구현하고 2026 지원이라고 표시하면 실패.
- WP-05: 취소 표시만 바뀌고 실제 실행이 계속되는 경우 의미와 한계를 숨기면 실패.
- WP-06: 예시 데이터가 실제 연결 상태처럼 표시되거나 오류가 사라지면 실패.
- WP-07: 기존 사용자 설정이나 수정 파일을 덮어쓰고 제거하면 실패.
- WP-08: 배포 전 URL을 이미 공개된 설치 주소처럼 안내하면 실패.

## 변경 제안의 위치

새 기능에는 REQ-ID와 사용자 흐름을 추가하고 관련 WP만 확장한다.
새 protocol 확장은 WP-03/04/05 계약과 WP-10 조합표를 함께 갱신한다.
테스트 범위가 겹치더라도 수정 파일 소유자는 하나로 유지한다.
