/** 对比记录页：antd Table + 详情抽屉，行内即看摘要，抽屉看完整详情。 */

import { useEffect, useState } from "react"
import { Badge, message, Modal, Select, Space, Table, Tag, Tooltip, Typography, Input } from "antd"
import type { ColumnsType } from "antd/es/table"
import { api, type HistoryRecord } from "../api"
import { HistoryDetail } from "./HistoryDetail"
import { STATUS_META, scoreColor } from "../uiTokens"

/** 本地时间格式化：created_at 为 UTC ISO 串，直接截串会差时区。 */
function formatTime(iso: string): string {
  const date = new Date(iso)
  return Number.isNaN(date.getTime())
    ? iso
    : date.toLocaleString("zh-CN", { hour12: false })
}

/** 重新比较弹窗：选择执行配置（沿用当前或换其他配置）。
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
      title="重新执行比较"
      okText="开始比较"
      cancelText="取消"
      onOk={() =>
        onConfirm(profile, { source: sourcePassword, target: targetPassword })
      }
      onCancel={onClose}
      destroyOnClose
    >
      <Typography.Paragraph style={{ fontSize: 13 }}>
        将重新比较 <strong>{record?.source_display}</strong> →{" "}
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
      <Typography.Text type="secondary" style={{ fontSize: 12, display: "block", marginTop: 8 }}>
        不选择则使用工作台当前配置（含规则配置与术语库）；清除输入框可恢复默认。
      </Typography.Text>
      <Typography.Paragraph style={{ fontSize: 12, marginTop: 12, marginBottom: 8 }}>
        若文档受打开密码保护，请重新输入密码（密码不保存）：
      </Typography.Paragraph>
      <Space direction="vertical" size={8} style={{ width: "100%" }}>
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
  onReopen,
  onRerun,
}: {
  onReopen: (record: HistoryRecord) => void
  /** 重新执行比较：profile 为 null 沿用工作台当前配置；密码不落历史需重输。 */
  onRerun: (
    record: HistoryRecord,
    profile: string | null,
    passwords: { source: string; target: string },
  ) => void
}) {
  const [records, setRecords] = useState<Omit<HistoryRecord, "report">[]>([])
  const [loading, setLoading] = useState(true)
  const [detailRecord, setDetailRecord] = useState<
    Omit<HistoryRecord, "report"> | null
  >(null)
  // 重新比较目标：先存摘要行，确认时再拉完整记录取路径。
  const [rerunRecord, setRerunRecord] = useState<Omit<HistoryRecord, "report"> | null>(null)
  const [messageApi, contextHolder] = message.useMessage()

  useEffect(() => {
    api
      .historyList()
      .then(setRecords)
      .catch((exc) =>
        messageApi.error(exc instanceof Error ? exc.message : String(exc)),
      )
      .finally(() => setLoading(false))
  }, [messageApi])

  const reopen = async (recordId: string) => {
    try {
      const record = await api.historyItem(recordId)
      if (!record.report) throw new Error("该记录不含完整报告")
      onReopen(record)
    } catch (exc) {
      messageApi.error(exc instanceof Error ? exc.message : String(exc))
    }
  }

  /** 确认重新比较：拉取完整记录拿服务器端路径，缺失（如清理后的临时文件）时报错。 */
  const confirmRerun = async (
    profile: string | null,
    passwords: { source: string; target: string },
  ) => {
    if (!rerunRecord) return
    try {
      const full = await api.historyItem(rerunRecord.record_id)
      if (!full.source_path || !full.target_path) {
        throw new Error("该记录缺少输入文档路径，无法重新比较")
      }
      onRerun(full, profile, passwords)
    } catch (exc) {
      messageApi.error(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setRerunRecord(null)
    }
  }

  const columns: ColumnsType<Omit<HistoryRecord, "report">> = [
    {
      title: "时间",
      dataIndex: "created_at",
      width: 165,
      render: (value: string) => (
        <Tooltip title={value}>
          <Typography.Text style={{ fontSize: 12 }}>
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
      render: (value: string) => {
        const meta = STATUS_META[value]
        return meta ? (
          <Badge status={meta.badge} text={meta.label} />
        ) : (
          <Tag>{value}</Tag>
        )
      },
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
          <Typography.Text strong style={{ color: "#cf1322" }}>
            {value}
          </Typography.Text>
        ) : (
          <Typography.Text type="secondary">0</Typography.Text>
        ),
    },
    {
      title: "操作",
      width: 230,
      // 防止 antd Table 单元格内容换行导致行高抖动。
      onCell: () => ({ style: { whiteSpace: "nowrap" } }),
      render: (_, record) => (
        <>
          <a onClick={() => setDetailRecord(record)}>详情</a>
          <Typography.Text type="secondary" style={{ margin: "0 8px" }}>
            |
          </Typography.Text>
          <a onClick={() => void reopen(record.record_id)}>工作台打开</a>
          <Typography.Text type="secondary" style={{ margin: "0 8px" }}>
            |
          </Typography.Text>
          <a onClick={() => setRerunRecord(record)}>重新比较</a>
        </>
      ),
    },
  ]

  return (
    <div>
      {contextHolder}
      <Table
        size="small"
        rowKey="record_id"
        loading={loading}
        columns={columns}
        dataSource={records}
        pagination={{ pageSize: 10, showSizeChanger: false }}
        locale={{
          emptyText: "还没有比较记录。执行一次比较后会自动保存到这里。",
        }}
      />
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
