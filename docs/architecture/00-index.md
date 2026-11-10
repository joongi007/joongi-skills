# 아키텍처 안내

- [구성요소·상태·흐름](01-components.md)
- [프로토콜 호환성](02-compatibility.md)
- [신뢰 경계와 보안](03-security.md)
- [실행 가능한 문서 계약](04-contracts.md)
- [연결 방식과 선택적 웹 실행](../operations/06-connection-modes.md)
- [설계 결정](../adr/00-index.md)

용어: **Host**는 AI 애플리케이션, **downstream client**는 Hub에 연결하는 MCP client,
**upstream server**는 Hub가 연결하는 MCP server다. Hub는 두 방향의 역할을 함께 가진다.
**스킬**은 지침·참조 문서, **도구**는 실행 가능한 MCP tool이다.
**발견**은 목록·설명·schema 조회, **실행**은 도구 호출이며 별도의 동작이다.
