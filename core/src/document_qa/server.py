"""界面化 API 服务的兼容入口。

应用本体见 document_qa.api.app.create_app；本文件只保留模块级 app，
供 uvicorn（document_qa.server:app）和旧引用使用。
"""

from document_qa.api.app import create_app

app = create_app()
