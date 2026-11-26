# 프론트엔드 (React + TypeScript) · PLAYBOOK §9.1, §11, §20

React·Zustand·Axios를 선택한 프로젝트의 예시다. 기존 스택·인증 계약을 우선하며 새 의존성이나 버전을 강제하지 않는다.

## 목차

- 폴더 골격 (§20.1)
- 폴더 축 원칙 (§9.1)
- 훅 규율 (§9.1)
- 상태를 어디에 두나 (§9.1)
- HTTP 클라이언트 — Axios (§20.2)
- Zustand 스토어 (§20.3)
- WebSocket 클라이언트 싱글톤 (§20.4)
- 기술 스택 (§20.5)
- UI–API 계약 (§11)

## 폴더 골격 (§20.1)

```
src/
  api/             # HTTP 클라이언트 래퍼 (도메인별 파일)
    http.ts        # axios 인스턴스 + 인터셉터
    auth.ts / <domain>.ts / ...
  components/
    features/      # 도메인 복합 컴포넌트 (<Domain>Panel, <Domain>View …)
    layout/        # 페이지 골격 (NavigationBar, Sidebar …)
    common/        # 재사용 원자 컴포넌트 (Button, Modal …)
  hooks/           # useXxx.ts — 관심사 하나당 파일 하나
  pages/           # 라우팅 단위 (<Name>Page/)
  stores/          # Zustand (<name>Store.ts)
  types/           # 공유 타입; 도메인 타입은 feature에 둘 수 있음
  ws/              # WsClient 싱글톤
  constants/
  utils/
  theme/           # MUI 테마
```

## 폴더 축 원칙 (§9.1)

- `pages` / `components`만으로 끝내지 말고, 가능하면 **`features/<도메인>/`** 처럼 **기능 단위**로 묶는다.
- **파일당 책임**: 한 화면 파일에 마크업·fetch·폼·derived state를 전부 넣지 않는다. **표시(프레젠테이션)**와 **데이터를 가져와 조합하는 층**을 나눈다.
- **모듈 경계**: `features/A`가 `features/B`의 내부 구현 파일을 직접 import하지 않게. **공개 entry(`index.ts`)·타입만** 바깥으로 노출 → 의존 방향 고정.

## 훅 규율 (§9.1)

- `useXxx`는 **하나의 관심사**(한 자원의 fetch, 한 폼의 lifecycle, 한 interval)에 대응.
- 두 화면 이상이 쓰면 **`hooks/` 또는 `features/...` 안으로** 올림.
- **여러 무관한 일을 하는 god hook은 쪼갠다.**

## 상태를 어디에 두나 (§9.1)

- **서버에서 온 진실** (목록·설정·집계): 가능하면 **요청 캐시·무효화가 있는 도구** (TanStack Query, SWR 등). 전역 Context에 API 응답을 복붙하지 않는다.
- **UI만의 상태**:
  - 기본은 **컴포넌트 로컬**.
  - 형제끼리만 공유면 **가까운 공통 부모로 lift**.
  - 앱 전역은 **정말 필요한 키만** Context·Zustand에.
- **코드 스플릿**: 라우트 단위 lazy import, 차트·에디터 등 무거운 묶음은 **동적 import** → 초기 번들 축소.

## HTTP 클라이언트 — Axios (§20.2)

```typescript
// api/http.ts
const http = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL ?? '' });

// Request: Authorization: Bearer <access>
http.interceptors.request.use((config) => {
  const token = getAccessToken();  // 선택한 인증 설계의 메모리 저장소 등
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Response: 401 → refresh → retry (큐로 동시 refresh 방지)
http.interceptors.response.use(undefined, async (error) => {
  if (error.response?.status !== 401) throw error;
  // POST /api/v1/auth/token/refresh → new tokens → retry
});
```

**중요한 디테일:**
- 브라우저 인증은 BFF 또는 `HttpOnly`·`Secure`·적절한 `SameSite` 쿠키와 CSRF 방어를 먼저 검토한다.
- `localStorage`·`sessionStorage`에 인증·갱신 토큰을 저장하는 것을 기본 권장하지 않는다. 같은 origin의 JavaScript가 접근하므로 XSS에 노출된다.
- JavaScript가 토큰을 다뤄야 하는 계약은 메모리 수명·재로그인·갱신·CSP와 사용 SDK의 보안 모델을 검토한다. 메모리 저장만으로 XSS가 해결되지는 않는다.
- proxying BFF·TMB·browser-only OAuth의 토큰 위치와 API aggregation 책임은 [브라우저 backend](browser-backends.md)를 따른다.
- 같은 클라이언트 실행 범위에서는 refresh single-flight를 사용하고 retry 횟수·종료 조건을 둔다.
  다른 탭·프로세스·replica까지 자동 조정되지는 않으므로 서버의 원자적 rotation 계약도 검증한다.
