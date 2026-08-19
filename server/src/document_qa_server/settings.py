"""服务运行配置：集中管理、环境变量与 .env 可覆盖。

默认值与历史硬编码行为完全一致（回环地址、8765 端口、项目根
webapp-artifacts/），部署时用 DQA_ 前缀环境变量或 .env 覆盖。
"""

from __future__ import annotations

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


def load_settings() -> ServerSettings:
    """读取配置；构造失败（如 .env 非法）由调用方转为启动错误。"""

    return ServerSettings()
