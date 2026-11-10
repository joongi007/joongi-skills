# 린트·포맷·이름 규칙 (PLAYBOOK §22)

## Python · Ruff (§22.1)

**`pyproject.toml`:**

```toml
[tool.ruff]
target-version = "py314"
line-length = 88

[tool.ruff.lint]
select = ["E", "W", "F", "I", "B", "C4", "UP", "N", "SIM"]
# E/W: pycodestyle, F: pyflakes, I: isort, B: bugbear
# C4: comprehensions, UP: pyupgrade, N: pep8-naming, SIM: simplify

[tool.ruff.lint.isort]
combine-as-imports = true

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

**규칙:**
- `ruff check --fix` + `ruff format` 두 단계로 끝.
- **Black·isort 별도 설치/설정 금지** — Ruff 하나로.
- 줄 길이 88자 (Black 기본값과 동일).

## TypeScript · ESLint v9 flat config (§22.2)

```javascript
// eslint.config.js
export default [
  js.configs.recommended,
  ...tseslint.configs.recommended,
  reactHooks.configs.flat.recommended,
  reactRefresh.configs.vite,
  { files: ["**/*.{ts,tsx}"], ... }
]
```

- **ESLint v9 flat config(`eslint.config.js`) — 구형 `.eslintrc.*` 사용 금지.**
- TypeScript strict mode (`tsconfig.json`에 `"strict": true`).

## 파일·식별자 명명 (§22.3)

| 대상 | 규칙 | 예시 |
|---|---|---|
| Python 상수 | `UPPER_SNAKE_CASE` | `NATS_SUBJECT_LIDAR` |
| Python 클래스 | `PascalCase` | `RecordsRepository` |
| Python 함수·변수 | `snake_case` | `get_by_idx` |
| Python private | `_leading` | `_parse_ts_ns` |
| TS 컴포넌트 파일 | `PascalCase.tsx` | `ControlPanel.tsx` |
| TS 훅 파일 | `camelCase.ts` | `useLiveKit.ts` |
| TS 스토어 파일 | `camelCaseStore.ts` | `robotStore.ts` |
| TS 타입 | `PascalCase` | `AuthState`, `RobotState` |
| WS/NATS 이벤트 키 | `snake_case` 영어 | `robot_state_updated` |

## 자주 발생하는 실수

- 상수에 `lowerCamelCase` 쓰기 → 항상 `UPPER_SNAKE_CASE`.
- 컴포넌트 파일을 `controlPanel.tsx`로 → `PascalCase.tsx`.
- 스토어 파일에 Store suffix 빠짐 (`robot.ts`) → `robotStore.ts`.
- WS 이벤트에 camelCase (`robotStateUpdated`) → `robot_state_updated` 또는 더 정확히는 §20.4의 `v1/<domain>/<action>` 형태.
- `__all__` 직접 관리 → `# ruff: noqa: F401` 사용 (`python-api.md` §5 참고).
