/** 逐页详情：页面选择 + 源/目标渲染图对比 + Issue 列表（含人工判定与筛选）。 */

import { useMemo, useState } from "react"
import {
  Button,
  Col,
  Collapse,
  Empty,
  Progress,
  Row,
  Segmented,
  Select,
  Space,
  Tag,
  Typography,
} from "antd"
import type { Issue, QAReport, ReviewDecision } from "../api"
import { DECISION_META, ISSUE_TYPE_META, SEVERITY_META, STATUS_META } from "../uiTokens"

function pageImage(
  side: "source" | "target",
  page: number,
  rendered: { source: string[]; target: string[] } | undefined,
): string | null {
  // rendered 元素是相对 pages/ 根的完整路径（task-xxx/side/page-0001.png）。
  const name = `page-${String(page).padStart(4, "0")}.png`
  const match = rendered?.[side].find((entry) => entry.endsWith(`/${side}/${name}`))
  return match ? `/api/pages/${match}` : null
}

/** 源/目标渲染图并排对比，目标图叠加 Issue 红框（BBox 为 PDF point）。 */
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
  // 渲染 dpi=144 即 2px/point；图片加载后由自然宽度反推页面 point 尺寸。
  const [pageWidth, setPageWidth] = useState(0)
  const [pageHeight, setPageHeight] = useState(0)

  if (!sourceUrl && !targetUrl) {
    return (
      <Empty
        description="本页无渲染图：默认只渲染需复核页面，历史记录回看也不含渲染图（可在工作台重新比较生成）。"
        image={Empty.PRESENTED_IMAGE_SIMPLE}
      />
    )
  }

  return (
    <Row gutter={12}>
      {sourceUrl && (
        <Col span={12}>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            源文档 · 第 {page} 页
          </Typography.Text>
          <div style={{ marginTop: 4 }}>
            <img
              src={sourceUrl}
              alt={`源文档第 ${page} 页`}
              style={{ width: "100%", border: "1px solid #d9d9d9", borderRadius: 6 }}
            />
          </div>
        </Col>
      )}
      {targetUrl && (
        <Col span={sourceUrl ? 12 : 24}>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            目标文档 · 第 {page} 页（红框为问题位置）
          </Typography.Text>
          <div style={{ marginTop: 4, position: "relative" }}>
            <img
              src={targetUrl}
              alt={`目标文档第 ${page} 页`}
              style={{ width: "100%", border: "1px solid #d9d9d9", borderRadius: 6 }}
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
                    style={{
                      position: "absolute",
                      border:
                        issue.id === activeIssueId
                          ? "3px solid #cf1322"
                          : "2px solid rgba(180,35,24,0.75)",
                      background:
                        issue.id === activeIssueId
                          ? "rgba(180,35,24,0.2)"
                          : "rgba(180,35,24,0.08)",
                      left: `${(issue.bbox!.x / pageWidth) * 100}%`,
                      top: `${(issue.bbox!.y / pageHeight) * 100}%`,
                      width: `${(issue.bbox!.width / pageWidth) * 100}%`,
                      height: `${(issue.bbox!.height / pageHeight) * 100}%`,
                      pointerEvents: "none",
                    }}
                  />
                ))}
          </div>
        </Col>
      )}
    </Row>
  )
}

/** 复核状态筛选选项。 */
type ReviewFilter = "all" | "pending" | "done"

/** Issue 展开详情：定位状态 + 阈值/差异明细，让"哪里出的问题"可读。 */
function IssueDetails({
  issue,
  decisions,
  onDecide,
  onHighlight,
}: {
  issue: Issue
  decisions: Record<string, ReviewDecision>
  onDecide: (issueId: string, decision: ReviewDecision) => void
  onHighlight: (issueId: string) => void
}) {
  // 数字不一致的差集明细按"缺失/多余"分组展示，比原始 metrics 更直观。
  const metrics = issue.metrics ?? {}
  const numberDetail = (
    ["missing_numbers", "extra_numbers"] as const
  ).filter((key) => Array.isArray(metrics[key]) && metrics[key].length)
  return (
    <Space direction="vertical" size={6} onClick={(e) => e.stopPropagation()}>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {issue.bbox
          ? `位置：目标文档第 ${issue.page} 页红框处（点击列表项可在图中高亮）`
          : "位置：无法定位到具体区域（差异为页面级，请对照左右两页人工检查）"}
      </Typography.Text>
      {numberDetail.length > 0 && (
        <Space wrap size={8}>
          {numberDetail.map((key) => (
            <Tag key={key} color={key === "missing_numbers" ? "red" : "orange"}>
              {key === "missing_numbers" ? "源有目标无" : "目标多出"}：
              {(metrics[key] as (string | number)[]).join("、")}
            </Tag>
          ))}
        </Space>
      )}
      {/* 其余 metrics（阈值、比例、样本文本）逐项罗列，便于复核追溯。 */}
      {Object.entries(metrics)
        .filter(([key]) => !numberDetail.includes(key as never))
        .map(([key, value]) => (
          <Typography.Text key={key} type="secondary" style={{ fontSize: 12 }}>
            {key}：{Array.isArray(value) ? value.join("、") : String(value)}
          </Typography.Text>
        ))}
      <Space>
        {(Object.keys(DECISION_META) as ReviewDecision[]).map((key) => (
          <Button
            key={key}
            size="small"
            type={decisions[issue.id] === key ? "primary" : "default"}
            onClick={() => {
              onHighlight(issue.id)
              onDecide(issue.id, key)
            }}
          >
            {DECISION_META[key].label}
          </Button>
        ))}
      </Space>
    </Space>
  )
}

