import { useRef, useState } from "react"
import type { Issue, QAReport } from "../api"

const STATUS_LABEL: Record<string, string> = {
  pass: "通过",
  review: "复核",
  fail: "失败",
}

/** 页码 → 渲染文件名（与渲染器命名规则一致）。 */
function pageImage(
  side: "source" | "target",
  page: number,
  rendered: { source: string[]; target: string[] } | undefined,
): string | null {
  const name = `page-${String(page).padStart(4, "0")}.png`
  return rendered && rendered[side].includes(name)
    ? `/api/pages/${side}/${name}`
    : null
}

/** 单条问题的可展开行：描述、位置与触发指标。 */
function IssueRow({
  issue,
  active,
  onActivate,
}: {
  issue: Issue
  active: boolean
  onActivate: () => void
}) {
  const [open, setOpen] = useState(false)
  return (
    <li className={`issue sev-${issue.severity}${active ? " issue-active" : ""}`}>
      <button
        className="issue-head"
        onClick={() => {
          setOpen(!open)
          onActivate()
        }}
      >
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

/** 源/目标页面并排对比：目标图叠加 Issue 高亮框（BBox 为 PDF point）。 */
function PageCompare({
  page,
  issues,
  rendered,
  activeIssueId,
}: {
  page: number
  issues: Issue[]
  rendered?: { source: string[]; target: string[] }
  activeIssueId: string | null
}) {
  const sourceUrl = pageImage("source", page, rendered)
  const targetUrl = pageImage("target", page, rendered)
  const targetRef = useRef<HTMLImageElement>(null)
  // 渲染 dpi=144，即 2 像素/point；图片加载后由自然宽度反推页面宽度。
  const [pageWidth, setPageWidth] = useState(0)
  const [pageHeight, setPageHeight] = useState(0)

  if (!sourceUrl && !targetUrl) {
    return (
      <p className="empty">
        本页状态为 PASS，未生成渲染图（比较任务默认只渲染需复核页面）。
      </p>
    )
  }

  return (
    <div className="compare">
      {sourceUrl && (
        <figure className="compare-side">
          <figcaption>源文档 · 第 {page} 页</figcaption>
          <img src={sourceUrl} alt={`源文档第 ${page} 页`} />
        </figure>
      )}
      {targetUrl && (
        <figure className="compare-side">
          <figcaption>目标文档 · 第 {page} 页（红框为问题位置）</figcaption>
          <div className="compare-overlay-wrap">
            <img
              ref={targetRef}
              src={targetUrl}
              alt={`目标文档第 ${page} 页`}
              onLoad={(event) => {
                const img = event.currentTarget
                setPageWidth(img.naturalWidth / 2)
                setPageHeight(img.naturalHeight / 2)
              }}
            />
            {pageWidth > 0 &&
              issues
                .filter((issue) => issue.bbox)
                .map((issue) => (
                  <div
                    key={issue.id}
                    className={
                      issue.id === activeIssueId
                        ? "bbox-box bbox-active"
                        : "bbox-box"
                    }
                    style={{
                      left: `${(issue.bbox!.x / pageWidth) * 100}%`,
                      top: `${(issue.bbox!.y / pageHeight) * 100}%`,
                      width: `${(issue.bbox!.width / pageWidth) * 100}%`,
                      height: `${(issue.bbox!.height / pageHeight) * 100}%`,
                    }}
                  />
                ))}
          </div>
        </figure>
      )}
    </div>
  )
}

/** 左侧页面列表 + 右侧对比图与问题明细。 */
export function PageDetails({
  report,
  rendered,
}: {
  report: QAReport
  rendered?: { source: string[]; target: string[] }
}) {
  const problems = report.pages.filter((page) => page.status !== "pass")
  const [selected, setSelected] = useState<number | null>(
    problems[0]?.page ?? report.pages[0]?.page ?? null,
  )
  const [activeIssueId, setActiveIssueId] = useState<string | null>(null)
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
            onClick={() => {
              setSelected(item.page)
              setActiveIssueId(null)
            }}
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
            <PageCompare
              page={page.page}
              issues={page.issues}
              rendered={rendered}
              activeIssueId={activeIssueId}
            />
            {page.issues.length ? (
              <ul className="issue-list">
                {page.issues.map((issue) => (
                  <IssueRow
                    key={issue.id}
                    issue={issue}
                    active={issue.id === activeIssueId}
                    onActivate={() => setActiveIssueId(issue.id)}
                  />
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
