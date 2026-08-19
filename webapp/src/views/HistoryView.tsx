/** 对比记录页：antd Table，可回看完整报告。 */

import { useEffect, useState } from "react"
import { message, Table, Tag, Typography } from "antd"
import type { ColumnsType } from "antd/es/table"
import { api, type HistoryRecord } from "../api"

const STATUS_COLOR: Record<string, string> = {
  pass: "green",
  review: "orange",
  fail: "red",
}

export function HistoryView({
  onReopen,
}: {
  onReopen: (record: HistoryRecord) => void
}) {
  const [records, setRecords] = useState<Omit<HistoryRecord, "report">[]>([])
  const [loading, setLoading] = useState(true)
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
      width: 170,
      render: (value: string) => (
        <Typography.Text code style={{ fontSize: 12 }}>
          {value.slice(0, 19).replace("T", " ")}
        </Typography.Text>
      ),
    },
    { title: "源文档", dataIndex: "source_display", ellipsis: true },
    { title: "目标文档", dataIndex: "target_display", ellipsis: true },
    {
      title: "状态",
      dataIndex: "status",
      width: 90,
      render: (value: string) => (
        <Tag color={STATUS_COLOR[value] ?? "default"}>{value}</Tag>
      ),
    },
    {
      title: "分数",
      dataIndex: "document_score",
      width: 80,
      render: (value: number) => value.toFixed(1),
    },
    { title: "页面", dataIndex: "pages", width: 70 },
    { title: "问题", dataIndex: "issue_total", width: 70 },
    {
      title: "配置",
      dataIndex: "rule_profile_reference",
      width: 170,
      render: (value: string) => (
        <Typography.Text code style={{ fontSize: 12 }}>
          {value}
        </Typography.Text>
      ),
    },
    {
      title: "操作",
      width: 90,
      render: (_, record) => (
        <a onClick={() => void reopen(record.record_id)}>查看</a>
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
    </div>
  )
}
