# 토큰을 프로젝트에 붙이기

## 목차

- 공통 원칙
- 순수 HTML / 아티팩트 한 파일
- Vite + React + TypeScript
- Tailwind 4
- MUI 7
- 다크 테마 만들기 (패키지가 안 준다)
- 검증

## 공통 원칙

1. **`tokens.css` 는 손대지 않고 그대로 둔다.** 고칠 게 생기면 그 아래에 덮어쓰는
   블록을 따로 둔다. 원본을 수정하면 나중에 패키지를 갱신할 때 뭘 바꿨는지 모른다.
2. **컴포넌트는 토큰만 참조한다.** 컴포넌트 안의 리터럴 색상 하나가 시스템 교체를 깨뜨린다.
3. **토큰을 새로 만들지 않는다.** 56개로 부족하면 대개 잘못 매핑한 것이다.
   정말 필요하면 `--app-` 접두사를 붙여 출처를 구분한다.

## 순수 HTML / 아티팩트 한 파일

패키지 `tokens.css` 내용을 `<style>` 최상단에 붙여넣고 그 아래에 페이지 CSS를 쓴다.
아티팩트는 외부 스타일시트를 못 불러오므로 인라인이 유일한 방법이다.

```html
<style>
  /* ── open-design/<slug>/tokens.css (그대로 붙여넣음) ── */
  :root { --bg: #08090a; --surface: #191a1b; /* … */ }

  /* ── 여기서부터 페이지 CSS. 값이 아니라 토큰만 쓴다 ── */
  body { background: var(--bg); color: var(--fg); font-family: var(--font-body); }
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: var(--space-4);
  }
</style>
```

폰트는 별도다. `--font-body` 가 이름만 주므로 Google Fonts `<link>` 를 직접 걸고
실제 폴백 스택을 적는다. 안 걸면 조용히 시스템 폰트로 떨어진다.

## Vite + React + TypeScript

```
src/
  styles/
    tokens.css      # 패키지에서 받은 그대로. 수정 금지
    theme.css       # 우리가 덮어쓰는 것 + 다크 테마
  main.tsx
```

```ts
// main.tsx — 순서가 중요하다. tokens 먼저, theme 나중
import "./styles/tokens.css";
import "./styles/theme.css";
```

## Tailwind 4

Tailwind 4는 `@theme` 에서 CSS 변수를 직접 읽는다. 토큰을 유틸리티로 노출한다.

```css
@import "tailwindcss";
@import "./tokens.css";

@theme {
  --color-bg: var(--bg);
  --color-surface: var(--surface);
  --color-fg: var(--fg);
  --color-accent: var(--accent);
  --radius-card: var(--radius-md);
}
```

→ `bg-surface`, `text-fg`, `rounded-card` 로 쓸 수 있다.
**Tailwind 기본 팔레트(`bg-slate-800` 등)를 같이 쓰지 않는다.** 두 시스템이 섞이면
시스템 교체가 반만 먹는다.

## MUI 7

MUI는 자체 테마 객체를 쓰므로 토큰을 한 번 옮겨준다.

```ts
import { createTheme } from "@mui/material/styles";

const cssVar = (name: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim();

export const theme = createTheme({
  palette: {
    background: { default: cssVar("--bg"), paper: cssVar("--surface") },
    text: { primary: cssVar("--fg"), secondary: cssVar("--fg-2") },
    primary: { main: cssVar("--accent"), contrastText: cssVar("--accent-on") },
    success: { main: cssVar("--success") },
    warning: { main: cssVar("--warn") },
    error: { main: cssVar("--danger") },
  },
  typography: { fontFamily: cssVar("--font-body") },
  shape: { borderRadius: parseInt(cssVar("--radius-md"), 10) || 8 },
});
```

`cssVar` 는 DOM이 있어야 동작한다. SSR이면 값을 상수로 복사하고
원본이 어느 슬러그에서 왔는지 주석에 남긴다.

## 다크 테마 만들기 (패키지가 안 준다)

패키지는 `:root` 블록 하나만 준다 (`linear-app` 은 다크 네이티브, `notion` 은 라이트).
양쪽이 필요하면 **같은 토큰 이름을 다시 정의**한다. 컴포넌트는 손대지 않는다.

```css
/* theme.css — tokens.css 다음에 로드된다 */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #0f1112;
    --surface: #1a1d1e;
    --fg: #f2f4f3;
    --fg-2: #c4cac7;
    --border: rgba(255, 255, 255, .09);
    /* accent는 어두운 바탕에서 대비가 맞는지 확인하고 필요하면 밝힌다 */
  }
}
:root[data-theme="dark"] { /* 위와 같은 값 — 토글이 OS 설정을 이기도록 */ }
```

세 가지 상태를 전부 다룬다: 명시적 라이트(`[data-theme="light"]`),
명시적 다크(`[data-theme="dark"]`), 아무 표시 없음(OS 설정만).
**토큰을 미디어 쿼리 안에서 처음 정의하면 표시 없는 상태에서 값이 없다** — 이게 전형적인 버그다.

라이트 시스템을 다크로 뒤집을 때 값을 단순 반전하지 않는다. 대비를 다시 확인하고,
액센트가 양쪽 바탕에서 모두 읽히는지 본다.

## 검증

- [ ] 컴포넌트 CSS에 리터럴 색상(`#`, `rgb(`)이 하나도 없는가
- [ ] `--font-body` / `--font-display` 에 대응하는 폰트를 실제로 로드했는가 (폴백 스택 포함)
- [ ] 다크·라이트 양쪽에서 본문과 바탕의 대비가 살아 있는가
- [ ] 상태 색(`--success/--warn/--danger`)에 액센트를 대신 쓰지 않았는가
- [ ] `--focus-ring` 이 키보드 포커스에 실제로 적용됐는가
- [ ] 슬러그를 바꿔 `tokens.css` 만 교체해도 레이아웃이 그대로인가 — 이게 제대로 붙였다는 증거다
