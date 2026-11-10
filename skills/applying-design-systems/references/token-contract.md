# 토큰 계약과 선택 예시

open-design 패키지는 아래 56개 CSS custom property를 공유한다.
카탈로그·조회 근거는 `catalog.md`, 프레임워크 적용은 `integration.md`에 있다.

| 구분 | 토큰 |
|---|---|
| 배경 | `--bg` `--surface` `--surface-warm` |
| 전경 | `--fg` `--fg-2` `--muted` `--meta` |
| 테두리 | `--border` `--border-soft` |
| 강조 | `--accent` `--accent-on` `--accent-hover` `--accent-active` |
| 상태 | `--success` `--warn` `--danger` |
| 글꼴 | `--font-display` `--font-body` `--font-mono` |
| 글자 크기 | `--text-xs` `--text-sm` `--text-base` `--text-lg` `--text-xl` `--text-2xl` `--text-3xl` `--text-4xl` |
| 줄 높이·자간 | `--leading-body` `--leading-tight` `--tracking-display` |
| 간격 | `--space-1` `--space-2` `--space-3` `--space-4` `--space-5` `--space-6` `--space-8` `--space-12` |
| 구역 간격 | `--section-y-desktop` `--section-y-tablet` `--section-y-phone` |
| 모서리 | `--radius-sm` `--radius-md` `--radius-lg` `--radius-pill` |
| 깊이·포커스 | `--elev-flat` `--elev-ring` `--elev-raised` `--focus-ring` |
| 모션 | `--motion-fast` `--motion-base` `--ease-standard` |
| 레이아웃 | `--container-max` `--container-gutter-desktop` `--container-gutter-tablet` `--container-gutter-phone` |

`--accent-on`은 accent 위의 글자색이다. `--fg-2`는 본문, `--muted`와 `--meta`는 보조 정보에 쓴다.
상태를 accent 하나로 표현하지 않고 success/warn/danger를 구분한다.

## 선택 예시

| 화면 유형 | 선택 예시 |
|---|---|
| 제품·SaaS | `linear-app`, `notion`, `figma`, `slack` |
| 개발자 도구 | `github`, `stripe`, `supabase`, `sentry`, `raycast` |
| 소비자 서비스 | `apple`, `airbnb`, `spotify`, `duolingo` |
| 문서·콘텐츠 | `editorial`, `publication`, `mintlify`, `paper` |
| 특정 미감 | `minimal`, `brutalism`, `glassmorphism`, `mono` |

예시는 2026-09-05 확인한 카탈로그 기준이다. 정확한 slug는 카탈로그에서 확인한다.

## 패키지가 제공하지 않는 부분

- 대개 한 테마의 토큰이다. 필요한 두 번째 테마는 같은 토큰 이름으로 보완한다.
- 토큰만으로 layout·정보 구조·컴포넌트·접근성이 완성되지는 않는다.
- 기존 디자인 시스템이 있으면 그 시스템을 먼저 사용한다.
- 네트워크 없이 직접 만든 값을 사용했다면 공식 패키지를 가져온 것처럼 설명하지 않는다.
