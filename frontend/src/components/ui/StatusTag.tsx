import { Tag } from "antd"
import { STATUS_META } from "../../uiTokens"

interface StatusTagProps {
  status: string
}

/** 文档状态统一展示，避免页面自行映射文案和颜色。 */
export function StatusTag({ status }: StatusTagProps) {
  const meta = STATUS_META[status]

  if (!meta) return <Tag className="qa-status-tag">{status}</Tag>

  return (
    <Tag
      className="qa-status-tag"
      variant="filled"
      style={{ color: meta.color, background: meta.background }}
    >
      <span className="qa-status-tag__dot" style={{ background: meta.accent ?? meta.color }} />
      {meta.label}
    </Tag>
  )
}
