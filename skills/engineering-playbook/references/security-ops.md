# 웹 백엔드 보안 — 설정·인프라·운영 (PLAYBOOK §24)

> `web-security.md`가 코드에서 막는 것들이라면, 이 파일은 **설정과 운영에서 막는 것들**이다.
> 코드 리뷰에서는 잡히지 않고, 아무도 시키지 않으면 영원히 하지 않게 되는 항목들.

## 목차

- §9 보안 헤더 (helmet 대응)
- §10 개인정보 보호 — 암호화, 유출 경로, 최소 수집, 내부 접근 통제
- §11 서버 리소스 탈취 — 침투 경로, 공급망, 컨테이너 하드닝, 아웃바운드 차단
- §12 랜섬웨어 / 백업 — 불변 백업, 복구 훈련, 사고 대응
- §13 설정 / 운영 — FastAPI 기본 뼈대, 설정 노출, 로깅·모니터링
- 부록 C 계층별 책임 분담

---

## §9. 보안 헤더 (Express의 helmet에 해당)

helmet은 **응답에 보안 헤더를 붙여주는 것이 전부**다. 마법이 아니라
"까먹기 쉬운 헤더 체크리스트"다. 파이썬에서는 직접 15줄로 작성하면 된다
(`secure` 라이브러리도 있지만 의존성을 늘릴 만큼의 값어치는 없다).

**이것은 심층 방어(2차 방어선)지 1차 방어가 아니다.**
CSP를 붙였다고 XSS가 막히는 게 아니라, 이스케이프가 본체고 CSP는 보험이다.
30분이면 끝나는 작업이므로 여기에 우선순위를 두지 말고
`web-security.md` §1(권한), §2(인증)에 시간을 쓴다.

```python
BASE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}

API_CSP  = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
HTML_CSP = ("default-src 'self'; script-src 'self'; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'")

@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    for k, v in BASE_HEADERS.items():
        resp.headers.setdefault(k, v)
    is_html = resp.headers.get("content-type", "").startswith("text/html")
    resp.headers.setdefault("Content-Security-Policy",
                            HTML_CSP if is_html else API_CSP)
    return resp
```

주의사항:

- **JSON API에는 `default-src 'none'`이 맞다.** 로드할 것이 없으므로 가장 강한 값을
  줘도 문제가 없고, HTML이 새어나가도 무력화된다.
- `setdefault`를 쓰는 이유: 특정 라우트에서 덮어써야 할 때
  (예: 결제 위젯 iframe 허용) 개별 응답이 우선하도록.
- **HSTS를 HTTP 응답에 붙이지 않는다.** `preload`는 모든 서브도메인이
  HTTPS일 때만. 아니면 서비스가 죽는다. 확신이 없으면 `preload`를 뺀다.
- `/docs`는 CDN에서 스크립트를 로드하므로 위 CSP에 걸려 흰 화면이 된다.
  프로덕션에서 끄거나 해당 경로만 예외 처리.
- nginx와 앱 양쪽에서 붙이면 헤더가 중복된다. **한 곳에서만** 한다.
- CSP/X-Frame-Options는 브라우저 렌더링 시의 규칙이라 순수 JSON API에는
  직접 효과가 적다. 그래도 붙이는 이유: 에러 페이지·`/docs`가 HTML로 나가고,
  업로드 파일 서빙 경로가 있으면 저장형 XSS 방어에 직결되며(`web-security.md §4.3`),
  보안 점검에서 스캔한다.
  **HSTS는 API여도 무조건 켠다** (렌더링과 무관하게 HTTPS 다운그레이드를 막는다).

---

## §10. 개인정보 보호

### §10.1 암호화

- 주민번호·카드·건강정보는 **컬럼 단위 암호화**(AES-GCM).
- **키는 DB가 아닌 곳에**(KMS, Vault). 같은 DB에 키를 두면 의미가 없다.
- 암호화 컬럼을 검색해야 하면 **블라인드 인덱스**(HMAC 해시)를 별도 컬럼으로.
- **키 회전**이 가능하게 설계 — 암호문에 키 버전 태그를 붙인다.
- 전송은 TLS 1.2+, 내부망도 가급적 TLS.

### §10.2 유출 경로 — 대부분 해킹이 아니라 실수로 샌다

- **로그**: 요청 바디 통째로 기록, 예외에 SQL 파라미터 포함,
  Sentry에 PII 전송 → `send_default_pii=False` + `before_send` 마스킹,
  로그 필터에 민감 키 리스트. (`logging.md`의 "로그에 남기지 않는 것" 규칙과 동일.)
- **응답**: `response_model` 미설정 (`web-security.md §1.3`).
- **에러 메시지**: 스택트레이스, DB 에러 원문 노출 금지.
- **URL 쿼리스트링에 토큰·PII를 넣지 않는다.**
  액세스 로그, 리퍼러, 브라우저 히스토리, 프록시에 전부 남는다.
