/** 质检记录页：antd Table + 详情抽屉，行内即看摘要，抽屉看完整详情。 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import type { Key } from "react"
import { DeleteOutlined, ReloadOutlined, SearchOutlined } from "@ant-design/icons"
import { Alert, Button, message, Modal, Popconfirm, Select, Space, Tooltip, Typography, Input } from "antd"
import type { ColumnsType } from "antd/es/table"
import type { TableRowSelection } from "antd/es/table/interface"
import type { HistoryRecord, TaskSummary } from "../api"
import { api } from "../services/queryClient"
import { ActiveTasksPanel } from "./ActiveTasksPanel"
import { HistoryDetail } from "./HistoryDetail"
import { PALETTE, scoreColor } from "../uiTokens"
import { DataTable, PageHeader, PageSection, StatusTag } from "../components/ui"

// 固定列合计约 980 px，源/目标文档两列合计保留约 380 px（各约 190 px），
// 保证完整文件名可直接读出；悬停还有 Tooltip 兜底。容器达到该宽度时
// 不应再被人为强制出横向滚动条。
const HISTORY_TABLE_MIN_WIDTH = 1360

/** 本地时间格式化：created_at 为 UTC ISO 串，直接截串会差时区。 */
function formatTime(iso: string): string {
  const date = new Date(iso)
  return Number.isNaN(date.getTime())
    ? iso
    : date.toLocaleString("zh-CN", { hour12: false })
}

/** 重新质检弹窗：选择执行配置（沿用当前或换其他配置）。
 *
 * profile 为 null 表示沿用工作台当前配置；选择具体配置文件则覆盖。
 * 密码不落历史记录：受打开密码保护的文档重比时需在此重新输入。
 */
function RerunModal({
  record,
  open,
  confirming,
  onConfirm,
  onClose,
}: {
  record: HistoryRecord | null
  open: boolean
  /** 确认中需要拉取完整记录取路径：按钮进入 loading，防止误以为卡死重复点击。 */
  confirming: boolean
  onConfirm: (profile: string | null, passwords: { source: string; target: string }) => void
  onClose: () => void
}) {
  const [profile, setProfile] = useState<string | null>(null)
  const [sourcePassword, setSourcePassword] = useState("")
  const [targetPassword, setTargetPassword] = useState("")
  const [profiles, setProfiles] = useState<
    { filename: string; name: string; version: number; reference: string; status: string }[]
  >([])

  useEffect(() => {
    if (open) {
      setProfile(null)
      setSourcePassword("")
      setTargetPassword("")
      api
        .profileList()
        .then((items) => setProfiles(items.filter((item) => item.status === "published")))
        .catch(() => undefined)
    }
  }, [open])

  return (
    <Modal
      open={open}
      title="重新质检"
      okText="开始质检"
      cancelText="取消"
      confirmLoading={confirming}
      okButtonProps={{ disabled: confirming }}
      onOk={() =>
        onConfirm(profile, { source: sourcePassword, target: targetPassword })
      }
      onCancel={onClose}
      destroyOnHidden
    >
      <Typography.Paragraph className="history-rerun-modal__lead">
        将重新质检 <strong>{record?.source_display}</strong> →{" "}
        <strong>{record?.target_display}</strong>
        （原记录使用配置 {record?.rule_profile_reference || "内置默认"}）。
      </Typography.Paragraph>
      <Select
        style={{ width: "100%" }}
        value={profile}
        onChange={setProfile}
        placeholder="沿用工作台当前配置"
        allowClear
        options={profiles.map((item) => ({
          value: item.filename,
          label: `${item.name} v${item.version}${item.reference === record?.rule_profile_reference ? "（该记录原配置）" : ""}`,
        }))}
      />
      <Typography.Text type="secondary" className="history-rerun-modal__help">
        不选择则使用工作台当前配置（含规则配置与术语库）；清除输入框可恢复默认。
      </Typography.Text>
      <Typography.Paragraph className="history-rerun-modal__password-label">
        若文档受打开密码保护，请重新输入密码（密码不保存）：
      </Typography.Paragraph>
      <Space orientation="vertical" size={8} style={{ width: "100%" }}>
        <Input.Password
          placeholder="源文档打开密码（无加密留空）"
          value={sourcePassword}
          onChange={(e) => setSourcePassword(e.target.value)}
          autoComplete="new-password"
        />
        <Input.Password
          placeholder="目标文档打开密码（无加密留空）"
          value={targetPassword}
          onChange={(e) => setTargetPassword(e.target.value)}
          autoComplete="new-password"
        />
      </Space>
    </Modal>
  )
}

