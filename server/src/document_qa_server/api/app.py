"""FastAPI 应用工厂与路由组装。"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from document_qa_server.services import (
    CompareHistoryService,
    CompareService,
    FileService,
    GlossaryService,
    NormalizationService,
    ProfileService,
    ReviewService,
    VerifyService,
)
from document_qa_server.settings import ServerSettings, load_settings


def create_app(
    *,
    artifacts_dir: Path | None = None,
    settings: ServerSettings | None = None,
) -> FastAPI:
    """构建应用实例；配置缺省来自 DQA_ 环境变量/.env（见 settings.py）。"""

    config = settings or load_settings()
    root = artifacts_dir or config.artifacts_dir
    root.mkdir(parents=True, exist_ok=True)

    # 服务实例在应用级创建一次；互斥锁因此对全部请求生效。
    compare_service = CompareService(artifacts_dir=root)
    verify_service = VerifyService(artifacts_dir=root)
    profile_service = ProfileService(artifacts_dir=root)
    file_service = FileService(
        artifacts_dir=root,
        samples_dir=config.samples_dir,
        max_upload_bytes=config.max_upload_bytes,
    )
    normalizer = NormalizationService(artifacts_dir=root)

    app = FastAPI(title="Structured Visual QA", version="0.1.0")
    # 前端开发服务器运行在其他端口，需要允许跨源访问本 API。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 把服务实例挂到 app.state，路由通过依赖注入获取，避免模块级单例。
    app.state.compare = compare_service
    app.state.verify = verify_service
    app.state.profiles = profile_service
    app.state.files = file_service
    app.state.normalizer = normalizer
    app.state.reviews = ReviewService(artifacts_dir=root)
    app.state.history = CompareHistoryService(artifacts_dir=root)
    app.state.glossaries = GlossaryService(artifacts_dir=root)
    # 导出路由需要产物根目录；异步模式开关来自配置。
    app.state.artifacts_dir = root
    app.state.async_mode = config.async_mode

    from document_qa_server.api.routes_compare import router as compare_router
    from document_qa_server.api.routes_files import router as files_router
    from document_qa_server.api.routes_glossary import router as glossary_router
    from document_qa_server.api.routes_history import router as history_router
    from document_qa_server.api.routes_normalize import router as normalize_router
    from document_qa_server.api.routes_report import router as report_router
    from document_qa_server.api.routes_review import router as review_router
    from document_qa_server.api.routes_profile import router as profile_router
    from document_qa_server.api.routes_verify import router as verify_router

    app.include_router(compare_router)
    app.include_router(verify_router)
    app.include_router(profile_router)
    app.include_router(files_router)
    app.include_router(normalize_router)
    app.include_router(review_router)
    app.include_router(history_router)
    app.include_router(glossary_router)
    app.include_router(report_router)

    @app.get("/api/health")
    def health() -> dict:
        """探活端点，同时返回版本号供前端显示。"""

        return {"status": "ok", "engine": "document-qa", "version": app.version}

    # 渲染页以只读静态目录暴露；两侧子目录需先存在才能挂载。
    for side in ("source", "target"):
        (compare_service.render_root() / side).mkdir(parents=True, exist_ok=True)
    app.mount(
        "/api/pages", StaticFiles(directory=compare_service.render_root()), name="pages"
    )
    return app
