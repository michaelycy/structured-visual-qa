"""FastAPI 应用工厂与路由组装。"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from document_qa.services import (
    CompareService,
    FileService,
    ProfileService,
    VerifyService,
)


def create_app(*, artifacts_dir: Path | None = None) -> FastAPI:
    """构建应用实例；artifacts_dir 缺省落在项目根 webapp-artifacts/。"""

    # api/app.py 位于 <root>/src/document_qa/api/，上退四级到项目根，
    # 产物目录 webapp-artifacts/ 保持不入源码树。
    project_root = artifacts_dir.resolve().parent if artifacts_dir else Path(
        __file__
    ).resolve().parents[3]
    root = artifacts_dir or project_root / "webapp-artifacts"
    root.mkdir(parents=True, exist_ok=True)

    # 服务实例在应用级创建一次；互斥锁因此对全部请求生效。
    compare_service = CompareService(artifacts_dir=root)
    verify_service = VerifyService(artifacts_dir=root)
    profile_service = ProfileService(artifacts_dir=root)
    file_service = FileService(
        artifacts_dir=root, samples_dir=project_root / "examples"
    )

    app = FastAPI(title="Structured Visual QA", version="0.1.0")
    # 前端开发服务器运行在其他端口，需要允许跨源访问本 API。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 把服务实例挂到 app.state，路由通过依赖注入获取，避免模块级单例。
    app.state.compare = compare_service
    app.state.verify = verify_service
    app.state.profiles = profile_service
    app.state.files = file_service

    from document_qa.api.routes_compare import router as compare_router
    from document_qa.api.routes_files import router as files_router
    from document_qa.api.routes_profile import router as profile_router
    from document_qa.api.routes_verify import router as verify_router

    app.include_router(compare_router)
    app.include_router(verify_router)
    app.include_router(profile_router)
    app.include_router(files_router)

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
