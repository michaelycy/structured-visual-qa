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

/** 序号角标：图上红框左上角与 Issue 列表行首共用，保证两侧对应。 */
export function IssueBadge({ index, active }: { index: number; active?: boolean }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: 18,
        height: 18,
        borderRadius: 9,
        background: active ? "#cf1322" : "#fff",
        color: active ? "#fff" : "#cf1322",
        border: `1.5px solid ${active ? "#cf1322" : "rgba(180,35,24,0.85)"}`,
        fontSize: 11,
        fontWeight: 600,
        lineHeight: 1,
        flexShrink: 0,
      }}
    >
      {index + 1}
    </span>
  )
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
  // 同一目标区域的多个 Issue（同 bbox，如偏移+字号变化）共用一个红框，
  // 角标横排——避免同位置叠出多个框和重叠角标（与列表分组同键）。
  const bboxGroups = useMemo(
    () => groupIssuesByBbox(issues.filter((issue) => issue.bbox)),
    [issues],
  )

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
              bboxGroups.map((group) => {
                const first = group[0].issue
                // 组内任一 Issue 激活即整框加粗，便于定位整组。
                const groupActive = group.some(
                  ({ issue }) => issue.id === activeIssueId,
                )
                return (
                  <div
                    key={first.id}
                    style={{
                      position: "absolute",
                      border: groupActive
                        ? "3px solid #cf1322"
                        : "2px solid rgba(180,35,24,0.75)",
                      background: groupActive
                        ? "rgba(180,35,24,0.2)"
                        : "rgba(180,35,24,0.08)",
                      left: `${(first.bbox!.x / pageWidth) * 100}%`,
                      top: `${(first.bbox!.y / pageHeight) * 100}%`,
                      width: `${(first.bbox!.width / pageWidth) * 100}%`,
                      height: `${(first.bbox!.height / pageHeight) * 100}%`,
                      pointerEvents: "none",
                    }}
                  >
                    {/* 序号角标横排：与列表行首序号对应；同框多问题时
                        逐个排列（如 ②③），不互相遮挡。 */}
                    <span
                      style={{
                        position: "absolute",
                        top: -10,
                        left: -10,
                        display: "flex",
                        gap: 2,
                      }}
                    >
                      {group.map(({ issue, index }) => (
                        <IssueBadge
                          key={issue.id}
                          index={index}
                          active={issue.id === activeIssueId}
                        />
                      ))}
                    </span>
                  </div>
                )
              })}
          </div>
        </Col>
      )}
    </Row>
  )
}

/** 复核状态筛选选项。 */
type ReviewFilter = "all" | "pending" | "done"

/** 严重度排序权重：组内展示取最高严重度。 */
const SEVERITY_ORDER: Record<string, number> = {
  critical: 4,
  high: 3,
  medium: 2,
  low: 1,
  info: 0,
}

/** 按页内 Issue 列表生成分组：同 bbox 的多条合并为一组（与图上红框
 * 分组同键），无 bbox 的独立成组。返回 [(组键, [issue, index][])]。
 */
export function groupIssuesByBbox(issues: Issue[]): { issue: Issue; index: number }[][] {
  const groups = new Map<string, { issue: Issue; index: number }[]>()
  issues.forEach((issue, index) => {
    const key = issue.bbox
      ? [
          issue.bbox.x,
          issue.bbox.y,
          issue.bbox.width,
          issue.bbox.height,
        ]
          .map((value) => Math.round(value))
          .join(",")
      : `solo-${issue.id}`
    const bucket = groups.get(key)
    if (bucket) bucket.push({ issue, index })
    else groups.set(key, [{ issue, index }])
  })
  return [...groups.values()]
}

