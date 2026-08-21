import type { ReactNode } from "react"
import { cn } from "../../lib/cn"

interface PageSectionProps {
  title?: ReactNode
  description?: ReactNode
  extra?: ReactNode
  children: ReactNode
  className?: string
}

/** 页面内容区块：统一承载标题、说明、工具栏和主体内容。 */
export function PageSection({
  title,
  description,
  extra,
  children,
  className,
}: PageSectionProps) {
  const hasHeader = title || description || extra

  return (
    <section className={cn("qa-page-section", className)}>
      {hasHeader ? (
        <div className="qa-page-section__header">
          {title || description ? (
            <div>
              {title ? <h2>{title}</h2> : null}
              {description ? <p>{description}</p> : null}
            </div>
          ) : null}
          {extra ? <div className="qa-page-section__extra">{extra}</div> : null}
        </div>
      ) : null}
      <div className="qa-page-section__body">{children}</div>
    </section>
  )
}
