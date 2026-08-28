/** 规则管理页：antd Table + 编辑抽屉内嵌表单 + 误报归因统计（T21 P0）。 */

import { useCallback, useEffect, useRef, useState } from "react"
import { Alert, Button, Modal, message, Popconfirm, Space, Spin, Tag, Typography } from "antd"
import type { ColumnsType } from "antd/es/table"
import type {
  AIRepairReport,
  IssueTypeInsight,
  RepairCluster,
  ReviewInsight,
  RuleProfile,
  TuningAdvice,
} from "../api"
import { api } from "../services/queryClient"
import { ProfileEditor } from "./ProfileEditor"
import { ISSUE_TYPE_META, PALETTE, SEVERITY_META } from "../uiTokens"
import { DataTable, FormDrawer, PageHeader, PageSection } from "../components/ui"

interface ProfileListItem {
  filename: string
  profile_id: string
  name: string
  version: number
  status: "draft" | "published" | "archived"
  reference: string
}

interface EditingProfile {
  profile: RuleProfile
  title: string
  description: string
}

const STATUS_COLOR: Record<string, { color: string; background: string; label: string }> = {
  published: { color: PALETTE.success, background: PALETTE.successSoft, label: "已发布" },
  draft: { color: PALETTE.warning, background: PALETTE.warningSoft, label: "草稿" },
  archived: { color: PALETTE.textSecondary, background: PALETTE.canvas, label: "已归档" },
}

// 百分比统一走 Intl 百分位格式，避免手写乘法在四舍五入上的口径漂移。
const PERCENT_FORMATTER = new Intl.NumberFormat("zh-CN", {
  style: "percent",
  maximumFractionDigits: 0,
})

const REPAIR_STAGE_LABELS: Record<RepairCluster["suspected_stage"], string> = {
  parse: "解析",
  group: "分组",
  alignment: "页面对齐",
  match: "区域匹配",
  detect: "规则检测",
  report: "报告输出",
}

/** 下载只在用户点击后发生，临时 URL 使用后立即释放。 */
function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

/** 生成未被现有规则家族占用的稳定标识。 */
function uniqueProfileId(profiles: ProfileListItem[], preferred: string) {
  const used = new Set(profiles.map((item) => item.profile_id))
  if (!used.has(preferred)) return preferred
  let suffix = 2
  while (used.has(`${preferred}-${suffix}`)) suffix += 1
  return `${preferred}-${suffix}`
}

/** 新建、派生和版本升级共用的加载器封装。 */
function useProfileLoader(profiles: ProfileListItem[]) {
  const [editing, setEditing] = useState<EditingProfile | null>(null)
  const startNew = () =>
    api
      .defaultProfile()
      .then((profile) =>
        setEditing({
          title: "新建规则",
          description: "从内置平衡配置开始创建草稿。",
          profile: {
            ...profile,
            profile_id: uniqueProfileId(profiles, "custom-rules"),
            name: "自定义规则",
            version: 1,
            status: "draft",
            description: "",
          },
        }),
      )
      .catch(() => message.error("无法加载默认配置"))
  const startEdit = (record: ProfileListItem) =>
    api
      .profileItem(record.filename)
      .then((profile) => {
        if (record.status === "draft") {
          setEditing({
            profile,
            title: "编辑规则",
            description: `正在编辑草稿 ${record.reference}。`,
          })
          return
        }
        const nextVersion = Math.max(
          ...profiles
            .filter((item) => item.profile_id === record.profile_id)
            .map((item) => item.version),
        ) + 1
        setEditing({
          title: "新建规则版本",
          description: `基于 ${record.reference} 创建不可冲突的新版本。`,
          profile: { ...profile, version: nextVersion, status: "draft" },
        })
      })
      .catch(() => message.error("读取失败"))
  const startFork = (filename: string) =>
    api
      .profileItem(filename)
      .then((profile) =>
        setEditing({
          title: "复制规则",
          description: `基于 ${profile.profile_id}@${profile.version} 创建独立规则。`,
          profile: {
            ...profile,
            profile_id: uniqueProfileId(profiles, `${profile.profile_id}-copy`),
            name: `${profile.name}（副本）`,
            version: 1,
            status: "draft",
          },
        }),
      )
      .catch(() => message.error("读取失败"))
  return { editing, setEditing, startNew, startEdit, startFork }
}