- refresh 뒤 모든 요청을 무조건 재전송하지 않는다. 대상 origin·인증 실패 원인·body 재사용 가능 여부와
  쓰기의 멱등 키·서버 처리 계약을 확인한다. refresh endpoint나 반복 실패는 재귀 갱신하지 않는다.
  Authorization 헤더를 외부 URL에 붙이지 않게 호출 대상도 제한한다.
- **Refresh 호출 자체는 인터셉터를 거치지 않게** — 별도 axios 인스턴스나 raw `axios.post`로. 안 그러면 refresh 응답이 401일 때 다시 refresh를 부르며 무한 루프.

## Zustand 스토어 (§20.3)

```typescript
interface AuthState {
  user: UserInfo | null;
  isAuthenticated: boolean;
  setLogin(accessToken, refreshToken, user, mustChange): void;
  clearAuth(): void;
}
export const useAuthStore = create<AuthState>((set) => ({ ... }));
```

- 스토어 파일명: **`<name>Store.ts`** (camelCase + Store suffix).
- 스토어 분리 기준: `auth` / `<domain>` / `settings`.
- **외부에서 직접 읽기 (stale closure 방지)**: `useXxxStore.getState()` (React 훅 외부에서). React 훅으로 구독한 값은 클로저에 캡처된 시점의 값이라, 인터셉터·타이머·이벤트 핸들러 같은 비-React 컨텍스트에서 호출되면 옛날 값을 본다 — 그래서 `getState()`로 매번 최신 스냅샷을 읽는다.

## WebSocket 클라이언트 싱글톤 (§20.4)

```typescript
// ws/wsClient.ts
class WsClient {
  on<T>(event: string, handler: (body: T) => void): () => void  // unsubscribe 반환
  send(event: string, body: unknown): void
  async connect(): Promise<void>
  startAutoConnect(): void   // 상한·backoff·jitter와 인증 만료 처리
  disconnect(): void
}
export const wsClient = new WsClient();
```

**WS 메시지 포맷:**
```json
{ "header": { "version": "v1", "event": "v1/<domain>/<action>" }, "body": { ... } }
```

- 이벤트 이름: `v1/<domain>/<action>` (슬래시, 버전 prefix).
- **`wsClient.on()` 반환값(unsubscribe 함수)을 `useEffect` cleanup에서 반드시 호출.**

## 기술 스택 (§20.5)

아래 이름은 선택 후보이며 지원 버전은 기존 lockfile·공식 지원 정책·취약점 공지로 확인한다.

| 역할 | 라이브러리 예시 |
|---|---|
| 상태관리 | Zustand |
| HTTP | Axios |
| 라우팅 | React Router |
| UI 컴포넌트 | MUI |
| CSS | Tailwind CSS 또는 Emotion |
| 시각화 | Recharts |
| 알림 | Notistack |
| 빌드 | Vite |
| 타입 | TypeScript |

> 영상 스트리밍·지도·3D 등 도메인 특화 라이브러리는 프로젝트마다 다르므로 별도 문서.

## UI–API 계약 (§11)

- API 버전 정책은 서버 계약과 일치시킨다. `/api/v1/...`은 경로 버전 방식의 예시다.
- 클라이언트 `baseURL`은 **상대 경로(`/api/...`)** 기본 → 배포·리버스 프록시 뒤에서 동일 오리진 유지.
- **브라우저에 시크릿을 넣지 않는다.** 공개해도 되는 값만 빌드 타임 env로.

### 개발할 때 UI 띄우기 (§11.1)

- **UI만 빠르게 고칠 때**: 호스트에서 `npm run dev`(Vite). "에디터 저장 → 즉시 반영" 루프 우선.
- **리버스 프록시(Traefik)로 검증할 때**: 브라우저가 **프록시가 노출한 단일 URL**(예: `http://127.0.0.1:9443`)만 보면 되게. 그 뒤에서 `/api → API`, `/ → Vite` 경로 분기.
- 이 구성에서는 이미 같은 오리진이므로 **Vite `server.proxy`를 따로 둘 필요 없음**. `fetch('/api/...')`만으로 프록시가 API로 넘긴다. (HMR 웹소켓 예외는 별도.)

### Vite만 단독으로 켰을 때 (§11.2)

- 브라우저가 `localhost:5173`이고 API가 다른 포트면 CORS·절대 URL 문제 발생.
- 이때만 **Vite 프록시** 또는 **API의 CORS 허용** 같은 추가 수단. **§11.1처럼 한 진입점으로 묶을 수 있으면 그쪽이 먼저.**

### 검증 순서 (§11.3)

- 먼저 브라우저 한 탭으로 "진입 URL에서 UI가 뜨는지", `/healthz`·대표 API 한두 개가 기대대로 오는지.
- 그 다음에만 추가 도메인·TLS 종단·이중 프록시·헤더 트릭으로 넓힌다. **처음부터 복잡한 솔루션으로 가지 않는다.**

브라우저 인증 저장 근거: [OWASP Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).
