"""`python -m document_qa_server` 启动本机 API 服务。"""

import argparse


def main() -> int:
    """解析参数并在指定地址启动 uvicorn；默认值来自 DQA_ 配置。"""

    from document_qa_server.settings import load_settings

    settings = load_settings()
    parser = argparse.ArgumentParser(
        prog="document-qa-server",
        description="Structured Visual QA 界面化 API 服务。",
    )
    parser.add_argument("--host", default=settings.host, help="监听地址")
    parser.add_argument("--port", type=int, default=settings.port, help="监听端口")
    args = parser.parse_args()

    import uvicorn

    from document_qa_server.server import app

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
