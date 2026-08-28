"""HTTP 协议层中间件：请求级关联 ID（T20 可观测性）。

纯 ASGI 实现（不用 BaseHTTPMiddleware）：不缓冲响应流、不破坏
StreamingResponse 语义，且 contextvar 的还原时机覆盖 Starlette
在应用调用内部执行的后台任务。
"""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from document_qa_server.observability import new_request_id, reset_request_id, set_request_id


class RequestIdMiddleware:
    """为每个 HTTP 请求生成 request_id：注入日志上下文并回写响应头。

    - 日志关联：请求处理期间（含其派生的后台任务）产生的 JSON 事件
      自动携带 request_id，可与 access.log 的时间线相互印证；
    - 响应头 X-Request-ID：前端/调用方报障时上报该 ID，即可在
      server.jsonl 中精确检索本次请求的全部事件。
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        # 非 HTTP 协议（lifespan、websocket）不注入，直接透传。
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = new_request_id()
        token = set_request_id(request_id)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                # 响应头回写关联 ID；用 append 不覆盖上游已设的值。
                MutableHeaders(scope=message).append("x-request-id", request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            reset_request_id(token)
