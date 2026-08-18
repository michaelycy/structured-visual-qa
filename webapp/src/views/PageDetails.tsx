import { useState } from "react"
import type { Issue, QAReport } from "../api"

const STATUS_LABEL: Record<string, string> = {
  pass: "通过",
  review: "复核",
  fail: "失败",
}

/** 单条问题的可展开行：描述、位置与触发指标。 */
function IssueRow({ issue }: { issue: Issue }) {
  const [open, setOpen] = useState(false)
  return (
    <li className={`issue sev-${issue.severity}`}>
      <button className="issue-head" onClick={() => setOpen(!open)}>
        <span className={`sev-badge sev-${issue.severity}`}>{issue.severity}</span>
        <span className="issue-type">{issue.type}</span>
        <span className="issue-desc">{issue.description}</span>
        <span className="issue-caret">{open ? "收起" : "指标"}</span>
      </button>
      {open && (
        <div className="issue-body">
          {issue.bbox && (
            <p>
              位置 x={issue.bbox.x.toFixed(1)} y={issue.bbox.y.toFixed(1)} w=
              {issue.bbox.width.toFixed(1)} h={issue.bbox.height.toFixed(1)}
            </p>
          )}
          <pre>{JSON.stringify(issue.metrics, null, 2)}</pre>
        </div>
      )}
    </li>
  )
}

/** 左侧页面列表 + 右侧所选页面的问题明细。 */
export function PageDetails({ report }: { report: QAReport }) {
  const problems = report.pages.filter((page) => page.status !== "pass")
  const [selected, setSelected] = useState<number | null>(
    problems[0]?.page ?? report.pages[0]?.page ?? null,
  )
  const page = report.pages.find((item) => item.page === selected)

  return (
    <section className="pages">
      <div className="page-list">
        {report.pages.map((item) => (
          <button
            key={item.page}
            className={`page-item status-${item.status}${
              item.page === selected ? " selected" : ""
            }`}
            onClick={() => setSelected(item.page)}
          >
            <span>第 {item.page} 页</span>
            <span className="page-score">{item.score.toFixed(0)}</span>
            <span className="page-status">{STATUS_LABEL[item.status]}</span>
          </button>
        ))}
      </div>
      <div className="page-detail">
        {page ? (
          <>
            <h2>
              第 {page.page} 页 · {STATUS_LABEL[page.status]} · {page.score.toFixed(1)} 分
            </h2>
            {page.issues.length ? (
              <ul className="issue-list">
                {page.issues.map((issue) => (
                  <IssueRow key={issue.id} issue={issue} />
                ))}
              </ul>
            ) : (
              <p className="empty">本页没有发现问题。</p>
            )}
          </>
        ) : (
          <p className="empty">选择左侧页面查看详情。</p>
        )}
      </div>
    </section>
  )
}
