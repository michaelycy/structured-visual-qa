import type { QAReport } from "../api"

const STATUS_LABEL: Record<string, string> = {
  pass: "通过",
  review: "需复核",
  fail: "失败",
}

/** 文档级摘要：状态、总分、页面分布与严重度计数。 */
export function ReportOverview({ report }: { report: QAReport }) {
  return (
    <section className="overview">
      <div className="stat-row">
        <div className={`stat status-${report.status}`}>
          <span className="stat-label">文档状态</span>
          <span className="stat-value">{STATUS_LABEL[report.status]}</span>
        </div>
        <div className="stat">
          <span className="stat-label">文档分数</span>
          <span className="stat-value">{report.document_score.toFixed(2)}</span>
        </div>
        <div className="stat">
          <span className="stat-label">页面</span>
          <span className="stat-value">
            {report.summary.pages}
            <small>（{report.summary.passed_pages} 通过 / {report.summary.review_pages} 复核 / {report.summary.failed_pages} 失败）</small>
          </span>
        </div>
        <div className="stat">
          <span className="stat-label">规则配置</span>
          <span className="stat-value stat-mono">{report.rule_profile_reference}</span>
        </div>
      </div>

      <h2>问题严重度分布</h2>
      <ul className="severity-grid">
        {Object.entries(report.summary.issue_counts)
          .filter(([, count]) => count > 0)
          .map(([severity, count]) => (
            <li key={severity} className={`severity sev-${severity}`}>
              <span className="sev-count">{count}</span>
              <span className="sev-name">{severity}</span>
            </li>
          ))}
        {Object.values(report.summary.issue_counts).every((c) => c === 0) && (
          <li className="empty">没有发现任何问题。</li>
        )}
      </ul>
    </section>
  )
}
