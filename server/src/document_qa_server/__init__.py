"""Structured Visual QA 界面化服务包。

只包含 HTTP 协议层（api/）与应用服务层（services/），核心引擎在
独立的 document-qa 发行包中。依赖方向：api → services → document_qa。
ASGI 应用实例见 document_qa_server.server:app。
"""
