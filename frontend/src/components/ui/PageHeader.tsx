import type { ReactNode } from "react"

interface PageHeaderProps {
  eyebrow?: string
  title: string
  meta?: ReactNode
  description?: string
  extra?: ReactNode
}

/** 管理页面统一页头：明确页面身份、用途和首要操作。 */
export function PageHeader({
  eyebrow,
  title,
  meta,
  description,
  extra,
}: PageHeaderProps) {
  return (
    <header className="qa-page-header">
      <div className="qa-page-header__content">
        {eyebrow ? <span className="qa-page-header__eyebrow">{eyebrow}</span> : null}
        <div className="qa-page-header__title-row">
          <h1>{title}</h1>
          {meta ? <span className="qa-page-header__meta">{meta}</span> : null}
        </div>
        {description ? <p>{description}</p> : null}
      </div>
      {extra ? <div className="qa-page-header__extra">{extra}</div> : null}
    </header>
  )
}
