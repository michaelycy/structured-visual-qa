/** 对比记录页：antd Table + 详情抽屉，行内即看摘要，抽屉看完整详情。 */

import { useEffect, useState } from "react"
import { Badge, message, Table, Tag, Tooltip, Typography } from "antd"
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

export function HistoryView({
  onReopen,
}: {
  onReopen: (record: HistoryRecord) => void
}) {
  const [records, setRecords] = useState<Omit<HistoryRecord, "report">[]>([])
  const [loading, setLoading] = useState(true)
  const [detailRecord, setDetailRecord] = useState<
    Omit<HistoryRecord, "report"> | null
  >(null)
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
      width: 130,
      render: (_, record) => (
        <>
          <a onClick={() => setDetailRecord(record)}>详情</a>
          <Typography.Text type="secondary" style={{ margin: "0 8px" }}>
            |
          </Typography.Text>
          <a onClick={() => void reopen(record.record_id)}>工作台打开</a>
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
    </div>
  )
}
