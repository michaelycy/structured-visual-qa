/** 逐页详情：页面选择 + 源/目标渲染图对比 + Issue 列表（含人工判定与筛选）。 */

import { useMemo, useState } from "react"
import {
  Button,
  Col,
  Empty,
  Row,
  Segmented,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from "antd"
import type { Issue, QAReport, ReviewDecision } from "../api"
import { DECISION_META, ISSUE_TYPE_META, PALETTE, SEVERITY_META, STATUS_META } from "../uiTokens"

const INTEGER_FORMATTER = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 })
const EMPTY_SEVERITIES: string[] = []

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
        background: active ? PALETTE.critical : PALETTE.surface,
        color: active ? PALETTE.surface : PALETTE.critical,
        border: `1.5px solid ${PALETTE.critical}`,
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
        description="本页无渲染图：默认只渲染需复核页面，历史记录回看也不含渲染图（可在工作台重新质检生成）。"
        image={Empty.PRESENTED_IMAGE_SIMPLE}
      />
    )
  }

  return (
    <Row gutter={[14, 14]} className="page-compare">
      {sourceUrl && (
        <Col xs={24} xl={12}>
          <div className="page-compare__panel page-compare__panel--source">
            <div className="page-compare__panel-head">
              <span><i />源文档 · 原文</span>
              <span>第 {page} 页</span>
            </div>
            <div className="page-compare__canvas">
            <img
              src={sourceUrl}
              alt={`源文档第 ${page} 页`}
              className="page-compare__image"
              width={1191}
              height={1684}
              loading="lazy"
              decoding="async"
            />
            </div>
          </div>
        </Col>
      )}
      {targetUrl && (
        <Col xs={24} xl={sourceUrl ? 12 : 24}>
          <div className="page-compare__panel page-compare__panel--target">
            <div className="page-compare__panel-head">
              <span><i />目标文档 · 译文</span>
              <span>第 {page} 页 · 红框为问题位置</span>
            </div>
            <div className="page-compare__canvas">
              <div className="page-compare__target-stage">
                <img
                  src={targetUrl}
                  alt={`目标文档第 ${page} 页`}
                  className="page-compare__image"
                  width={1191}
                  height={1684}
                  loading="lazy"
                  decoding="async"
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
                            ? `3px solid ${PALETTE.critical}`
                            : `2px solid ${PALETTE.critical}`,
                          background: groupActive
                            ? "rgba(255,82,82,0.18)"
                            : "rgba(255,82,82,0.08)",
                          left: `${(first.bbox!.x / pageWidth) * 100}%`,
                          top: `${(first.bbox!.y / pageHeight) * 100}%`,
                          width: `${(first.bbox!.width / pageWidth) * 100}%`,
                          height: `${(first.bbox!.height / pageHeight) * 100}%`,
                          pointerEvents: "none",
                        }}
                      >
                        <span className="page-compare__badges">
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
            </div>
          </div>
        </Col>
      )}
    </Row>
  )
}

/** 复核状态筛选选项。 */
export type ReviewFilter = "all" | "pending" | "done"

export interface PageDetailsViewState {
  page?: number
  issue?: string
  severity?: string[]
  review?: ReviewFilter
  issuePage?: number
}

/** 按页内 Issue 列表生成分组：同 bbox 的多条合并为一组（与图上红框
 * 分组同键），无 bbox 的独立成组。返回 [(组键, [issue, index][])]。
 */