/** Issue 展开详情：定位状态 + 阈值/差异明细，让"哪里出的问题"可读。 */
function IssueDetails({
  issue,
  decisions,
  onDecide,
  onHighlight,
  hideLocation = false,
}: {
  issue: Issue
  decisions: Record<string, ReviewDecision>
  onDecide: (issueId: string, decision: ReviewDecision) => void
  onHighlight: (issueId: string) => void
  /** 合并组内非首条不重复"位置"行。 */
  hideLocation?: boolean
}) {
  // 数字不一致的差集明细按"缺失/多余"分组展示，比原始 metrics 更直观。
  const metrics = issue.metrics ?? {}
  // 原文/译文对照：先取局部变量再收窄类型，避免 Record<string, unknown>
  // 索引访问的 typeof 收窄不生效。
  const sourceText = typeof metrics.source_text === "string" ? metrics.source_text : null
  const targetText = typeof metrics.target_text === "string" ? metrics.target_text : null
  const numberDetail = (
    ["missing_numbers", "extra_numbers"] as const
  ).filter((key) => Array.isArray(metrics[key]) && metrics[key].length)
  return (
    <Space direction="vertical" size={6} onClick={(e) => e.stopPropagation()}>
      {!hideLocation && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {issue.bbox
            ? `位置：目标文档第 ${issue.page} 页红框处（点击列表项可在图中高亮）`
            : "位置：无法定位到具体区域（差异为页面级，请对照左右两页人工检查）"}
        </Typography.Text>
      )}
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
      {/* 原文 → 译文对照：文本类问题（漏译/碎片化/隐形）必须能看到
          两侧内容，否则无法判断是翻译错还是渲染错。 */}
      {(sourceText || targetText) && !numberDetail.length && (
        <Space direction="vertical" size={2} style={{ fontSize: 12 }}>
          {sourceText && (
            <div>
              <Typography.Text type="secondary">原文：</Typography.Text>
              <Typography.Text>{sourceText}</Typography.Text>
            </div>
          )}
          {targetText && (
            <div>
              <Typography.Text type="secondary">译文：</Typography.Text>
              <Typography.Text type="danger">{targetText}</Typography.Text>
            </div>
          )}
        </Space>
      )}
      {/* 其余 metrics（阈值、比例、样本文本）逐项罗列，便于复核追溯。
          原文/译文已在上方对照展示，此处排除避免重复。 */}
      {Object.entries(metrics)
        .filter(
          ([key]) =>
            !numberDetail.includes(key as never) &&
            key !== "source_text" &&
            key !== "target_text",
        )
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
              items={groupIssuesByBbox(visibleIssues).map((group) => {
                // 组内展示取最高严重度；类型去重后逐个列出。
                const top = group.reduce((acc, cur) =>
                  (SEVERITY_ORDER[cur.issue.severity] ?? 0) >
                  (SEVERITY_ORDER[acc.issue.severity] ?? 0)
                    ? cur
                    : acc,
                )
                const types = [...new Set(group.map(({ issue }) => issue.type))]
                const decisionsAll = group.map(({ issue }) => decisions[issue.id])
                return {
                  key: group[0].issue.id,
                  label: (
                    <Space wrap size={8}>
                      {/* 组内全部序号角标：与目标页红框上的横排角标一致。 */}
                      {group.map(({ issue, index }) => (
                        <IssueBadge
                          key={issue.id}
                          index={index}
                          active={issue.id === activeIssueId}
                        />
                      ))}
                      <Tag color={SEVERITY_META[top.issue.severity]?.color}>
                        {SEVERITY_META[top.issue.severity]?.label ??
                          top.issue.severity}
                      </Tag>
                      {types.map((type) => (
                        <Tag
                          key={type}
                          bordered={false}
                          style={{ color: "rgba(0,0,0,0.58)" }}
                        >
                          {ISSUE_TYPE_META[type] ?? type}
                        </Tag>
                      ))}
                      <span>{top.issue.description}</span>
                      {group.length > 1 && (
                        <Tag bordered={false} color="volcano">
                          {group.length} 个问题
                        </Tag>
                      )}
                      {!group[0].issue.bbox && (
                        <Tag bordered={false} color="warning">
                          图上无定位
                        </Tag>
                      )}
                      {decisionsAll.every(Boolean) && decisionsAll[0] && (
                        <Tag color={DECISION_META[decisionsAll[0]].color}>
                          {DECISION_META[decisionsAll[0]].label}
                        </Tag>
                      )}
                    </Space>
                  ),
                  children: (
                    <Space direction="vertical" size={12}>
                      {/* 组内多条合并展示，但复核判定按 Issue 粒度独立。 */}
                      {group.map(({ issue }, memberIndex) => (
                        <div
                          key={issue.id}
                          style={
                            memberIndex > 0
                              ? {
                                  borderTop: "1px dashed #d9d9d9",
                                  paddingTop: 8,
                                }
                              : undefined
                          }
                        >
                          {group.length > 1 && (
                            <Space size={6} style={{ marginBottom: 4 }}>
                              <IssueBadge
                                index={group[memberIndex].index}
                                active={issue.id === activeIssueId}
                              />
                              <Tag bordered={false} color="error">
                                {ISSUE_TYPE_META[issue.type] ?? issue.type}
                              </Tag>
                            </Space>
                          )}
                          <IssueDetails
                            issue={issue}
                            decisions={decisions}
                            onDecide={onDecide}
                            onHighlight={setActiveIssueId}
                            hideLocation={memberIndex > 0}
                          />
                        </div>
                      ))}
                    </Space>
                  ),
                }
              })}
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
