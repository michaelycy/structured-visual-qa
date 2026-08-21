/** 质检记录页：antd Table + 详情抽屉，行内即看摘要，抽屉看完整详情。 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { ReloadOutlined, SearchOutlined } from "@ant-design/icons"
import { Button, message, Modal, Select, Space, Tooltip, Typography, Input } from "antd"
import type { ColumnsType } from "antd/es/table"
import type { HistoryRecord } from "../api"
import { api } from "../services/queryClient"
import { HistoryDetail } from "./HistoryDetail"
import { PALETTE, scoreColor } from "../uiTokens"
import { DataTable, PageHeader, PageSection, StatusTag } from "../components/ui"

// 固定列合计约 730 px，给两个可省略的文档列各保留约 95 px；
// 容器达到该宽度时不应再被人为强制出横向滚动条。
const HISTORY_TABLE_MIN_WIDTH = 920

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
  onConfirm,
  onClose,
}: {
  record: HistoryRecord | null
  open: boolean
  onConfirm: (profile: string | null, passwords: { source: string; target: string }) => void
  onClose: () => void
}) {
  const [profile, setProfile] = useState<string | null>(null)
  const [sourcePassword, setSourcePassword] = useState("")
  const [targetPassword, setTargetPassword] = useState("")
  const [profiles, setProfiles] = useState<
    { filename: string; name: string; version: number; reference: string }[]
  >([])

  useEffect(() => {
    if (open) {
      setProfile(null)
      setSourcePassword("")
      setTargetPassword("")
      api.profileList().then(setProfiles).catch(() => undefined)
    }
  }, [open])

  return (
    <Modal
      open={open}
      title="重新质检"
      okText="开始质检"
      cancelText="取消"
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
  onReopen,
  onRerun,
  onStart,
}: {
  /** 每次比较成功落盘后变化，驱动列表重新读取服务端记录。 */
  refreshToken: number
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
  const [query, setQuery] = useState("")
  const [statusFilter, setStatusFilter] = useState("all")
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

  /** 确认重新质检：拉取完整记录拿服务器端路径，缺失（如清理后的临时文件）时报错。 */
  const confirmRerun = async (
    profile: string | null,
    passwords: { source: string; target: string },
  ) => {
    if (!rerunRecord) return
    try {
      const full = await api.historyItem(rerunRecord.record_id)
      if (!full.source_path || !full.target_path) {
        throw new Error("该记录缺少输入文档路径，无法重新质检")
      }
      onRerun(full, profile, passwords)
    } catch (exc) {
      const reason = exc instanceof Error ? exc.message : String(exc)
      messageApi.error(`准备重新质检失败：${reason}。请确认原文档仍可用后重试。`)
    } finally {
      setRerunRecord(null)
    }
  }

  const columns: ColumnsType<Omit<HistoryRecord, "report">> = [
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
    { title: "源文档", dataIndex: "source_display", ellipsis: true },
    { title: "目标文档", dataIndex: "target_display", ellipsis: true },
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
      title: "问题",
      dataIndex: "issue_total",
      width: 70,
      align: "right",
      // 无问题弱化展示，有问题红字突出，扫一眼即可定位差记录。
      render: (value: number) =>
        value > 0 ? (
          <Typography.Text strong style={{ color: PALETTE.criticalText }}>
            {value}
          </Typography.Text>
        ) : (
          <Typography.Text type="secondary">0</Typography.Text>
        ),
    },
    {
      title: "操作",
      width: 256,
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
        </Space>
      ),
    },
  ]

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
      <PageSection
        className="history-records"
        extra={
          <Space className="history-records__filters" wrap>
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
            loading={loading}
            columns={columns}
            dataSource={filteredRecords}
            scroll={{ x: HISTORY_TABLE_MIN_WIDTH }}
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
        onConfirm={(profile, passwords) => void confirmRerun(profile, passwords)}
        onClose={() => setRerunRecord(null)}
      />
    </div>
  )
}