export function PageDetails({
  report,
  rendered,
  taskId,
  decisions,
  onDecide,
}: {
  report: QAReport
  rendered?: { source: string[]; target: string[] }
  taskId: string | null
  decisions: Record<string, ReviewDecision>
  onDecide: (issueId: string, decision: ReviewDecision) => void
}) {
  const problems = report.pages.filter((page) => page.status !== "pass")
  const [selected, setSelected] = useState<number | null>(
    problems[0]?.page ?? report.pages[0]?.page ?? null,
  )
  const [activeIssueId, setActiveIssueId] = useState<string | null>(null)
  // 复核工作流筛选：只看某种严重度 / 只看未复核，处理上百条 Issue 时定位更快。
  const [severityFilter, setSeverityFilter] = useState<string[]>([])
  const [reviewFilter, setReviewFilter] = useState<ReviewFilter>("all")
  const page = report.pages.find((item) => item.page === selected)
  const totalIssues = report.pages.reduce((sum, p) => sum + p.issues.length, 0)
  const reviewed = Object.keys(decisions).length

  // 当前页按筛选条件过滤后的 Issue；红框同步使用过滤结果。
  const visibleIssues = useMemo(() => {
    let list = page?.issues ?? []
    if (severityFilter.length) {
      list = list.filter((issue) => severityFilter.includes(issue.severity))
    }
    if (reviewFilter === "pending") {
      list = list.filter((issue) => !decisions[issue.id])
    } else if (reviewFilter === "done") {
      list = list.filter((issue) => decisions[issue.id])
    }
    return list
  }, [page, severityFilter, reviewFilter, decisions])

  return (
    <Space direction="vertical" size={12} style={{ width: "100%" }}>
      <Space wrap>
        <Select
          style={{ minWidth: 220 }}
          value={selected}
          onChange={(value) => {
            setSelected(value)
            setActiveIssueId(null)
          }}
          options={report.pages.map((item) => ({
            value: item.page,
            label: `第 ${item.page} 页 · ${item.score.toFixed(0)} 分 · ${
              STATUS_META[item.status]?.label ?? item.status
            }${item.issues.length ? ` · ${item.issues.length} 个问题` : ""}`,
          }))}
          showSearch
          optionFilterProp="label"
        />
        {taskId && (
          <Progress
            percent={totalIssues ? Math.round((reviewed / totalIssues) * 100) : 100}
            size="small"
            style={{ width: 180 }}
            format={() => `复核 ${reviewed}/${totalIssues}`}
          />
        )}
      </Space>

      {page ? (
        <>
          {/* key 按页重挂载：换页时清掉上一页的尺寸状态，避免红框按旧尺寸错位闪现。 */}
          <PageCompare
            key={page.page}
            page={page.page}
            issues={visibleIssues}
            rendered={rendered}
            activeIssueId={activeIssueId}
          />
          {page.issues.length > 0 && (
            <Space wrap>
              <Select
                mode="multiple"
                allowClear
                placeholder="按严重度筛选"
                style={{ minWidth: 200 }}
                value={severityFilter}
                onChange={setSeverityFilter}
                options={Object.entries(SEVERITY_META).map(([key, meta]) => ({
                  value: key,
                  label: meta.label,
                }))}
              />
              <Segmented
                value={reviewFilter}
                onChange={(value) => setReviewFilter(value as ReviewFilter)}
                options={[
                  { value: "all", label: `全部 ${page.issues.length}` },
                  {
                    value: "pending",
                    label: `未复核 ${
                      page.issues.filter((issue) => !decisions[issue.id]).length
                    }`,
                  },
                  {
                    value: "done",
                    label: `已复核 ${
                      page.issues.filter((issue) => decisions[issue.id]).length
                    }`,
                  },
                ]}
              />
            </Space>
          )}
          {page.issues.length === 0 ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="本页没有发现问题。"
            />
          ) : visibleIssues.length === 0 ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="当前筛选条件下没有匹配的问题，可调整筛选。"
            />
          ) : (
            <Collapse
              size="small"
              activeKey={activeIssueId ?? undefined}
              onChange={(keys) =>
                setActiveIssueId(
                  Array.isArray(keys) ? keys[0] ?? null : keys ?? null,
                )
              }
              items={visibleIssues.map((issue) => ({
                key: issue.id,
                label: (
                  <Space wrap size={8}>
                    <Tag color={SEVERITY_META[issue.severity]?.color}>
                      {SEVERITY_META[issue.severity]?.label ?? issue.severity}
                    </Tag>
                    <Tag bordered={false} style={{ color: "rgba(0,0,0,0.58)" }}>
                      {ISSUE_TYPE_META[issue.type] ?? issue.type}
                    </Tag>
                    <span>{issue.description}</span>
                    {/* 无 bbox 的 Issue 在图上没有红框，显式标记避免用户在图里找不到。 */}
                    {!issue.bbox && (
                      <Tag bordered={false} color="warning">
                        图上无定位
                      </Tag>
                    )}
                    {decisions[issue.id] && (
                      <Tag color={DECISION_META[decisions[issue.id]].color}>
                        {DECISION_META[decisions[issue.id]].label}
                      </Tag>
                    )}
                  </Space>
                ),
                children: (
                  <IssueDetails
                    issue={issue}
                    decisions={decisions}
                    onDecide={onDecide}
                    onHighlight={setActiveIssueId}
                  />
                ),
              }))}
            />
          )}
        </>
      ) : (
        <Empty
          description="选择页面查看详情。"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      )}
    </Space>
  )
}
