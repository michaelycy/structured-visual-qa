"""`python -m document_qa_server` 启动本机 API 服务。"""

import argparse


def main() -> int:
    """解析端口参数并在回环地址启动 uvicorn。"""

    parser = argparse.ArgumentParser(
        prog="document-qa-server",
        description="Structured Visual QA 界面化 API 服务。",
    )
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=8765, help="监听端口")
    args = parser.parse_args()

    import uvicorn

    from document_qa_server.server import app

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