- **CSV 인젝션**: 셀이 `=`, `+`, `-`, `@`로 시작하면 엑셀에서 수식이 실행된다
  → 앞에 `'` 추가.
- **이미지 EXIF**: 업로드 사진에 GPS 좌표가 남는다 → 재인코딩으로 제거
  (`web-security.md §4.2`).
- **PDF/DOCX 메타데이터**: 작성자, 편집 이력.

### §10.3 최소 수집·보관

- **안 쓸 데이터는 받지 않는다. 없는 데이터는 유출될 수 없다.**
- 보관 기간을 정하고 자동 삭제 (탈퇴 사용자 데이터, 오래된 로그).
- soft delete로 끝내지 말고 실제 파기 정책이 필요하다
  (한국은 개인정보보호법상 파기 의무가 있다).
- **개발/스테이징에 운영 데이터를 복사하지 않는다.** 마스킹된 더미를 쓴다.
  유출 사고의 단골 원인.

### §10.4 내부 접근 통제

- 관리자 조회 화면에도 **감사 로그**. 내부자가 특정 계정을 열람하는 사고가 많다.
- DB 계정 최소 권한. 앱 계정에 `DROP`, `CREATE USER` 권한을 주지 않는다.
- 백업 파일도 암호화 (평문 덤프가 S3에 퍼블릭으로 있는 사고가 흔하다).

---

## §11. 서버 리소스 탈취 (크립토마이닝·봇넷)

원인은 결국 **RCE 아니면 크리덴셜 유출**이다.

### §11.1 침투 경로

- 역직렬화(pickle/yaml), SSTI, 커맨드 인젝션 (`web-security.md §3`)
- **의존성 공급망** — 현재 가장 비중이 큰 경로 (§11.2)
- **노출된 관리 인터페이스**: Redis(인증 기본값 없음 → 즉시 털린다),
  Docker API 2375, Kubernetes 대시보드, Jupyter, DB 포트.
  크립토마이너 봇이 자동 스캔해서 즉시 심는다.
- 클라우드 메타데이터로 IAM 크리덴셜 탈취 (`web-security.md §5.4`)

### §11.2 공급망

- **Dependency confusion**: 사내 패키지명이 PyPI에 없으면 공격자가
  같은 이름의 높은 버전을 올려 가로챈다 → 내부 인덱스 우선 설정, 이름 선점.
- **타이포스쿼팅**: `reqeusts`, `python-dateutil` vs `dateutil`.
- 설치 시점에 코드가 실행된다(`setup.py`) → lockfile + 해시 고정
  (`uv.lock`을 커밋한다).
- `pip-audit` / Dependabot을 CI에.

### §11.3 실행 자체를 막기

```dockerfile
USER 1000:1000            # root 금지
```
```yaml
readOnlyRootFilesystem: true       # 페이로드를 쓸 수 없다 = 마이너를 심을 수 없다
allowPrivilegeEscalation: false
capabilities: { drop: ["ALL"] }
```

- 컨테이너에 컴파일러/curl/wget을 넣지 않는다 (distroless 또는 slim + 멀티스테이지).
- 쓰기가 필요한 경로만 tmpfs로.

### §11.4 아웃바운드 차단 — 핵심인데 대부분 하지 않는다

대부분 방화벽을 인바운드만 설정한다.
**아웃바운드를 기본 차단하면 RCE가 나도 마이너가 풀에 접속하지 못해 수익화가 되지 않고,
데이터 유출도 동시에 막힌다.**

```
egress: DB, 결제사, 필요한 API 도메인만 허용. 나머지 DENY
```

### §11.5 탐지

- CPU 지속 100%, 비정상 아웃바운드 연결, 알 수 없는 프로세스 → 알림.
- 이미지 스캔(Trivy), 런타임 이상탐지(Falco).
- **GitHub secret scanning 활성화.** AWS 키가 커밋되면
  몇 분 안에 마이닝 인스턴스가 수십 대 뜬다.

---

## §12. 랜섬웨어 / 백업

예방은 §11과 동일하다. 웹 백엔드 관점에서 중요한 것은
**"암호화당해도 복구 가능한가"** 하나다.

### §12.1 백업이 같이 털리는 것이 문제

공격자가 가장 먼저 하는 일이 백업 삭제다.

**3-2-1-1-0 원칙**: 3벌, 2개 매체, 1개 오프사이트,
**1개 오프라인/불변**, 0개 복구 실패.

핵심은 **불변(immutable) 백업**:

- S3 Object Lock (Compliance 모드) — 루트 권한으로도 삭제 불가.
- **push가 아니라 pull 구조.** 앱 서버가 백업 서버에 쓰는 구조면
  앱 서버가 털릴 때 백업도 털린다. 백업 서버가 가져가게 한다.
- 백업용 크레덴셜은 **쓰기 전용**(삭제·덮어쓰기 권한 없음).
- 별도 계정/구독에 보관 (같은 AWS 계정이면 IAM이 털릴 때 끝난다).