/** 误报率到展示色的映射：高误报率提示"优先复核该类规则"。 */
function fpRateTone(rate: number): { color: string; background: string } {
  if (rate >= 0.5) return { color: PALETTE.critical, background: PALETTE.criticalSoft }
  if (rate >= 0.25) return { color: PALETTE.warning, background: PALETTE.warningSoft }
  return { color: PALETTE.success, background: PALETTE.successSoft }
}

/** 误报热区表格列定义：静态配置提为模块常量，避免每次渲染重建。 */
const insightColumns: ColumnsType<IssueTypeInsight> = [
  {
    title: "问题类型",
    dataIndex: "issue_type",
    render: (value: string) => ISSUE_TYPE_META[value] ?? value,
  },
  {
    title: "检测器",
    dataIndex: "detector",
    render: (value: string) => <span className="qa-code-value">{value || "-"}</span>,
  },
  {
    title: "严重度",
    dataIndex: "severity",
    width: 100,
    render: (value: string) => SEVERITY_META[value]?.label ?? value,
  },
  {
    title: "分布",
    dataIndex: "reviewed",
    width: 150,
    render: (_, record) => (
      <DistributionBar confirmed={record.confirmed} fp={record.false_positive} ignored={record.ignored} />
    ),
  },
  { title: "确认", dataIndex: "confirmed", width: 70 },
  { title: "误报", dataIndex: "false_positive", width: 70 },
  { title: "忽略", dataIndex: "ignored", width: 70 },
  {
    title: "误报率",
    dataIndex: "fp_rate",
    width: 110,
    render: (value: number) => {
      const tone = fpRateTone(value)
      return (
        <Tag
          variant="filled"
          style={{ color: tone.color, background: tone.background, margin: 0 }}
        >
          {PERCENT_FORMATTER.format(value)}
        </Tag>
      )
    },
  },
]

const repairColumns: ColumnsType<RepairCluster> = [
  {
    title: "误报模式",
    dataIndex: "issue_type",
    width: 150,
    render: (value: string) => ISSUE_TYPE_META[value] ?? value,
  },
  {
    title: "检测器",
    dataIndex: "detector",
    width: 140,
    render: (value: string) => <span className="qa-code-value">{value}</span>,
  },
  {
    title: "对照证据",
    width: 150,
    render: (_, record) => `误报 ${record.false_positive_count} · 确认 ${record.confirmed_count}`,
  },
  {
    title: "疑似阶段",
    dataIndex: "suspected_stage",
    width: 120,
    render: (value: RepairCluster["suspected_stage"]) => REPAIR_STAGE_LABELS[value],
  },
  {
    title: "代码检索起点",
    dataIndex: "suspected_code_locations",
    width: 300,
    ellipsis: { showTitle: false },
    render: (locations: string[]) => (
      <span className="qa-code-value rules-repair__code-location" title={locations.join("\n")}>
        {locations[0] ?? "待定位"}
      </span>
    ),
  },
]

/** 异步加载占位：role=status 让读屏软件可感知加载过程。 */
function LoadingStatus({ label }: { label: string }) {
  return (
    <div className="rules-loop__loading rules-loop__state" role="status" aria-live="polite">
      <Spin size="small" />
      <Typography.Text type="secondary">{label}</Typography.Text>
    </div>
  )
}

/** 复核结论分布条：一段式堆叠条，颜色仅承载业务语义（确认=信息 / 误报=严重 / 忽略=弱提示）。 */
function DistributionBar({ confirmed, fp, ignored }: { confirmed: number; fp: number; ignored: number }) {
  const total = confirmed + fp + ignored
  const label = `确认 ${confirmed}，误报 ${fp}，忽略 ${ignored}`
  if (!total) return <span className="rules-loop__bar-empty">—</span>
  const segments = [
    { key: "确认", value: confirmed, tone: "rules-loop__bar-seg--confirmed" },
    { key: "误报", value: fp, tone: "rules-loop__bar-seg--fp" },
    { key: "忽略", value: ignored, tone: "rules-loop__bar-seg--ignored" },
  ].filter((segment) => segment.value > 0)
  return (
    <span
      className="rules-loop__bar"
      role="img"
      aria-label={label}
      title={label}
    >
      {segments.map((segment) => (
        <span
          key={segment.key}
          className={`rules-loop__bar-seg ${segment.tone}`}
          style={{ flexGrow: segment.value }}
        />
      ))}
    </span>
  )
}

