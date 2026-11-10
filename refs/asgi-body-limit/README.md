# ASGI 바디 크기 제한 미들웨어

`web-security.md` §4.1 / `security-ops.md` §13.1 의 근거 자료.

**문제**: Starlette/FastAPI에는 요청 바디 크기 제한이 **없다.** `UploadFile`은
`SpooledTemporaryFile`이라 1MB를 넘으면 디스크에 쓴다. 제한이 없으면 `/tmp`가 포화되고,
디스크가 차면 DB도 로그도 같이 죽는다.

**왜 `Content-Length`를 믿으면 안 되나**: `Transfer-Encoding: chunked` 로 보내면
`Content-Length` 헤더가 아예 없거나 거짓일 수 있다. **실제로 읽은 바이트를 세야 한다.**

**왜 `BaseHTTPMiddleware`면 안 되나**: `BaseHTTPMiddleware`는 요청 바디를 버퍼링해서
다음 단계로 넘긴다. 즉 우리가 크기를 확인하는 시점에는 이미 전부 메모리에 올라와 있다.
제한의 목적이 사라진다. → **순수 ASGI 미들웨어**로 작성해서 `receive` 콜백을 감싼다.

## 파일

- [`max_body_size.py`](max_body_size.py) — 미들웨어 최소 구현. 의존성 없음(순수 ASGI).
  ASGI 앱이면 프레임워크 무관하게 붙는다.

```python
from max_body_size import MaxBodySizeMiddleware

app.add_middleware(MaxBodySizeMiddleware, max_size=10 * 1024 * 1024)
```

## 핵심

`receive`를 감싸서 `http.request` 메시지가 올 때마다 누적 바이트를 세고,
한도를 넘으면 그 자리에서 413을 보내고 스트림을 끊는다.
앱 코드는 이 미들웨어의 존재를 몰라도 된다.

**앱 레벨이 마지막 방어선이 아니다.** nginx `client_max_body_size` 를 함께 건다
(`web-security.md` §6.1). 요청이 앱에 도달한 시점에는 이미 소켓과 워커가 소비된 뒤다.

## 출처

- ASGI 명세 (HTTP `receive` 이벤트 형태): https://asgi.readthedocs.io/en/latest/specs/www.html
- Starlette 미들웨어 문서: https://www.starlette.io/middleware/

이 저장소에서 작성했다. 외부 코드 인용 아님.
이 환경에 starlette이 설치돼 있지 않아 **실행 검증은 하지 않았다** — 문법만 확인했다.
