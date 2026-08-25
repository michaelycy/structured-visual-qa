"""结构化日志：JSON 行格式，服务端关键路径的可观测性基础。

uvicorn 的访问日志保持原样（人读），本模块的 JSON 行供机器采集：
任务状态转换、归一化失败、异常兜底等事后排障依赖这些事件字段。
纯标准库实现，不引入额外依赖。
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

# 事件名 → 打点位置的约定（新增打点先在此登记，保持可检索）。
KNOWN_EVENTS = (
    "task_submitted",      # 任务登记（task_id、输入展示名）
    "task_state",          # 任务状态迁移（含终态与错误摘要）
    "task_interrupted",    # 启动恢复：上次运行遗留任务被标记中断
    "task_recovered",      # 重启后从数据库读回终态任务
    "normalize_failed",    # LibreOffice 归一化失败
    "render_garbage",      # 产物 GC 删除的孤儿渲染目录
)


# LogRecord 的内建属性名（makeRecord 固定写入）；extra 业务字段不在此列。
_LOG_RECORD_ATTRS = frozenset(
    "args created exc_info exc_text filename funcName levelname levelno lineno "
    "module msecs msg name pathname process processName relativeCreated "
    "stack_info taskName thread threadName".split()
)


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
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        # 不向根 logger 传播，避免与 uvicorn 的文本格式混排。
        logger.propagate = False
    return logger


def log_event(event: str, /, **fields: Any) -> None:
    """打点的便捷入口：logger.log(INFO, msg, extra={event, ...fields})。"""

    logger = get_server_logger()
    logger.info(
        fields.pop("message", event),
        extra={"event": event, **fields},
    )