function groupIssuesByBbox(issues: Issue[]): { issue: Issue; index: number }[][] {
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
    <Space orientation="vertical" size={6} onClick={(e) => e.stopPropagation()}>
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
            <Tag
              key={key}
              style={{
                color: key === "missing_numbers" ? PALETTE.critical : PALETTE.warning,
                background:
                  key === "missing_numbers" ? PALETTE.criticalSoft : PALETTE.warningSoft,
                borderColor:
                  key === "missing_numbers" ? PALETTE.criticalSoft : PALETTE.warningSoft,
              }}
            >
              {key === "missing_numbers" ? "源有目标无" : "目标多出"}：
              {(metrics[key] as (string | number)[]).join("、")}
            </Tag>
          ))}
        </Space>
      )}
      {/* 原文 → 译文对照：文本类问题（漏译/碎片化/隐形）必须能看到
          两侧内容，否则无法判断是翻译错还是渲染错。 */}
      {(sourceText || targetText) && !numberDetail.length && (
        <Space orientation="vertical" size={2} style={{ fontSize: 12 }}>
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
  viewState,
  onViewStateChange,
}: {
  report: QAReport
  rendered?: { source: string[]; target: string[] }
  taskId: string | null
  decisions: Record<string, ReviewDecision>
  onDecide: (issueId: string, decision: ReviewDecision) => void
  viewState?: PageDetailsViewState
  onViewStateChange?: (state: PageDetailsViewState) => void
}) {
  const problems = report.pages.filter((page) => page.status !== "pass")
  const defaultPage = problems[0]?.page ?? report.pages[0]?.page ?? null
  const [localSelected, setLocalSelected] = useState<number | null>(defaultPage)
  const [localActiveIssueId, setLocalActiveIssueId] = useState<string | null>(null)
  // 复核工作流筛选：只看某种严重度 / 只看未复核，处理上百条 Issue 时定位更快。
  const [localSeverityFilter, setLocalSeverityFilter] = useState<string[]>([])
  const [localReviewFilter, setLocalReviewFilter] = useState<ReviewFilter>("all")
  const [localIssuePage, setLocalIssuePage] = useState(1)
  const selected = viewState ? viewState.page ?? defaultPage : localSelected
  const activeIssueId = viewState ? viewState.issue ?? null : localActiveIssueId
  const severityFilter = viewState ? viewState.severity ?? EMPTY_SEVERITIES : localSeverityFilter
  const reviewFilter = viewState ? viewState.review ?? "all" : localReviewFilter
  const issuePage = viewState ? viewState.issuePage ?? 1 : localIssuePage

  const updateViewState = (patch: Partial<PageDetailsViewState>) => {
    onViewStateChange?.({ ...viewState, ...patch })
  }

  const selectPage = (value: number | null) => {
    setLocalSelected(value)
    setLocalActiveIssueId(null)
    updateViewState({ page: value ?? undefined, issue: undefined })
  }

  const highlightIssue = (value: string | null) => {
    setLocalActiveIssueId(value)
    updateViewState({ issue: value ?? undefined })
  }
  const page = report.pages.find((item) => item.page === selected)
  const allIssues = useMemo(() => report.pages.flatMap((item) => item.issues), [report.pages])

  // 问题列表覆盖整份文档；点击行会同步切换双栏页码并高亮目标区域。
  const visibleIssues = useMemo(() => {
    let list = allIssues
    if (severityFilter.length) {
      list = list.filter((issue) => severityFilter.includes(issue.severity))
    }
    if (reviewFilter === "pending") {
      list = list.filter((issue) => !decisions[issue.id])
    } else if (reviewFilter === "done") {
      list = list.filter((issue) => decisions[issue.id])
    }
    return list
  }, [allIssues, severityFilter, reviewFilter, decisions])
  const pageVisibleIssues = visibleIssues.filter((issue) => issue.page === selected)

  return (
    <section className="page-review">
      <div className="report-section-heading report-section-heading--compare">
        <Space wrap size={10}>
          <Typography.Title level={5}>双语对照</Typography.Title>
          <Tag variant="filled" className="report-count-tag">{report.summary.pages} 页</Tag>
          {taskId && <span className="page-review__state"><i />复核任务已开启</span>}
        </Space>
        <Select
          aria-label="选择对照页码"
          className="page-review__page-select"
          value={selected}
          onChange={(value) => {
            selectPage(value)
          }}
          options={report.pages.map((item) => ({
            value: item.page,
            label: `第 ${item.page} 页 · ${INTEGER_FORMATTER.format(item.score)} 分 · ${
              STATUS_META[item.status]?.label ?? item.status
            }${item.issues.length ? ` · ${item.issues.length} 个问题` : ""}`,
          }))}
          showSearch
          optionFilterProp="label"
        />
      </div>
      {page ? (
        <div className="page-review__compare-body">
          {/* key 按页重挂载：换页时清掉上一页的尺寸状态，避免红框按旧尺寸错位闪现。 */}
          <PageCompare
            key={page.page}
            page={page.page}
            issues={pageVisibleIssues}
            rendered={rendered}
            activeIssueId={activeIssueId}
          />
        </div>
      ) : (
        <Empty
          description="选择页面查看详情。"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      )}

      <div className="issue-list-heading">
        <Space wrap size={10}>
          <Typography.Title level={5}>问题列表</Typography.Title>
          <Tag variant="filled" className="issue-list-count">{allIssues.length}</Tag>
        </Space>
        <Space wrap size={8}>
          <Select
            aria-label="按严重度筛选问题"
            mode="multiple"
            allowClear
            placeholder="按严重度筛选…"
            className="issue-list-filter"
            value={severityFilter}
            onChange={(value) => {
              setLocalSeverityFilter(value)
              setLocalIssuePage(1)
              updateViewState({ severity: value.length ? value : undefined, issuePage: undefined })
            }}
            options={Object.entries(SEVERITY_META).map(([key, meta]) => ({
              value: key,
              label: meta.label,
            }))}
          />
          <Segmented
            aria-label="按复核状态筛选问题"
            value={reviewFilter}
            onChange={(value) => {
              const next = value as ReviewFilter
              setLocalReviewFilter(next)
              setLocalIssuePage(1)
              updateViewState({ review: next === "all" ? undefined : next, issuePage: undefined })
            }}
            options={[
              { value: "all", label: `全部 ${allIssues.length}` },
              {
                value: "pending",
                label: `待处理 ${allIssues.filter((issue) => !decisions[issue.id]).length}`,
              },
              {
                value: "done",
                label: `已复核 ${allIssues.filter((issue) => decisions[issue.id]).length}`,
              },
            ]}
          />
        </Space>
      </div>

      <Table<Issue>
        className="issue-table"
        rowKey="id"
        size="middle"
        dataSource={visibleIssues}
        pagination={{
          current: issuePage,
          pageSize: 8,
          hideOnSinglePage: true,
          showSizeChanger: false,
          onChange: (value) => {
            setLocalIssuePage(value)
            updateViewState({ issuePage: value === 1 ? undefined : value })
          },
        }}
        locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前筛选条件下没有问题" /> }}
        columns={[
          {
            title: "级别",
            dataIndex: "severity",
            width: 104,
            render: (severity: string) => (
              <Tag
                variant="filled"
                style={{
                  color: SEVERITY_META[severity]?.color,
                  background: SEVERITY_META[severity]?.background,
                }}
              >
                <i className="issue-severity-dot" style={{ background: SEVERITY_META[severity]?.color }} />
                {SEVERITY_META[severity]?.label ?? severity}
              </Tag>
            ),
          },
          {
            title: "问题类型",
            dataIndex: "type",
            width: 138,
            render: (type: string, issue) => (
              <Tag
                variant="filled"
                style={{
                  color: SEVERITY_META[issue.severity]?.color,
                  background: SEVERITY_META[issue.severity]?.background,
                }}
              >
                {ISSUE_TYPE_META[type] ?? type}
              </Tag>
            ),
          },
          {
            title: "位置",
            dataIndex: "page",
            width: 118,
            render: (issuePage: number, issue) =>
              `第 ${issuePage} 页${issue.bbox ? " · 已定位" : " · 页级"}`,
          },
          {
            title: "问题描述",
            dataIndex: "description",
            ellipsis: true,
          },
          {
            title: "状态",
            width: 104,
            render: (_, issue) => {
              const decision = decisions[issue.id]
              return decision ? (
                <Tag
                  variant="filled"
                  style={{
                    color: DECISION_META[decision].color,
                    background: DECISION_META[decision].background,
                  }}
                >
                  {DECISION_META[decision].label}
                </Tag>
              ) : (
                <Tag variant="filled" className="issue-pending-tag">待处理</Tag>
              )
            },
          },
        ]}
        expandable={{
          expandedRowKeys: activeIssueId ? [activeIssueId] : [],
          onExpand: (expanded, issue) => {
            setLocalSelected(issue.page)
            setLocalActiveIssueId(expanded ? issue.id : null)
            updateViewState({ page: issue.page, issue: expanded ? issue.id : undefined })
          },
          expandedRowRender: (issue) => (
            <IssueDetails
              issue={issue}
              decisions={decisions}
              onDecide={onDecide}
              onHighlight={(issueId) => highlightIssue(issueId)}
            />
          ),
        }}
        onRow={(issue) => ({
          className: issue.id === activeIssueId ? "issue-table__row--active" : "",
          tabIndex: 0,
          "aria-label": `查看第 ${issue.page} 页问题：${issue.description}`,
          onClick: () => {
            setLocalSelected(issue.page)
            setLocalActiveIssueId(issue.id)
            updateViewState({ page: issue.page, issue: issue.id })
          },
          onKeyDown: (event) => {
            if (event.key !== "Enter" && event.key !== " ") return
            event.preventDefault()
            setLocalSelected(issue.page)
            setLocalActiveIssueId(issue.id)
            updateViewState({ page: issue.page, issue: issue.id })
          },
        })}
      />
    </section>
  )
}
