import type { ReactNode } from "react"
import { Empty } from "antd"

interface EmptyStateProps {
  title: string
  description?: string
  action?: ReactNode
  compact?: boolean
}

/** 统一空状态：先说明当前结果，再给出原因或下一步。 */
export function EmptyState({
  title,
  description,
  action,
  compact = false,
}: EmptyStateProps) {
  return (
    <Empty
      className={compact ? "qa-empty-state qa-empty-state--compact" : "qa-empty-state"}
      image={Empty.PRESENTED_IMAGE_SIMPLE}
      description={
        <span className="qa-empty-state__description">
          <strong>{title}</strong>
          {description ? <span>{description}</span> : null}
        </span>
      }
    >
      {action}
    </Empty>
  )
}
