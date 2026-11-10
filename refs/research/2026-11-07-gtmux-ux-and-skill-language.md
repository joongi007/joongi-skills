# GTMUX 공통 UX와 스킬 언어

확인 날짜: 2026-11-07. 원문을 복제하지 않고 공통 원칙과 적용 판단을 정리했다.

## GTMUX에서 추출한 원칙

로컬 프로젝트의 `gtmux/docs/DESIGN.md`와 `gtmux/website/content/ko/design.md`를 읽었다.
기존 토큰·컨트롤 재사용, 명확한 설정 label, 작업 상태·실패 원인 표시,
사용자 선택 보존, 키보드·테마·좁은 창에서의 검토를 공통 원칙으로 추출했다.
즉시 적용되는 설정의 switch와 선택·동의를 위한 checkbox는 용도로 구분한다.

적용: `skills/applying-design-systems/references/product-ux.md`.
GTMUX 전용 CLI 스킬·컴포넌트·브랜드 자산·픽셀 크기·서버 동작은 공용 스킬로 복사하지 않았다.
Hub의 단계적 정보 공개는 이 원칙을 현재 제품에 적용한 설계 판단이다.

## 언어 선택의 근거와 한계

- [Agent Skills 규격](https://agentskills.io/specification)은 frontmatter와 Markdown 구조를 정의한다.
  본문 작성 언어를 영어 하나로 강제하는 규칙은 확인하지 못했다.
- [Anthropic의 작성 지침](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)은
  짧은 지침·실사용 검증·필요한 파일만 읽는 progressive disclosure를 강조한다.
- [Beyond English, NAACL Findings 2025](https://arxiv.org/abs/2502.09331)는 35개 언어의 여러 작업에서
  prompt 구성요소별 번역을 비교한다. 번역 전략의 효과가 언어·작업·모델 등의 조건에 의존한다.
- [Behzad 외, EMNLP Findings 2024](https://aclanthology.org/2024.findings-emnlp.916/)는
  영어 문법 판단이라는 제한된 작업에서 영어 이외의 prompt가 더 나은 경우를 보고한다.
  이 결과를 현재 모든 모델의 모든 스킬에 일반화할 수는 없다.

따라서 “영어 스킬이 항상 더 좋다”거나 “한국어가 항상 더 좋다”는 결론은 내리지 않는다.
사용자가 개인 자료의 언어가 섞여 있어 읽기 불편하다고 설명했다.
이에 이 저장소는 설명·지침·제목·표를 한국어로 통일하고 기술 식별자는 원문을 보존한다.
이는 성능 우열이 아닌 개인 자료의 일관성과 유지보수를 위한 선택이다.
한 스킬의 전체 지침을 두 언어로 중복 적재하지 않고 필요한 예시·참조만 추가한다.

성능 차이가 중요한 스킬은 같은 의미의 두 지침을 같은 모델·버전·실제 작업 사례로 비교해야 한다.
지침 준수·결과 정확성·실패 유형과 실제 tokenizer의 입력량을 비교한다.
이번 변경은 모델별 영어/한국어 성능 실험을 수행한 결과가 아니다.
