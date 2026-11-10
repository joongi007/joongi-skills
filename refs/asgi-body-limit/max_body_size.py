"""요청 바디 크기를 제한하는 순수 ASGI 미들웨어.

Starlette/FastAPI에는 바디 크기 제한이 없다. `BaseHTTPMiddleware`는 바디를 버퍼링하므로
제한 용도로는 쓸 수 없다 — 그래서 `receive` 콜백을 직접 감싼다.

    app.add_middleware(MaxBodySizeMiddleware, max_size=10 * 1024 * 1024)
"""

# 10 MiB — 이미지 업로드 한 장을 받되 /tmp를 채우지는 못하는 크기.
# 실제 값은 서비스가 받는 파일 종류에 맞춰 정하고, nginx client_max_body_size와 같은 값으로 둔다.
DEFAULT_MAX_SIZE = 10 * 1024 * 1024


class BodyTooLarge(Exception):
    """한도를 넘은 바디. 이 미들웨어 안에서만 쓰고 밖으로 새지 않는다."""


class MaxBodySizeMiddleware:
    def __init__(self, app, max_size: int = DEFAULT_MAX_SIZE):
        self.app = app
        self.max_size = max_size

    async def __call__(self, scope, receive, send):
        # websocket·lifespan 스코프에는 바디가 없다. 그대로 흘려보낸다.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        total = 0

        async def limited_receive():
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                # Content-Length가 아니라 실제로 도착한 바이트를 센다.
                # chunked 인코딩이면 헤더가 거짓말을 할 수 있다.
                total += len(message.get("body", b""))
                if total > self.max_size:
                    raise BodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except BodyTooLarge:
            # 앱이 아직 응답을 시작하지 않은 상태여야 한다. 바디를 읽는 시점이
            # 곧 핸들러 진입 직후이므로 보통 성립한다.
            await send({
                "type": "http.response.start",
                "status": 413,
                "headers": [(b"content-type", b"text/plain; charset=utf-8")],
            })
            await send({"type": "http.response.body", "body": b"request body too large"})