### §12.2 복구를 실제로 해봐야 한다

- **복원 훈련을 하지 않으면 백업은 없는 것과 같다.** 분기 1회 실제 복원 테스트.
- RPO/RTO를 정하고 측정한다
  ("몇 시간치 데이터를 잃어도 되나", "몇 시간 안에 복구해야 하나").
- **PITR**(Point-in-Time Recovery)를 켠다. 스냅샷만으로는 "감염 직전"으로 못 돌아간다.
- 랜섬웨어는 잠복 후 터진다 → **백업 보관 기간을 충분히**(30~90일).
  7일치만 있으면 이미 감염된 백업만 남는다.

### §12.3 무결성 / 사고 대응

- 백업 체크섬 검증 (손상된 백업을 자동 생성하지 않도록).
- **감사 로그는 append-only 별도 저장소로.**
  침해 조사에 필수인데 같은 서버에 있으면 지워진다.
- 파일 스토리지도 버저닝 (S3 versioning + MFA delete).
- **연락처와 절차를 오프라인에** 보관 (사내 위키가 암호화되면 볼 수 없다).
- 격리 → 보존(포렌식용 스냅샷) → 복구 순서.
  성급히 재부팅하면 증거가 사라진다.
- 한국은 개인정보 유출 시 **72시간 내 신고 의무**
  (개인정보보호위원회/KISA). 절차를 미리 확인해 둔다.

---

## §13. 설정 / 운영

### §13.1 FastAPI 기본 뼈대

새 프로젝트 스캐폴딩 시 이 블록을 같이 넣는다 (`scaffolding.md`와 함께 본다).

```python
app = FastAPI(
    docs_url=None if PROD else "/docs",     # 프로덕션 문서 차단
    redoc_url=None if PROD else "/redoc",
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["api.example.com"])
app.add_middleware(HTTPSRedirectMiddleware)
app.add_middleware(CORSMiddleware,
                   allow_origins=["https://app.example.com"],
                   allow_credentials=True,
                   allow_methods=["GET", "POST"])
app.add_middleware(MaxBodySizeMiddleware, max_size=10 * 1024 * 1024)

@app.exception_handler(Exception)
async def handler(request, exc):
    logger.exception("unhandled")                                  # 내부에는 남기고
    return JSONResponse({"detail": "Internal Server Error"}, 500)  # 외부에는 주지 않는다
```

`MaxBodySizeMiddleware` 구현은 `web-security.md §4.1`.
CORS origins는 환경 변수로 뺀다 (§19.10, `auth-jwt.md`).

### §13.2 설정 노출

- **프로덕션에서 `debug=True` 금지.** 스택트레이스에 쿼리·경로·설정이 전부 나온다.
- **`.git/` 웹 노출 → 소스 전체가 복원된다.**
  `.env`, `.DS_Store`, `backup.sql`, `swagger.json`도 마찬가지.
- 시크릿을 코드/git에 넣지 않는다. env 또는 시크릿 매니저 (`config-secrets.md`).
  **이미 커밋했다면 키를 폐기해야 한다. 커밋 삭제로는 해결되지 않는다.**
- **서브도메인 탈취**: DNS는 남았는데 서비스는 내린 CNAME →
  공격자가 그 도메인을 점유 → 쿠키·CORS 신뢰가 전부 넘어간다.
- 클라우드 스토리지 버킷 퍼블릭 여부 확인.
- 관리 포트(Redis 6379, Postgres 5432)를 인터넷에 노출하지 않는다.

### §13.3 로깅·모니터링 (OWASP 정식 항목)

털려도 모르면 피해가 무한정 커진다.

- 인증 실패, 권한 거부, 입력 검증 실패는 **반드시 로그**.
- 알림 임계치 설정 (같은 IP에서 401 100회 등).
- 로그는 append-only, 별도 저장소.
- 로그에 비번·토큰·카드번호가 찍히지 않게 (§10.2).

---

## 부록 C. 계층별 책임 분담

**이 문서의 상당수는 코드가 아니라 설정과 운영이다.**
코드 보안은 리뷰에서 잡히지만, 백업 복원 테스트나 아웃바운드 정책은
아무도 시키지 않으면 영원히 하지 않게 된다. 캘린더에 넣어두는 것이
실질적으로 가장 효과가 크다.

그리고 **보안은 단일 방어선이 아니라 계층**이다.

| 계층 | 담당 |
|---|---|
| CDN/WAF | 볼륨 공격, 봇 |
| nginx | 바디 크기, slowloris, IP당 레이트리밋, Host 검증 |
| uvicorn | `--limit-concurrency`, keep-alive 타임아웃, proxy-headers 제한 |
| 앱 | 권한 검사, 스키마 검증, 인젝션 방어, 이벤트루프 보호 |
| DB | UNIQUE/CHECK 제약, RLS, 최소 권한 계정 |
| 인프라 | 컨테이너 하드닝, 아웃바운드 차단, 불변 백업 |
