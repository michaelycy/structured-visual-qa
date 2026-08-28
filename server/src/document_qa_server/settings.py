"""服务运行配置：集中管理、环境变量与 .env 可覆盖。

默认值与历史硬编码行为完全一致（回环地址、8765 端口、项目根
webapp-artifacts/），部署时用 DQA_ 前缀环境变量或 .env 覆盖。
"""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根（server/src/document_qa_server/settings.py 上退四级）。
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


class ServerSettings(BaseSettings):
    """document-qa-server 的全部运行参数。"""

    model_config = SettingsConfigDict(
        env_prefix="DQA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 8765
    artifacts_dir: Path = _PROJECT_ROOT / "webapp-artifacts"
    samples_dir: Path = _PROJECT_ROOT / "examples"
    max_upload_bytes: int = 100 * 1024 * 1024
    # CORS 收紧为显式来源（对抗审查 H-1：allow_origins=["*"] 配合任意
    # 本地路径输入，恶意网页可跨源读取本机文档报告）。默认只放行
    # 本地前端开发服务器；生产经 DQA_CORS_ORIGINS 显式扩展。
    cors_origins: list[str] = [
        "http://127.0.0.1:5180",
        "http://localhost:5180",
    ]
    # 比较任务异步模式：True 时 compare 立即返回 task_id 由后台执行；
    # False 时保持同步阻塞行为（CLI/测试回归路径）。
    async_mode: bool = True
    # 持久化日志（T20）：JSON 事件与 uvicorn 访问/错误日志按天轮转落盘，
    # 便于事后排障；关闭后退回纯 stderr/stdout（与历史行为一致）。
    log_file_enabled: bool = True
    # None 表示跟随 artifacts_dir/logs；显式路径供部署侧分离数据与日志。
    log_dir: Path | None = None
    # 按天轮转后保留的历史文件数；超出自动删除，给磁盘占用一个上界。
    log_retention_days: int = 14
    # OCR 为可选增强能力；关闭时不加载 PaddleOCR 或模型依赖。
    ocr_enabled: bool = False
    ocr_provider: str = "paddle"
    ocr_device: str = "cpu"
    ocr_language: str = "ch"
    ocr_version: str = "PP-OCRv6"
    # None 时使用 artifacts_dir/ocr-cache，避免模型写进用户主目录。
    ocr_cache_dir: Path | None = None
    ocr_detection_model_dir: Path | None = None
    ocr_recognition_model_dir: Path | None = None


def load_settings() -> ServerSettings:
    """读取配置；构造失败（如 .env 非法）由调用方转为启动错误。

    绑定非回环地址时输出安全告警：compare 接受服务器本地任意文档
    路径（内网质检工作台的既定用法），暴露到非回环网络等于允许
    该网段读取本机文档的分析结果，必须显式知情。
    """

    settings = ServerSettings()
    if settings.host not in ("127.0.0.1", "localhost", "::1"):
        logging.getLogger("document_qa_server").warning(
            "DQA_HOST=%s 为非回环地址：API 将接受该网络上任意客户端的"
            "比较请求，且可引用服务器本地任意 PDF/Office 路径。生产部署"
            "请配套网络隔离或认证网关。",
            settings.host,
        )
    return settings
