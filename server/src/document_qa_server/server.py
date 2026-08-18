"""ASGI 应用入口，供 uvicorn（document_qa_server:app）使用。"""

from document_qa_server.api.app import create_app

app = create_app()
