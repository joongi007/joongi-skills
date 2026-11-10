# 공식 MCP SDK 실접속 검증

문서 ID: OPS-SDK · 요구사항: REQ-PROTOCOL, REQ-SKILL, REQ-CALL

Hub의 자체 fixture 테스트와 별도로 수정하지 않은 공식 TypeScript SDK 클라이언트가
실제 Hub 프로세스와 통신한다. SDK나 SDK의 schema validator를 바꾸거나 우회하지 않는다.
외부 Claude·Codex 등의 제품 UI에 실제 로그인하여 확인한 결과와는 구분한다.

## 실행

Node 22 이상과 Python 3.10 이상을 사용한다. 저장소의 개발 의존성으로 설치한다.

```bash
npm ci
npm run test:sdk
```

개발 의존성을 별도 디렉터리에 이미 설치했다면 다음처럼 지정한다.

```bash
JOONGI_NODE_MODULES=/tmp/joongi-mcp-sdk/node_modules node tests/sdk_interop.cjs
```

`JOONGI_NODE_MODULES`는 `@modelcontextprotocol/` 패키지들이 있는 node_modules 경로다.
Python 실행 파일은 `PYTHON`으로 지정할 수 있다. 임시 skills/state만 생성하며 실제 홈이나
에이전트 설정을 변경하지 않는다. HTTP 검증은 localhost socket을 열 수 있어야 한다.

## 실제 검증한 조합

2026-11-05 Linux/WSL, Python 3.10.12, Node 22.13.0에서 다음 네 조합이 통과했다.

| 공식 클라이언트 | wire 규격 | 전송 | 결과 |
|---|---|---|---|
| `@modelcontextprotocol/sdk` 1.32.2 | 2025-11-25 | stdio subprocess | 통과 |
| `@modelcontextprotocol/sdk` 1.32.2 | 2025-11-25 | Streamable HTTP | 통과 |
| `@modelcontextprotocol/client` 2.4.0 | 2026-07-28 | stdio subprocess | 통과 |
| `@modelcontextprotocol/client` 2.4.0 | 2026-07-28 | Streamable HTTP | 통과 |

공식 Client 2.4.0의 기본 모드는 legacy다. 현대 규격 검증에서는 문서화된
`versionNegotiation: {mode: {pin: '2026-07-28'}}` 옵션을 사용하고, 결과 era가 실제로
modern인지 확인한다. legacy로 조용히 fallback해서 현대 규격 통과처럼 기록하지 않는다.

## 검증 내용

- 서버 identity와 연결, 도구 목록, 로컬 스킬 검색.
- resources 목록·SKILL.md·참조 파일 조회.
- Hub가 연결한 실제 upstream subprocess 도구 발견·호출.
- namespace된 prompt 목록과 prompt 본문 조회.
- legacy ping. modern에서는 SDK가 제거된 ping 호출을 거절하는지 확인.
- 현대 SkillsClient의 목록·직접 lookup과 manifest 검증.
- folded YAML description과 중첩 string metadata 보존.
- SKILL.md·참조 문서·binary asset의 byte size와 SHA-256 검증.
- `resources/directory/read`와 원격 MCP가 제공한 native skill의 무결성 검증.

SDK의 `SkillsClient.read()`가 직접 검증하므로 서버와 테스트가 같은 hash helper를
공유해서 잘못된 바이트를 서로 맞췄다는 식의 검증이 아니다. 테스트는 metadata의
문자열 map 등 Agent Skills의 유효한 frontmatter 규칙도 따른다.

## 발견해 수정한 계약 오류

첫 공식 SDK 실행은 2026 `tools/list`에 필수인 `ttlMs`, `cacheScope` 누락을 잡았다.
그다음 실행은 원격 skill URI를 통째로 opaque 문자열로 감싸면서 `/SKILL.md`와
skill 디렉터리 구조가 사라지는 문제를 잡았다. Hub가 필수 cache field를 제공하고
namespace URI에서도 원래 skill 경로를 보존하도록 수정한 후 네 조합이 모두 통과했다.

이 기록은 해당 SDK 버전·기능의 상호 운용 증거다. 전체 MCP conformance 인증이나
모든 에이전트 제품·인증 제공자·App의 무수정 호환성을 의미하지 않는다.

공식 구현 출처: [TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk).
