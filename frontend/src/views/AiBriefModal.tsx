/** AI 排查任务书弹窗（开发者模式）：追加描述 + 实时预览 + 剪贴板复制。
 *
 * 复制失败（权限/不支持）时降级为预览区手动全选复制；组件不持久化
 * 任何状态，关闭即重置。
 */

import { useEffect, useMemo, useState } from "react"
import { Input, message, Modal, Typography } from "antd"
import type { QAReport } from "../api"
import { buildIssueBrief, type BriefIssue } from "../features/workbench/model/ai-brief"

export function AiBriefModal({
  open,
  issues,
  report,
  historyRecordId,
  sourceDisplay,
  targetDisplay,
  onClose,
}: {
  open: boolean
  issues: BriefIssue[]
  report: QAReport
  historyRecordId: string | null
  sourceDisplay: string
  targetDisplay: string
  onClose: () => void
}) {
  const [note, setNote] = useState("")
  const [busy, setBusy] = useState(false)
  const [messageApi, contextHolder] = message.useMessage()

  useEffect(() => {
    if (open) setNote("")
  }, [open])

  const brief = useMemo(
    () =>
      buildIssueBrief({
        report,
        issues,
        historyRecordId,
        sourceDisplay,
        targetDisplay,
        note,
      }),
    [report, issues, historyRecordId, sourceDisplay, targetDisplay, note],
  )

  const copyBrief = async () => {
    setBusy(true)
    try {
      await navigator.clipboard.writeText(brief)
      messageApi.success("任务书已复制，请粘贴到 AI 对话中开始排查")
      onClose()
    } catch {
      messageApi.warning("自动复制失败，请在下方预览区手动全选复制")
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      open={open}
      title={`AI 排查任务书（${issues.length} 条）`}
      width={860}
      destroyOnHidden
      onCancel={onClose}
      okText="复制任务书"
      okButtonProps={{ loading: busy }}
      onOk={() => void copyBrief()}
    >
      {contextHolder}
      <Input.TextArea
        aria-label="追加描述"
        placeholder="追加描述（可选）：补充复现步骤、期望行为或业务背景，将原文随任务书提供给 AI…"
        value={note}
        maxLength={2000}
        autoSize={{ minRows: 2, maxRows: 4 }}
        onChange={(event) => setNote(event.target.value)}
      />
      <Typography.Text type="secondary" className="ai-brief-hint">
        任务书包含 issue 完整 metrics 证据、疑似代码位置与本项目的开发契约约定；AI 将按契约排查与修复。
      </Typography.Text>
      <pre className="ai-brief-preview">{brief}</pre>
    </Modal>
  )
}
