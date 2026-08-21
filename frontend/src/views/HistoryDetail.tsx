/** 质检记录详情抽屉：直接内嵌共用的 ReportDetail（总览 + 逐页复核）。
 *
 * 历史记录不含页面渲染图，逐页详情以 Issue 列表为主；复核判定
 * 按 Issue 粒度持久化，与工作台共享同一份进度。
 */

import { useEffect, useState } from "react"
import { Drawer, Empty, message, Spin } from "antd"
import type { HistoryRecord } from "../api"
import { api } from "../services/queryClient"
import { ReportDetail } from "./ReportDetail"

export function HistoryDetail({
  record,
  open,
  onClose,
}: {
  record: Omit<HistoryRecord, "report"> | null
  open: boolean
  onClose: () => void
}) {
  const [full, setFull] = useState<HistoryRecord | null>(null)
  const [loading, setLoading] = useState(false)
  const [messageApi, contextHolder] = message.useMessage()

  // 打开抽屉时拉取完整记录；record 切换时重置旧内容避免闪现上一条。
  useEffect(() => {
    if (!open || !record) return
    setFull(null)
    setLoading(true)
    api
      .historyItem(record.record_id)
      .then(setFull)
      .catch((exc) =>
        messageApi.error(exc instanceof Error ? exc.message : String(exc)),
      )
      .finally(() => setLoading(false))
  }, [open, record, messageApi])

  return (
    <Drawer
      open={open}
      onClose={onClose}
      size={1000}
      rootStyle={{ minWidth: "60vw" }}
      title={
        record ? (
          <span>
            质检记录详情 · {record.source_display} → {record.target_display}
          </span>
        ) : (
          "质检记录详情"
        )
      }
    >
      {contextHolder}
      {loading ? (
        <div style={{ textAlign: "center", padding: 48 }}>
          <Spin />
        </div>
      ) : !record ? null : full?.report ? (
        <ReportDetail
          report={full.report}
          rendered={full.rendered ?? { source: [], target: [] }}
          historyRecordId={record.record_id}
        />
      ) : (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="该记录不含完整报告（可能已被淘汰）。"
        />
      )}
    </Drawer>
  )
}