/** 误报归因统计区块：关键计数条 + 按类型的分布与误报热区排序。 */
function ReviewInsightSection() {
  const [insight, setInsight] = useState<ReviewInsight | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    api
      .reviewInsight()
      .then((data) => {
        if (!cancelled) setInsight(data)
      })
      .catch((exc) => {
        if (!cancelled) setError(exc instanceof Error ? exc.message : String(exc))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [reloadKey])

  const reviewed = insight ? insight.confirmed + insight.false_positive + insight.ignored : 0
  const hasData = Boolean(insight?.by_type.length)

  return (
    <PageSection
      className="management-page__section rules-loop-section"
      title="误报归因统计"
      description="复核结论按问题类型的分布；误报率高的类型是阈值调优的优先候选。"
      extra={
        insight && hasData ? (
          <span className="rules-loop__scope">
            {insight.pair_count} 个文档对 · {reviewed} 条已归因判定
            {insight.unmatched > 0 ? ` · ${insight.unmatched} 条无法归因` : ""}
          </span>
        ) : undefined
      }
    >
      {loading ? <LoadingStatus label="正在加载误报统计…" /> : null}
      {!loading && error ? (
        <div className="rules-loop__state">
          <Alert
            type="warning"
            showIcon
            message="误报统计加载失败"
            description={`${error}。请确认服务状态后重试。`}
            action={(
              <Button size="small" onClick={() => setReloadKey((value) => value + 1)}>
                重试
              </Button>
            )}
          />
        </div>
      ) : null}
      {!loading && !error && insight && hasData ? (
        <>
          <div className="rules-loop__stats">
            <div className="rules-loop__stat">
              <span className="rules-loop__stat-value rules-loop__stat-value--critical">
                {insight.false_positive}
              </span>
              <span className="rules-loop__stat-label">误报</span>
            </div>
            <div className="rules-loop__stat">
              <span className="rules-loop__stat-value rules-loop__stat-value--info">
                {insight.confirmed}
              </span>
              <span className="rules-loop__stat-label">确认</span>
            </div>
            <div className="rules-loop__stat">
              <span className="rules-loop__stat-value">{insight.ignored}</span>
              <span className="rules-loop__stat-label">忽略</span>
            </div>
            <div className="rules-loop__stat">
              <span className="rules-loop__stat-value rules-loop__stat-value--warning">
                {insight.unmatched}
              </span>
              <span className="rules-loop__stat-label">无法归因</span>
            </div>
          </div>
          <DataTable
            rowKey="issue_type"
            columns={insightColumns}
            dataSource={insight.by_type}
            pagination={false}
          />
          {insight.unmatched ? (
            <div className="rules-loop__notes">
              <p className="rules-loop__note">
                无法归因的 {insight.unmatched} 条判定来自报告重跑前的旧 Issue 编号，不参与误报率计算。
              </p>
            </div>
          ) : null}
        </>
      ) : null}
      {!loading && !error && !hasData ? (
        <div className="rules-loop__state">
          <Typography.Text type="secondary">
            还没有复核判定数据；在工作台对问题做出“误报 / 确认”标记后，这里会汇总出误报热区。
          </Typography.Text>
        </div>
      ) : null}
    </PageSection>
  )
}

/** AI 修复报告区块：呈现误报诊断任务摘要，并导出供代码修复代理读取的 Markdown。 */
function AIRepairReportSection() {
  const [report, setReport] = useState<AIRepairReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const [exporting, setExporting] = useState(false)
  const [selectedClusterIds, setSelectedClusterIds] = useState<string[]>([])
  const [messageApi, contextHolder] = message.useMessage()

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    api
      .aiRepairReport()
      .then((data) => {
        if (!cancelled) {
          setReport(data)
          setSelectedClusterIds([])
        }
      })
      .catch((exc) => {
        if (!cancelled) setError(exc instanceof Error ? exc.message : String(exc))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [reloadKey])

  const exportReport = async () => {
    if (!selectedClusterIds.length) return
    setExporting(true)
    try {
      const blob = await api.downloadAIRepairReport(selectedClusterIds)
      downloadBlob(blob, "ai-repair-report.md")
      messageApi.success("AI 修复报告已导出")
    } catch (exc) {
      messageApi.error(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setExporting(false)
    }
  }

  const hasClusters = Boolean(report?.clusters.length)

  return (
    <PageSection
      className="management-page__section rules-loop-section"
      title="AI 修复报告"
      description="勾选需要排查的误报模式，导出包含代表案例、疑似阶段、代码检索起点与回归要求的任务书。"
      extra={hasClusters ? (
        <Button
          type="primary"
          disabled={!selectedClusterIds.length}
          loading={exporting}
          onClick={() => void exportReport()}
        >
          导出已选（{selectedClusterIds.length}）
        </Button>
      ) : undefined}
    >
      {contextHolder}
      {loading ? <LoadingStatus label="正在生成误报诊断…" /> : null}
      {!loading && error ? (
        <div className="rules-loop__state">
          <Alert
            type="warning"
            showIcon
            message="AI 修复报告生成失败"
            description={`${error}。请确认服务状态后重试。`}
            action={(
              <Button size="small" onClick={() => setReloadKey((value) => value + 1)}>
                重试
              </Button>
            )}
          />
        </div>
      ) : null}
      {!loading && !error && report && hasClusters ? (
        <>
          <div className="rules-loop__stats">
            <div className="rules-loop__stat">
              <span className="rules-loop__stat-value">{report.clusters.length}</span>
              <span className="rules-loop__stat-label">误报模式</span>
            </div>
            <div className="rules-loop__stat">
              <span className="rules-loop__stat-value rules-loop__stat-value--critical">
                {report.false_positive}
              </span>
              <span className="rules-loop__stat-label">误报判定</span>
            </div>
            <div className="rules-loop__stat">
              <span className="rules-loop__stat-value rules-loop__stat-value--info">
                {report.confirmed}
              </span>
              <span className="rules-loop__stat-label">确认对照</span>
            </div>
            <div className="rules-loop__stat">
              <span className="rules-loop__stat-value rules-loop__stat-value--warning">
                {report.unmatched}
              </span>
              <span className="rules-loop__stat-label">无法归因</span>
            </div>
          </div>
          <DataTable
            rowKey="cluster_id"
            columns={repairColumns}
            dataSource={report.clusters}
            pagination={false}
            rowSelection={{
              selectedRowKeys: selectedClusterIds,
              onChange: (keys) => setSelectedClusterIds(keys.map(String)),
              getCheckboxProps: (record) => ({
                "aria-label": `选择${ISSUE_TYPE_META[record.issue_type] ?? record.issue_type}`,
              }),
            }}
          />
          <div className="rules-loop__notes">
            <p className="rules-loop__note">
              报告中的疑似阶段和代码位置仅用于导航，根因统一标记为待验证；AI 必须先复现，再决定修代码或调整规则。
            </p>
          </div>
        </>
      ) : null}
      {!loading && !error && report && !hasClusters ? (
        <div className="rules-loop__state">
          <Typography.Text type="secondary">
            当前没有可归因的误报；完成误报复核后，系统会生成代码审查任务书。
          </Typography.Text>
        </div>
      ) : null}
    </PageSection>
  )
}

/** 规则调优区块：保留阈值/严重度建议与 DRAFT 草案，作为代码诊断后的可选分支。 */
function TuningAdviceSection({ onApplied }: { onApplied: () => void }) {
  const [advice, setAdvice] = useState<TuningAdvice | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [applying, setApplying] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)
  const [appliedReference, setAppliedReference] = useState<string | null>(null)
  const [messageApi, contextHolder] = message.useMessage()

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    setAppliedReference(null)
    api
      .tuningSuggestions()
      .then((data) => {
        if (!cancelled) setAdvice(data)
      })
      .catch((exc) => {
        if (!cancelled) setError(exc instanceof Error ? exc.message : String(exc))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [reloadKey])

  const applyDraft = async () => {
    if (!advice?.proposed_profile) return
    setApplying(true)
    try {
      const saved = await api.saveProfile(advice.proposed_profile)
      setAppliedReference(saved.reference)
      messageApi.success(`已保存草案 ${saved.reference}；发布前请先完成 Golden 回归`)
      onApplied()
    } catch (exc) {
      messageApi.error(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setApplying(false)
    }
  }

  const hasSuggestions = Boolean(advice?.suggestions.length)

  return (
    <PageSection
      className="management-page__section rules-loop-section rules-advice-section"
      title="规则调优"
      description="仅在确认检测逻辑正确后使用；基于复核样本生成规则草案，保存后不会自动生效。"
      extra={
        appliedReference ? (
          <Tag color={PALETTE.successSoft} style={{ color: PALETTE.successText, marginInlineEnd: 0 }}>
            已保存草稿 {appliedReference}
          </Tag>
        ) : hasSuggestions && advice?.proposed_profile ? (
          <Button loading={applying} onClick={() => void applyDraft()}>
            保存为草稿（v{advice.proposed_profile.version}）
          </Button>
        ) : undefined
      }
    >
      {contextHolder}
      {loading ? <LoadingStatus label="正在加载调优建议…" /> : null}
      {!loading && error ? (
        <div className="rules-loop__state">
          <Alert
            type="warning"
            showIcon
            message="调优建议加载失败"
            description={`${error}。请确认服务状态后重试。`}
            action={(
              <Button size="small" onClick={() => setReloadKey((value) => value + 1)}>
                重试
              </Button>
            )}
          />
        </div>
      ) : null}
      {!loading && !error && advice && hasSuggestions ? (
        <>
          <div className="rules-loop__basis">
            <span className="rules-loop__basis-label">调优基准</span>
            <code className="rules-loop__basis-ref">{advice.base_reference}</code>
            <span className="rules-loop__basis-tag">
              {advice.profile_basis === "stored" ? "已保存版本" : "内置配置"}
            </span>
            <span className="rules-loop__basis-meta">
              样本 {advice.sample_count} 条
              {advice.unmatched ? ` · ${advice.unmatched} 条无法归因` : ""}
            </span>
          </div>
          <div className="rules-suggestion-list">
            {advice.suggestions.map((item) => {
              const titleId = `rules-suggestion-${item.field.replace(/[^a-zA-Z0-9_-]/g, "-")}`
              return (
                <article
                  key={item.field}
                  aria-labelledby={titleId}
                  className={`rules-suggestion rules-suggestion--${
                    item.kind === "threshold" ? "threshold" : "severity"
                  }`}
                >
                  <header className="rules-suggestion__head">
                    <span
                      className={`rules-suggestion__kind rules-suggestion__kind--${item.kind}`}
                    >
                      {item.kind === "threshold" ? "阈值调整" : "严重度降级"}
                    </span>
                    <h3 id={titleId} className="rules-suggestion__type">
                      {ISSUE_TYPE_META[item.issue_type] ?? item.issue_type}
                    </h3>
                    <span className="rules-suggestion__evidence">
                      误报 {item.fp_samples} · 确认 {item.confirmed_samples}
                    </span>
                  </header>
                  <div className="rules-suggestion__change">
                    <code className="rules-suggestion__field">{item.field}</code>
                    <span className="rules-suggestion__values">
                      <span className="rules-suggestion__value">{String(item.current_value)}</span>
                      <span className="rules-suggestion__arrow" aria-hidden="true">
                        →
                      </span>
                      <span className="rules-suggestion__value rules-suggestion__value--target">
                        {String(item.proposed_value)}
                      </span>
                    </span>
                  </div>
                  <p className="rules-suggestion__rationale">{item.rationale}</p>
                </article>
              )
            })}
          </div>
          {advice.notes.length ? (
            <div className="rules-loop__notes">
              {advice.notes.map((note) => (
                <p key={note} className="rules-loop__note">
                  {note}
                </p>
              ))}
            </div>
          ) : null}
        </>
      ) : null}
      {!loading && !error && advice && !hasSuggestions ? (
        <div className="rules-loop__state">
          <Typography.Text type="secondary">
            复核样本还不足以生成有依据的建议（同类误报至少 2 条，或误报率 ≥70% 且判定数 ≥3）。
            继续积累复核结论后，这里会给出阈值/严重度调整草案。
          </Typography.Text>
        </div>
      ) : null}
    </PageSection>
  )
}

export function ProfileManager() {
  const [profiles, setProfiles] = useState<ProfileListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [messageApi, contextHolder] = message.useMessage()
  // 编辑器脏标记：Form onChange 置位，打开/保存后复位；关闭前据此拦截。
  const editorDirtyRef = useRef(false)
  const { editing, setEditing, startNew, startEdit, startFork } = useProfileLoader(profiles)

  useEffect(() => {
    if (editing) editorDirtyRef.current = false
  }, [editing])

  const closeEditor = () => {
    if (!editorDirtyRef.current) {
      setEditing(null)
      return
    }
    // 有未保存改动时先确认，避免误触 mask/ESC 丢失整版配置。
    Modal.confirm({
      title: "放弃未保存的修改？",
      content: "抽屉中的改动尚未保存，关闭后将全部丢失。",
      okText: "放弃修改",
      okButtonProps: { danger: true },
      cancelText: "继续编辑",
      onOk: () => setEditing(null),
    })
  }

  const refresh = useCallback(() => {
    setLoading(true)
    api
      .profileList()
      .then(setProfiles)
      .catch((exc) =>
        messageApi.error(exc instanceof Error ? exc.message : String(exc)),
      )
      .finally(() => setLoading(false))
  }, [messageApi])

  useEffect(refresh, [refresh])

  const archive = async (filename: string, reference: string) => {
    try {
      await api.profileDelete(filename)
      messageApi.success(`已归档 ${reference}`)
      refresh()
    } catch (exc) {
      messageApi.error(exc instanceof Error ? exc.message : String(exc))
    }
  }

  const publish = async (filename: string, reference: string) => {
    try {
      await api.profilePublish(filename)
      messageApi.success(`已发布 ${reference}`)
      refresh()
    } catch (exc) {
      messageApi.error(exc instanceof Error ? exc.message : String(exc))
    }
  }

  const columns: ColumnsType<ProfileListItem> = [
    { title: "名称", dataIndex: "name", ellipsis: { showTitle: true } },
    {
      title: "标识",
      dataIndex: "profile_id",
      render: (value: string) => (
        <Tag className="qa-code-value" title={value}>{value}</Tag>
      ),
    },
    { title: "版本", dataIndex: "version", width: 70, render: (v: number) => `v${v}` },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (value: string) => {
        const meta = STATUS_COLOR[value]
        return (
          <Tag
            style={{
              color: meta?.color ?? PALETTE.textSecondary,
              background: meta?.background ?? PALETTE.canvas,
              borderColor: meta?.background ?? PALETTE.border,
            }}
          >
            {meta?.label ?? value}
          </Tag>
        )
      },
    },
    {
      title: "引用",
      dataIndex: "reference",
      render: (value: string) => (
        <span className="qa-code-value" title={value}>{value}</span>
      ),
    },
    {
      title: "操作",
      width: 240,
      render: (_, record) => (
        <Space className="rules-table__actions" size={8}>
          <Button type="link" size="small" onClick={() => void startEdit(record)}>
            {record.status === "draft" ? "编辑" : "新建版本"}
          </Button>
          {record.status === "draft" ? (
            <Button type="link" size="small" onClick={() => void publish(record.filename, record.reference)}>
              发布
            </Button>
          ) : (
            <Button type="link" size="small" onClick={() => void startFork(record.filename)}>
              复制派生
            </Button>
          )}
          <Popconfirm
            title={`确定归档 ${record.reference}？`}
            description="归档后不再用于新质检，历史记录仍可复现。"
            okText="归档"
            okButtonProps={{ danger: true }}
            onConfirm={() => void archive(record.filename, record.reference)}
          >
            <Button type="link" size="small" danger>
              归档
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="qa-page management-page">
      {contextHolder}
      <PageHeader
        title="规则管理"
        meta={`· ${profiles.length} 个配置`}
        description="配置检测规则与阈值；草稿发布后不可覆盖，调整时创建新版本。"
        extra={
          <Button type="primary" onClick={startNew}>
            新建配置
          </Button>
        }
      />
      <PageSection className="management-page__section">
        <DataTable
          rowKey="filename"
          loading={loading}
          columns={columns}
          dataSource={profiles}
          pagination={false}
          emptyTitle="尚未保存规则配置"
          emptyDescription="新建配置可从内置平衡配置起步。"
        />
      </PageSection>
      <ReviewInsightSection />
      <AIRepairReportSection />
      <TuningAdviceSection onApplied={refresh} />
      <FormDrawer
        open={Boolean(editing)}
        title={editing?.title ?? "规则配置"}
        description={editing?.description}
        size={720}
        destroyOnHidden
        onClose={closeEditor}
      >
        {editing ? (
          <ProfileEditor
            initial={editing.profile}
            onDirtyChange={(dirty) => {
              editorDirtyRef.current = dirty
            }}
            onSaved={(reference) => {
              messageApi.success(`已保存 ${reference}`)
              editorDirtyRef.current = false
              setEditing(null)
              refresh()
            }}
          />
        ) : null}
      </FormDrawer>
    </div>
  )
}
