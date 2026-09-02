"""渲染验证层（T38）：检测主张的像素级实证。

阶段 1（shadow）：只对已注册类型的 Issue 输出裁决事件，不改变任何
检测输出。裁决经管线的 progress 事件通道输出（stage="verification"），
服务端落入任务进度 JSONL；metrics 落盘与严重度变更推迟到 enforce 期。
配置为引擎级常量（settings.VerificationSettings）——RuleProfile 全量
快照会进报告，enforce 期才随 Golden 更新迁入 Profile。
"""

from document_qa.verification.service import VerificationService
from document_qa.verification.settings import VerificationSettings

__all__ = ["VerificationService", "VerificationSettings"]
