# 실행 가능한 문서 계약

문서 ID: ARCH-CONTRACTS · 요구사항: REQ-PROCESS, REQ-KNOWLEDGE

이 문서가 설명하는 패키지 버전은 **0.1.0**이다.

<!-- contract: runtime.version = "0.1.0" -->

지원 규격 날짜는 `2026-07-28`, `2025-11-25`, `2025-06-18`이다.

<!-- contract: protocol.versions = ["2026-07-28", "2025-11-25", "2025-06-18"] -->

CLI의 `serve`는 `--host`, `--port`, `--skills-dir`, `--state-dir`, `--help`를 제공한다.
`stdio`는 `--skills-dir`, `--state-dir`, `--profile`, `--mode`, `--url`, `--fallback`, `--help`를 제공한다.
`state`로 저장소 진단·등록 가져오기·백업 복구를 수행한다.
`configure`로 연결 설정을 저장하며 `start/stop/restart/status/open`으로 선택적 웹 실행을 관리한다.

<!-- contract: cli.options = {"serve":["--help","--host","--port","--skills-dir","--state-dir"],"stdio":["--fallback","--help","--mode","--profile","--skills-dir","--state-dir","--url"],"configure":["--fallback","--help","--mode","--profile","--skills-dir","--state-dir","--url"],"start":["--help","--port","--skills-dir","--state-dir"],"stop":["--help","--skills-dir","--state-dir"],"restart":["--help","--port","--skills-dir","--state-dir"],"status":["--help","--skills-dir","--state-dir"],"open":["--help","--port","--skills-dir","--state-dir"],"state":["--help","--import-from","--restore-backup","--skills-dir","--state-dir"],"credentials":["--help","--migrate","--skills-dir","--state-dir"]} -->

## 검사 범위

[contracts.json](../contracts.json)은 검토한 인터페이스 사실과 요구사항별 수용 테스트를 보관한다.
`python3 scripts/check_contracts.py`가 다음을 실제 구현과 대조한다.

- 패키지 버전·VERSION 파일과 문서 주장.
- 각 CLI의 실제 `--help` 출력과 문서의 옵션 목록.
- HTTP dispatch의 method·경로·가변 경로와 문서 계약.
- RPC method 분기 목록과 modern/legacy capability의 실제 반환값.
- 에이전트 탐지·스킬 설치 경로와 설치기 상수.
- 모든 REQ-ID의 설계 문서·수용 테스트가 실제로 존재하는지.
- 여러 문서의 `contract:` 주장이 같은 값을 유지하는지.

RPC 분기 존재는 그 기능의 완전한 적합성 검증이 아니다. 실패 상태·버전별 동작은 연결된
수용 테스트가 검증한다. 자연어 전체의 의미를 자동 증명하는 도구도 아니다. 검사 가능한
주장을 명시적으로 표시하고, 그 밖의 문장은 변경 영향 검토를 통해 판단한다.

## 변경 절차

1. 요구사항·ADR과 구현·수용 테스트를 함께 고친다.
2. `--snapshot`으로 읽기 전용 실제 인터페이스를 확인한다.
3. 바뀐 동작이 의도한 결정인지 검토하고 contracts.json과 영향을 받는 문서 주장을 갱신한다.
4. 문서 검사와 수용 테스트를 실행하고 결과를 검증 기록에 남긴다.

snapshot을 자동으로 계약에 덮어써 검사를 통과시키지 않는다. 기대 계약 변경은 설계 변경이다.

2026 Skills capability의 `directoryRead: true`와 `resources/directory/read` 분기도 검토한 계약이다.
디렉터리 조회 광고와 실제 method 추가가 어긋나면 이 계약을 기준으로 검사한다.
