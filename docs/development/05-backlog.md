# 확장 후보와 백로그

문서 ID: DEV-BACKLOG · 조사일: 2026-11-15

아래 항목은 제안이며 현재 지원 기능이나 설치 완료 목록이 아니다.
기존 [도입 조사](../../refs/research/2026-11-11-awesome-shelf-integrations.md)와
[클라이언트별 도구 로딩 측정](../../refs/research/2026-11-11-client-tool-loading-evaluation.md)을 함께 본다.

## 외부 지침·검수 도구

| 후보 | 확인한 제공 방식 | 판단·다음 단계 |
|---|---|---|
| ARTEX Global | 자율 침투 테스트 애플리케이션. 확인한 MCP 코드는 외부 서버를 사용하는 클라이언트이며 공식 검사 서버로 등록할 endpoint는 확인하지 못함 | 공용 Hub 기본 등록 보류. 실제 자격증명 없는 격리 Hub에서 별도 검수 실행을 검토 |
| Modern Web Guidance | `modern-web-guidance-src`는 제작·평가 소스, `modern-web-guidance`는 배포용 skill·CLI. 확인한 README·package에는 공식 MCP 서버 실행 방법 없음 | 프론트엔드 작업의 선택형 보완 자료로 우선 검토. MCP 전용 클라이언트 수요가 확인되면 읽기 전용 adapter를 별도 검증 |

Modern Web Guidance는 최신 CSS·HTML·DOM API, 성능·접근성, 브라우저 호환성과 fallback을
검색·조회한다. engineering-playbook의 프로젝트 구조·API·상태 관리·인프라·운영 규칙과
구분해 사용한다. applying-design-systems의 디자인 토큰·제품 UX와도 대체 관계가 아니다.
접근성·보안·성능 일부는 겹치므로 전체 문서를 standing instruction으로 합치지 않는다.
프로젝트 제약·지원 브라우저·기존 디자인 시스템을 먼저 확인하고 필요한 지침만 조회한다.

도입 시 배포본의 버전·출처·Node 요구사항(확인한 package는 Node 22 이상)을 검증한다.
SKILL.md만 복사하면 CLI와 supporting files까지 설치되는 것으로 간주하지 않는다.
외부 스킬의 매 작업 필수 검색·출력 형식 요구도 기존 규칙과 함께 검토한다.
MCP adapter는 검색·본문 조회만 제한적으로 노출하고 임의 CLI 인수·프로젝트 경로 실행을
열지 않는 방향을 검토한다. 현재 설치·등록·adapter 구현은 하지 않았다.

## MCP 탐색·추가 화면

상태: 백로그 · 우선순위: 핵심 연결·인증·승인 흐름 안정화 다음.

목표는 웹 UI에서 외부 후보를 찾고 설정을 검토한 뒤 사용자·프로젝트 범위에 추가하는 것이다.
서버 후보 검색과 현재 연결된 서버의 도구 검색(`hub_search`)은 구분한다.

### 단계

1. **검토한 추천 목록**: 소수 후보에 출처·공식 제공자·전송·실행 환경·인증·용도를 표시한다.
2. **awesome-shelf 가져오기**: `data/shelf.json`을 탐색 원천으로 사용한다. 목록·스킬·CLI·실제 MCP
   서버를 구분하고 중복 저장소를 합친다. README 문자열만으로 실행 명령을 만들어 설치하지 않는다.
3. **외부 검색**: 공식 MCP Registry API를 우선 후보로 검토한다. 별 수·인기·Registry 등재 자체를
   보안 검증으로 표시하지 않는다. shelf 직접 등재와 shelf가 링크한 컬렉션에서 찾은 후보도 구분한다.
4. **검토 후 추가**: 정확한 패키지·버전·endpoint·명령·인수·인증 방식·필요 권한·등록 범위를
   미리 보여준다. 추가·연결·계정 로그인은 각각 구분하고 기존 항목을 조용히 덮어쓰지 않는다.

### 수용 조건

- 후보 목록 조회만으로 MCP 실행·OAuth 로그인·스킬 설치·도구 목록 전체 연결을 하지 않는다.
- 외부 설명은 비신뢰 텍스트로 표시하고 기존 XSS·SSRF·경로·실행 정책을 재사용한다.
- 외부 후보 목록의 메타데이터를 캐시하고 페이지를 나눈다. 공급자 실패·요청 제한·오프라인 상태를 표시한다.
  이 백로그는 현재 등록된 카탈로그의 프로세스별 준비 캐시와 별개다.
