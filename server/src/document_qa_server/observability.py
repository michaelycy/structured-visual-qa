"""结构化日志：JSON 行格式，服务端关键路径的可观测性基础。

uvicorn 的访问日志保持原样（人读），本模块的 JSON 行供机器采集：
任务状态转换、归一化失败、异常兜底等事后排障依赖这些事件字段。
纯标准库实现，不引入额外依赖。

落盘（T20）：configure_file_logging 把 JSON 事件与 uvicorn 访问/错误
日志按天轮转写入文件；stderr/stdout 输出保持不变（12-Factor 约定，
容器侧仍可走标准流采集）。

请求关联：HTTP 中间件为每个请求生成 request_id 存入 contextvar，
JSON 事件经 RequestContextFilter 自动携带，跨层排障可串联
"访问日志 → 业务事件"；后台任务继承提交请求的 request_id。
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any
from uuid import uuid4

# 事件名 → 打点位置的约定（新增打点先在此登记，保持可检索）。
KNOWN_EVENTS = (
    "task_submitted",      # 任务登记（task_id、输入展示名）
    "task_state",          # 任务状态迁移（含终态与错误摘要）
    "task_interrupted",    # 启动恢复：上次运行遗留任务被标记中断
    "task_recovered",      # 重启后从数据库读回终态任务
    "normalize_failed",    # LibreOffice 归一化失败
    "render_garbage",      # 产物 GC 删除的孤儿渲染目录
    "server_started",      # 服务启动（pid、事件日志路径、版本）
    "server_stopped",      # 服务正常停机（lifespan shutdown）
)

# 当前 HTTP 请求的关联 ID；None 表示非请求上下文（启动/后台兜底路径）。
_request_id_var: ContextVar[str | None] = ContextVar("dqa_request_id", default=None)


def new_request_id() -> str:
    """生成 8 位 hex 请求 ID：足够区分同秒内的并发请求且便于肉眼比对。"""

    return uuid4().hex[:8]


def set_request_id(value: str) -> Token[str | None]:
    """进入请求上下文时绑定 request_id；返回 token 供退出时还原。"""

    return _request_id_var.set(value)


def reset_request_id(token: Token[str | None]) -> None:
    """离开请求上下文时还原，避免上下文泄漏到后续无关代码。"""

    _request_id_var.reset(token)


# LogRecord 的内建属性名（makeRecord 固定写入）；extra 业务字段不在此列。
_LOG_RECORD_ATTRS = frozenset(
    "args created exc_info exc_text filename funcName levelname levelno lineno "
    "module msecs msg name pathname process processName relativeCreated "
    "stack_info taskName thread threadName".split()
)


# 文件 handler 的角色标记（挂载前防重复检查用；--reload 重启进程内幂等）。
_ROLE_ATTR = "_dqa_log_role"


class RequestContextFilter(logging.Filter):
    """把当前请求的 request_id 注入 LogRecord。

    附加在 document_qa_server 的 handler 上；非请求上下文产生的记录
    （后台兜底、启动事件）不带该字段，保持 JSON 输出干净。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        request_id = _request_id_var.get()
        if request_id:
            record.request_id = request_id  # type: ignore[attr-defined]
        return True


class JsonLineFormatter(logging.Formatter):
    """把 LogRecord 渲染成单行 JSON；事件字段放 event，附加字段平铺。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", "log"),
            "message": record.getMessage(),
        }
        # extra 业务字段（排除 LogRecord 内建属性）平铺到 JSON 顶层。
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _LOG_RECORD_ATTRS and not key.startswith("_")
        }
        payload.update(extras)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def get_server_logger() -> logging.Logger:
    """返回服务统一 logger；JSON 行输出到 stderr（uvicorn 约定）。"""

    logger = logging.getLogger("document_qa_server")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(JsonLineFormatter())
        handler.addFilter(RequestContextFilter())
        handler._dqa_log_role = "stderr"  # type: ignore[attr-defined]
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        # 不向根 logger 传播，避免与 uvicorn 的文本格式混排。
        logger.propagate = False
    return logger


def configure_file_logging(log_dir: Path, retention_days: int = 14) -> Path:
    """为服务与 uvicorn 日志挂载按天轮转的文件 handler（幂等），返回事件日志路径。

    调用时机必须在 uvicorn dictConfig 之后（lifespan startup 满足），
    否则挂到 uvicorn.access/uvicorn.error 上的 handler 会被其日志
    配置整体替换。stderr/stdout 输出不受影响，两条通道并存。

    已知限制：TimedRotatingFileHandler 不支持多进程并发写同一文件，
    当前单进程部署不受影响；未来多 worker 需换外部采集方案。
    """

    log_dir.mkdir(parents=True, exist_ok=True)

    # JSON 事件流：复用 stderr 同款 formatter 与请求过滤器，机器可采集。
    events_file = log_dir / "server.jsonl"
    server_logger = get_server_logger()
    if not any(getattr(h, _ROLE_ATTR, None) == "events" for h in server_logger.handlers):
        handler: logging.Handler = TimedRotatingFileHandler(
            events_file, when="midnight", backupCount=retention_days, encoding="utf-8"
        )
        handler.setFormatter(JsonLineFormatter())
        handler.addFilter(RequestContextFilter())
        setattr(handler, _ROLE_ATTR, "events")
        server_logger.addHandler(handler)

    # uvicorn 人读流：访问日志是排障时定位"哪个请求何时返回什么状态"的
    # 一手证据；error 流携带应用异常与启动生命周期消息。均为纯文本落盘。
    text_targets = (
        ("uvicorn.access", "access.log", "access", "%(message)s"),
        ("uvicorn.error", "error.log", "error", "%(asctime)s %(levelname)s %(message)s"),
    )
    for logger_name, filename, role, fmt in text_targets:
        target = logging.getLogger(logger_name)
        if any(getattr(h, _ROLE_ATTR, None) == role for h in target.handlers):
            continue
        handler = TimedRotatingFileHandler(
            log_dir / filename, when="midnight", backupCount=retention_days, encoding="utf-8"
        )
        # access 记录的 msg+args 已插值出完整访问行（与控制台一致、无色）。
        handler.setFormatter(logging.Formatter(fmt))
        setattr(handler, _ROLE_ATTR, role)
        target.addHandler(handler)

    return events_file


def log_event(event: str, /, **fields: Any) -> None:
    """打点的便捷入口：logger.log(INFO, msg, extra={event, ...fields})。"""

    logger = get_server_logger()
    logger.info(
        fields.pop("message", event),
        extra={"event": event, **fields},
    )
