"""`python -m document_qa_server` 启动本机 API 服务。"""

import argparse


def main() -> int:
    """解析参数并在指定地址启动 uvicorn；默认值来自 DQA_ 配置。

    --reload 开发模式：uvicorn 监听本包源码变更并自动重启进程，
    改代码后无需手动重启（生产部署不要开启）。同时挂载 core 源码
    目录——server 依赖 core 的可编辑安装，core 代码变更同样生效。
    """

    from document_qa_server.settings import load_settings

    settings = load_settings()
    parser = argparse.ArgumentParser(
        prog="document-qa-server",
        description="Structured Visual QA 界面化 API 服务。",
    )
    parser.add_argument("--host", default=settings.host, help="监听地址")
    parser.add_argument("--port", type=int, default=settings.port, help="监听端口")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="开发模式：源码变更自动重启（监听 server 与 core 包）",
    )
    args = parser.parse_args()

    import uvicorn

    if args.reload:
        # reload 模式要求 import 字符串（而非 app 对象），让重载器
        # 每次重新执行模块导入；监听范围限本包与 core 源码目录，
        # 避免产物目录（webapp-artifacts）变化触发无谓重启。
        from document_qa_server import settings as settings_module
        from pathlib import Path

        package_root = Path(settings_module.__file__).resolve().parent
        core_root = package_root.parents[2] / "core" / "src"
        reload_dirs = [str(package_root)]
        if core_root.is_dir():
            reload_dirs.append(str(core_root))
        uvicorn.run(
            "document_qa_server.server:app",
            host=args.host,
            port=args.port,
            log_level="info",
            reload=True,
            reload_dirs=reload_dirs,
            reload_includes=["*.py"],
        )
        return 0

    from document_qa_server.server import app

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
