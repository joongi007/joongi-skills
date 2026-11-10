# open-design — 디자인 시스템 패키지 구조 조사 (2026-09-05)

> **출처**: https://github.com/nexu-io/open-design (Apache-2.0)
> **조회일**: 2026-09-05
> 확인한 파일:
> - `design-systems/` 디렉터리 목록 (GitHub contents API)
> - `design-systems/linear-app/{manifest.json, DESIGN.md, tokens.css}`
> - `design-systems/notion/tokens.css`
>
> 아래 "확인한 것"은 위 파일을 직접 읽은 결과다. "추정"은 그렇게 표시했다.

## 왜 조사했나

"디자인할 때 이 저장소를 참고하게 하자"는 요구. 그런데 저장소가 매우 크다
(README 기준 design-systems 151개 + plugins 277개 + skills 100개 이상,
contents API로 센 `design-systems/` 하위 디렉터리는 **229개**).
스킬에 통째로 넣는 것은 불가능하므로 **무엇을 담고 무엇을 남길지** 정해야 했다.

## 결론 (한 줄)

**229개 패키지가 전부 같은 56개 CSS 커스텀 프로퍼티 이름을 쓴다.**
따라서 스킬은 시스템을 담을 필요가 없다 — **토큰 계약(이름 56개)만 담고,
값은 고른 패키지 하나의 `tokens.css` 만 가져오면 된다.**

## 확인한 것

### 패키지 구조

```
design-systems/<slug>/
  manifest.json     # id, name, category, description, files, preview
  DESIGN.md         # 서술형 디자인 명세
  tokens.css        # CSS 커스텀 프로퍼티
  design-tokens.json / tailwind-v4.css / components.html / preview/ (선택)
```

`linear-app/manifest.json` 실제 값:

```json
{ "schemaVersion": "od-design-system-project/v1",
  "id": "linear-app", "name": "Linear", "category": "Productivity & SaaS",
  "files": { "design": "DESIGN.md", "tokens": "tokens.css",
             "designTokens": "design-tokens.json", "tailwind": "tailwind-v4.css",
             "components": "components.html" },
  "importMode": "normalized" }
```

`"importMode": "normalized"` — 이 값이 토큰 이름이 정규화돼 있다는 신호다.

### 토큰 계약 (핵심 발견)

`linear-app/tokens.css` 와 `notion/tokens.css` 를 대조한 결과 **같은 이름 집합**을 쓴다.
브랜드가 전혀 다른 두 패키지가 같은 계약을 지키므로, 정규화가 실제로 적용돼 있다고 본다.

- surface: `--bg --surface --surface-warm`
- foreground: `--fg --fg-2 --muted --meta`
- border: `--border --border-soft`
- accent: `--accent --accent-on --accent-hover --accent-active`
- semantic: `--success --warn --danger`
- type: `--font-display --font-body --font-mono` / `--text-xs`~`--text-4xl` /
  `--leading-body --leading-tight --tracking-display`
- space: `--space-1..6,8,12` / `--section-y-desktop|tablet|phone`
- shape: `--radius-sm --radius-md --radius-lg --radius-pill`
- depth: `--elev-flat --elev-ring --elev-raised` / `--focus-ring`
- motion: `--motion-fast --motion-base --ease-standard`
- layout: `--container-max --container-gutter-desktop|tablet|phone`

**총 56개.** (`_schema/README.md` 는 404라 명세 문서로 확인한 것이 아니라
두 패키지를 대조해 경험적으로 확인했다. 다른 패키지가 이 계약을 어길 가능성은 남아 있다.)

### 크기

- `DESIGN.md` 한 개가 약 6,500~7,000 단어. **229개를 다 담는 것은 불가능하다.**
- `tokens.css` 한 개는 주석 포함 약 60~90줄. **이건 통째로 가져와도 싸다.**

### 다크 테마 (주의)

`linear-app` 과 `notion` 둘 다 `:root` 블록 하나만 있고 **다크 테마 블록이 없다.**
linear-app은 애초에 다크 네이티브(`--bg: #08090a`), notion은 라이트.
→ **양쪽 테마가 필요한 결과물(아티팩트 등)에서는 반대 테마를 직접 만들어야 한다.**
패키지가 주지 않는다.

## 우리가 내린 설계 결정

| 결정 | 이유 |
|---|---|
| 패키지를 vendoring 하지 않는다 | 229개 × 7,000단어. 사본은 즉시 낡는다 |
| 스킬에는 **토큰 계약 56개**를 인라인한다 | 고정이고 작고 매번 필요하다 |
| 고를 때 **패키지 하나의 `tokens.css` 만** 가져온다 | 60~90줄. `DESIGN.md`는 더 필요할 때만 |
| 슬러그 목록은 스냅샷 + 라이브 조회 병행 | 저장소가 계속 늘어난다. 스냅샷만 두면 낡는다 |

## 라이선스

Apache-2.0. 파일을 복사해 배포하면 라이선스·저작권 고지 의무가 있다.
**우리는 파일을 복사하지 않고 URL로 참조한다.** 토큰 이름(사실의 나열)과
설명용 짧은 인용만 스킬에 들어간다.

## 스킬 반영 상태

- `skills/applying-design-systems/` — 이 조사 결과로 만든 스킬
- `skills/applying-design-systems/references/catalog.md` — 슬러그 스냅샷 (조회일 명시)