- 지원하지 않는 전송·런타임·인증은 등록 전 설명하고, 추가 실패 시 부분 설정을 복구한다.
- 공용·프로젝트 등록 격리, 기존 설정 충돌, 악성 메타데이터, 버전 변경, 제거·재추가를 검증한다.
- 검색 적중률·추가 완료율·실패율·지연·실제 클라이언트 토큰·프로세스 비용으로 효과를 측정한다.
  MCP 등록 개수만으로 성능을 평가하지 않는다.

## 3D 엔진·캐릭터·이미지 제작 후보

상태: 아이디어·미도입 · 확인일: 2026-11-24. MCP 등록·설치·모델 다운로드는 하지 않았다.
현재 `building-procedural-3d`는 Three.js 전용이다. Blender를 지원할 때 공통 제작·렌더 검수 원칙과
엔진별 참조를 나누고, 이미지 생성 지침은 별도 용도로 구분한다. 현재 스킬이 Blender까지 지원한다고 표시하지 않는다.

| 후보 | 제공 방식·검토점 |
|---|---|
| [mcp-for-blender](https://github.com/ahujasid/mcp-for-blender) | 커뮤니티 MCP + Blender addon. Blender Foundation 공식 제품이 아니다. Blender 안의 Python 실행과 인증 없는 addon 소켓 경계를 검토한 뒤 선택형 도입 판단 |
| [blender-skills](https://github.com/arjun988/blender-skills) | Blender MCP를 사용하는 제작 지침 모음. 캐릭터·리토폴로지·UV·리깅·export 등 필요한 참조만 골라 공통 제작 원칙과 엔진별 지침을 분리할 후보 |
| [MPFB](https://static.makehumancommunity.org/mpfb.html) | Blender용 오픈소스 인체 캐릭터 생성기. MCP 자체가 아니며 addon 자동화·생성 에셋 라이선스 확인 필요 |
| [ComfyUI](https://github.com/Comfy-Org/ComfyUI) | 노드 기반 이미지·미디어 제작 엔진. 공식 README의 Comfy MCP 안내를 별도 후보로 검토. 모델·custom node·외부 API·GPU 자원과 각 라이선스는 따로 확인 |

awesome-shelf의 실제 `data/shelf.json`에서 mcp-for-blender·blender-skills·Comfy Cloud를 확인했다.
MPFB와 오픈소스 ComfyUI는 별도로 조사한 후보이며 Comfy Cloud 서비스와 구분한다.
캐릭터·이미지 생성에 동일한 인물·복장·스타일을 유지하는 참조·seed·workflow 기록과 단계별 검수를 검토한다.
Blender MCP를 컨테이너에서 실행해도 명령을 받는 Blender 자체가 격리되는 것은 아니다.
도입 전 임의 Python 실행·파일/에셋 접근·외부 전송과 사용자 승인 범위를 별도로 검토한다.

## 확인한 출처

- [ARTEX 개요](https://github.com/jiwoochris/artex-global), [MCP 클라이언트](https://github.com/jiwoochris/artex-global/blob/main/mcphttp/client.go), [연결·발견 코드](https://github.com/jiwoochris/artex-global/blob/main/server/mcpdiscover.go)
- [Modern Web Guidance 제작 소스](https://github.com/GoogleChrome/modern-web-guidance-src), [배포본·설치 안내](https://github.com/GoogleChrome/modern-web-guidance), [배포 package](https://github.com/GoogleChrome/modern-web-guidance/blob/main/package.json)
- [awesome-shelf](https://github.com/joongi007/awesome-shelf): 2026-11-15 기록에서는 JSON 본문을 확인하지 못했다. 2026-11-24 추가 조회에서는 실제 `data/shelf.json`의 위 3D 후보를 확인했으며 설치·등록은 하지 않았다.
- [공식 MCP Registry](https://github.com/modelcontextprotocol/registry): 서버 카탈로그와 API를 제공한다.


## Codex Security 선택 실행 어댑터

상태: 보류 · 현재 제공: engineering-playbook 검수 가이드. 공식 CLI MCP는 `info`만 제공한다.
[통합 적합성과 수용 조건](../operations/15-codex-security.md)을 충족한 다음에만 구현한다.
별도 worker·프로젝트 snapshot·외부 전송 승인·자격증명 분리·비용/시간 상한·영속 작업 상태·취소·보고서 접근 제어가 필요하다.
공식 scan 접근 권한으로 실제 정상·거부·취소·실패 경로를 검증할 환경이 없으면 지원 완료로 표시하지 않는다.