export function HistoryView({
  refreshToken,
  busy = false,
  progressText = "",
  onReopen,
  onRerun,
  onStart,
}: {
  /** 每次比较成功落盘后变化，驱动列表重新读取服务端记录。 */
  refreshToken: number
  /** 是否有质检任务在后台执行：历史页显示执行中横幅，避免误以为无响应。 */
  busy?: boolean
  /** 后台任务的实时进度文案（排队/处理中/渲染中）。 */
  progressText?: string
  onReopen: (record: HistoryRecord) => void
  /** 重新执行质检：profile 为 null 沿用工作台当前配置；密码不落历史需重输。 */
  onRerun: (
    record: HistoryRecord,
    profile: string | null,
    passwords: { source: string; target: string },
  ) => void
  /** 初始空状态返回工作台创建第一条质检记录。 */
  onStart: () => void
}) {
  const [records, setRecords] = useState<Omit<HistoryRecord, "report">[]>([])
  const [loading, setLoading] = useState(true)
  const [detailRecord, setDetailRecord] = useState<
    Omit<HistoryRecord, "report"> | null
  >(null)
  // 重新质检目标：先存摘要行，确认时再拉完整记录取路径。
  const [rerunRecord, setRerunRecord] = useState<Omit<HistoryRecord, "report"> | null>(null)
  const [rerunSubmitting, setRerunSubmitting] = useState(false)
  const [query, setQuery] = useState("")
  const [statusFilter, setStatusFilter] = useState("all")
  // 批量删除的选中行（跨分页保持）；值即 record_id。
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([])
  const [deleting, setDeleting] = useState(false)
  const tableContainerRef = useRef<HTMLDivElement>(null)
  const [tableViewportWidth, setTableViewportWidth] = useState<number | null>(null)
  const [messageApi, contextHolder] = message.useMessage()

  useEffect(() => {
    const container = tableContainerRef.current
    if (!container) return

    // 固定列只服务真实溢出场景；宽屏继续 sticky 会让 AntD 生成额外滚动占位。
    const syncWidth = () => setTableViewportWidth(container.clientWidth)
    syncWidth()
    const observer = new ResizeObserver(syncWidth)
    observer.observe(container)
    return () => observer.disconnect()
  }, [])

  const shouldFixOperation =
    tableViewportWidth !== null && tableViewportWidth < HISTORY_TABLE_MIN_WIDTH

  /** 服务端记录刷新统一走一个入口，供初始加载、比较完成和手动刷新复用。 */
  const loadRecords = useCallback(() => {
    setLoading(true)
    api
      .historyList()
      .then(setRecords)
      .catch((exc) => {
        const reason = exc instanceof Error ? exc.message : String(exc)
        messageApi.error(`加载质检记录失败：${reason}。请检查服务状态后重试。`)
      })
      .finally(() => setLoading(false))
  }, [messageApi])

  useEffect(() => {
    loadRecords()
  }, [loadRecords, refreshToken])

  // ---- 任务动态（服务端事实来源）：轮询 /api/tasks，展示执行中与最近失败。
  // 大文档（尤其 OCR）可能跑几十分钟，若记录页完全不可见进行中任务，
  // 用户会误以为提交丢失而重复提交（单 worker 串行只会越积越多）。
  const [activeTasks, setActiveTasks] = useState<TaskSummary[]>([])
  const [now, setNow] = useState(() => Date.now())
  const hadActiveRef = useRef(false)

  useEffect(() => {
    let cancelled = false
    const pollTasks = () => {
      api
        .taskList()
        .then((tasks) => {
          if (cancelled) return
          setActiveTasks(tasks)
          const hasActive = tasks.some(
            (task) => task.status === "queued" || task.status === "running",
          )
          // 活跃任务刚清零（完成/失败）：记录列表立即刷新一次，
          // 让新结果即时出现，不必等用户手动刷新。
          if (hadActiveRef.current && !hasActive) loadRecords()
          hadActiveRef.current = hasActive
        })
        .catch(() => {
          // 任务动态是增强信息（旧版服务无该接口时不拖垮记录页），静默降级。
          if (!cancelled) setActiveTasks([])
        })
    }
    pollTasks()
    const timer = window.setInterval(pollTasks, 5000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [loadRecords])

  // 存在活跃任务时每秒走一次时钟，驱动"已 x 分 x 秒"的耗时刷新。
  const hasActiveTask = activeTasks.some(
    (task) => task.status === "queued" || task.status === "running",
  )
  useEffect(() => {
    if (!hasActiveTask) return
    const ticker = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(ticker)
  }, [hasActiveTask])

  // 面板可见项：进行中任务始终展示；失败任务只在最近 24 小时内展示，
  // 避免历史失败长期霸占"任务动态"造成困扰（done 任务直接进记录表）。
  const visibleTasks = useMemo(() => {
    const dayMs = 24 * 60 * 60 * 1000
    return activeTasks.filter((task) => {
      if (task.status === "queued" || task.status === "running") return true
      if (task.status !== "error") return false
      const updated = Date.parse(task.updated_at)
      return !Number.isNaN(updated) && Date.now() - updated < dayMs
    })
  }, [activeTasks])

  const filteredRecords = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase()
    return records.filter((record) => {
      const matchesStatus = statusFilter === "all" || record.status === statusFilter
      const matchesQuery =
        !normalizedQuery ||
        record.source_display.toLocaleLowerCase().includes(normalizedQuery) ||
        record.target_display.toLocaleLowerCase().includes(normalizedQuery)
      return matchesStatus && matchesQuery
    })
  }, [query, records, statusFilter])

  const reopen = async (recordId: string) => {
    try {
      const record = await api.historyItem(recordId)
      if (!record.report) throw new Error("该记录不含完整报告")
      onReopen(record)
    } catch (exc) {
      const reason = exc instanceof Error ? exc.message : String(exc)
      messageApi.error(`打开质检记录失败：${reason}。请刷新列表后重试。`)
    }
  }

  /** 复制完整记录 ID，失败时保留明确反馈，避免省略文本无法手动确认。 */
  const copyRecordId = async (recordId: string) => {
    try {
      if (!navigator.clipboard) throw new Error("浏览器不支持剪贴板 API")
      await navigator.clipboard.writeText(recordId)
      messageApi.success("记录 ID 已复制")
    } catch {
      messageApi.error("复制记录 ID 失败，请检查浏览器剪贴板权限后重试。")
    }
  }

  /** 删除记录（单条/批量同走批量接口）：成功后清空选择并刷新列表。
   *
   * 服务端同步删除记录、完整报告与无共享引用的渲染目录；部分 ID
   * 已不存在时不整体报错，用警告区分回告。
   */
  const deleteRecords = async (recordIds: string[]) => {
    if (recordIds.length === 0 || deleting) return
    setDeleting(true)
    try {
      const result = await api.historyDeleteBatch(recordIds)
      if (result.missing.length > 0) {
        messageApi.warning(
          `已删除 ${result.deleted.length} 条；${result.missing.length} 条记录不存在（可能已被删除或清理）。`,
          6,
        )
      } else {
        messageApi.success(`已删除 ${result.deleted.length} 条质检记录及其衍生渲染文件。`)
      }
      setSelectedRowKeys([])
      // 打开中的详情抽屉若指向被删记录，一并关闭避免展示悬空数据。
      setDetailRecord((current) =>
        current && recordIds.includes(current.record_id) ? null : current,
      )
      loadRecords()
    } catch (exc) {
      const reason = exc instanceof Error ? exc.message : String(exc)
      messageApi.error(`删除质检记录失败：${reason}。请重试。`)
    } finally {
      setDeleting(false)
    }
  }

  /** 确认重新质检：拉取完整记录拿服务器端路径，缺失（如清理后的临时文件）时报错。 */
  const confirmRerun = async (
    profile: string | null,
    passwords: { source: string; target: string },
  ) => {
    if (!rerunRecord) return
    if (busy) {
      // executeCompare 对并发提交是静默忽略的；必须在这里提前拦截，
      // 否则点击"开始质检"后弹窗关闭且毫无反应，与卡死无法区分。
      messageApi.warning("已有质检任务在执行中，请等待完成后再重新质检。")
      return
    }
    setRerunSubmitting(true)
    try {
      const full = await api.historyItem(rerunRecord.record_id)
      if (!full.source_path || !full.target_path) {
        throw new Error("该记录缺少输入文档路径，无法重新质检")
      }
      onRerun(full, profile, passwords)
      // 任务在后台轮询执行；历史页本身不展示进度（顶部横幅除外），
      // 必须显式告知已提交，否则用户以为点击没有生效。
      messageApi.success(
        `已提交重新质检任务（${rerunRecord.source_display} → ${rerunRecord.target_display}），完成后将自动打开报告。`,
        6,
      )
    } catch (exc) {
      const reason = exc instanceof Error ? exc.message : String(exc)
      messageApi.error(`准备重新质检失败：${reason}。请确认原文档仍可用后重试。`)
    } finally {
      setRerunSubmitting(false)
      setRerunRecord(null)
    }
  }

  const columns: ColumnsType<Omit<HistoryRecord, "report">> = [
    {
      title: "ID",
      dataIndex: "record_id",
      width: 160,
      render: (value: string) => (
        <Tooltip title={`${value}（点击复制）`}>
          <button
            type="button"
            className="history-record-id qa-code-value"
            aria-label={`复制记录 ID：${value}`}
            onClick={() => void copyRecordId(value)}
          >
            {value}
          </button>
        </Tooltip>
      ),
    },
    {
      title: "时间",
      dataIndex: "created_at",
      width: 190,
      render: (value: string) => (
        <Tooltip title={value}>
          <Typography.Text className="history-record-time">
            {formatTime(value)}
          </Typography.Text>
        </Tooltip>
      ),
    },
    {
      title: "源文档",
      dataIndex: "source_display",
      width: 190,
      // Tooltip 的触发元素是块级自截断的 span：定位矩形等于单元格可视
      // 宽度；行内长文本会把矩形溢出到单元格外，导致气泡向右偏移。
      ellipsis: { showTitle: false },
      render: (value: string) => (
        <Tooltip title={value}>
          <span className="history-record-doc">{value}</span>
        </Tooltip>
      ),
    },
    {
      title: "目标文档",
      dataIndex: "target_display",
      width: 190,
      ellipsis: { showTitle: false },
      render: (value: string) => (
        <Tooltip title={value}>
          <span className="history-record-doc">{value}</span>
        </Tooltip>
      ),
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 95,
      render: (value: string) => <StatusTag status={value} />,
    },
    {
      title: "分数",
      dataIndex: "document_score",
      width: 80,
      sorter: (a, b) => a.document_score - b.document_score,
      render: (value: number) => (
        <Typography.Text strong style={{ color: scoreColor(value) }}>
          {value.toFixed(1)}
        </Typography.Text>
      ),
    },
    {
      title: "页面",
      dataIndex: "pages",
      width: 70,
      align: "right",
    },
    {
      title: "问题组",
      dataIndex: "problem_total",
      width: 96,
      align: "right",
      // 窄桌面下与操作列一起固定，避免问题数被右侧操作区覆盖。
      fixed: shouldFixOperation ? "right" : undefined,
      // 无问题弱化展示，有问题红字突出，扫一眼即可定位差记录。
      render: (value: number | undefined, record) => {
        const total = value ?? record.issue_total
        return (
          <Tooltip title={`${record.issue_total} 条规则命中`}>
            {total > 0 ? (
              <Typography.Text strong style={{ color: PALETTE.criticalText }}>
                {total}
              </Typography.Text>
            ) : (
              <Typography.Text type="secondary">0</Typography.Text>
            )}
          </Tooltip>
        )
      },
    },
    {
      title: "操作",
      width: 330,
      fixed: shouldFixOperation ? "right" : undefined,
      // 防止 antd Table 单元格内容换行导致行高抖动。
      onCell: () => ({
        className: "history-record-actions",
        style: { whiteSpace: "nowrap" },
      }),
      render: (_, record) => (
        <Space size={4}>
          <Button type="link" size="small" onClick={() => setDetailRecord(record)}>
            查看详情
          </Button>
          <Button type="link" size="small" onClick={() => void reopen(record.record_id)}>
            工作台打开
          </Button>
          <Button type="link" size="small" onClick={() => setRerunRecord(record)}>
            重新质检
          </Button>
          <Popconfirm
            title="删除该质检记录？"
            description="将同时删除完整报告与衍生渲染文件，不可恢复。"
            okText="删除"
            okButtonProps={{ danger: true }}
            cancelText="取消"
            onConfirm={() => void deleteRecords([record.record_id])}
          >
            <Button
              type="link"
              size="small"
              danger
              icon={<DeleteOutlined />}
              aria-label={`删除质检记录：${record.record_id}`}
            >
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const rowSelection: TableRowSelection<Omit<HistoryRecord, "report">> = {
    selectedRowKeys,
    onChange: (keys) => setSelectedRowKeys(keys),
    // 选择列固定在行首，与右侧操作列呼应，批量扫选时不随横向滚动跑位。
    fixed: true,
  }

  return (
    <div className="qa-page history-page">
      {contextHolder}
      <PageHeader
        title="质检记录"
        meta={
          query.trim() || statusFilter !== "all"
            ? `· 显示 ${filteredRecords.length}/${records.length} 条`
            : `· ${records.length} 条记录`
        }
        extra={
          <Button icon={<ReloadOutlined />} loading={loading} onClick={loadRecords}>
            刷新记录
          </Button>
        }
      />
      {busy ? (
        // 后台质检任务的唯一可见信号（本页没有工作台的进度条）：
        // 不展示时用户会以为"重新质检"点击后没有生效。
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message={`质检任务执行中：${progressText || "已提交，等待任务启动"}`}
          description="完成后将自动打开报告；当前列表可继续浏览，无需等待。"
        />
      ) : null}
      <ActiveTasksPanel tasks={visibleTasks} now={now} />
      <PageSection
        className="history-records"
        extra={
          <Space className="history-records__filters" wrap>
            {selectedRowKeys.length > 0 ? (
              <Popconfirm
                title={`删除选中的 ${selectedRowKeys.length} 条质检记录？`}
                description="将同时删除完整报告与衍生渲染文件，不可恢复。"
                okText="删除"
                okButtonProps={{ danger: true }}
                cancelText="取消"
                onConfirm={() => void deleteRecords(selectedRowKeys.map(String))}
              >
                <Button danger icon={<DeleteOutlined />} loading={deleting}>
                  删除所选（{selectedRowKeys.length}）
                </Button>
              </Popconfirm>
            ) : null}
            <Input
              className="qa-table-search"
              allowClear
              prefix={<SearchOutlined />}
              placeholder="搜索源文档或目标文档"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <Select
              aria-label="按质检状态筛选"
              className="history-records__status-filter"
              value={statusFilter}
              onChange={setStatusFilter}
              options={[
                { value: "all", label: "全部状态" },
                { value: "pass", label: "通过" },
                { value: "review", label: "需复核" },
                { value: "fail", label: "未通过" },
              ]}
            />
          </Space>
        }
      >
        <div ref={tableContainerRef}>
          <DataTable
            rowKey="record_id"
            rowSelection={rowSelection}
            loading={loading}
            columns={columns}
            dataSource={filteredRecords}
            scroll={{ x: HISTORY_TABLE_MIN_WIDTH }}
            pagination={{ pageSize: 20 }}
            emptyTitle={records.length === 0 ? "还没有质检记录" : "没有匹配的质检记录"}
            emptyDescription={
              records.length === 0
                ? "完成一次文档质检后，结果会自动保存到这里。"
                : "请调整搜索关键词或状态筛选条件。"
            }
            emptyAction={
              records.length === 0 ? (
                <Button type="link" onClick={onStart}>前往工作台开始质检</Button>
              ) : (
                <Button
                  type="link"
                  onClick={() => {
                    setQuery("")
                    setStatusFilter("all")
                  }}
                >
                  清除筛选
                </Button>
              )
            }
          />
        </div>
      </PageSection>
      <HistoryDetail
        record={detailRecord}
        open={detailRecord !== null}
        onClose={() => setDetailRecord(null)}
      />
      <RerunModal
        record={rerunRecord}
        open={rerunRecord !== null}
        confirming={rerunSubmitting}
        onConfirm={(profile, passwords) => void confirmRerun(profile, passwords)}
        onClose={() => setRerunRecord(null)}
      />
    </div>
  )
}
