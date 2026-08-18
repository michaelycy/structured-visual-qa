import { useEffect, useState } from "react"
import { api, type HistoryRecord } from "../api"

/** 对比记录页：历史比较任务列表，可点击回看完整报告。 */
export function HistoryView({ onReopen }: { onReopen: (record: HistoryRecord) => void }) {
  const [records, setRecords] = useState<Omit<HistoryRecord, "report">[] | null>(null)
  const [error, setError] = useState("")
  const [busyId, setBusyId] = useState("")

  const refresh = () => {
    api
      .historyList()
      .then(setRecords)
      .catch((exc) => setError(exc instanceof Error ? exc.message : String(exc)))
  }

  useEffect(refresh, [])

  const reopen = async (recordId: string) => {
    setBusyId(recordId)
    setError("")
    try {
      const record = await api.historyItem(recordId)
      if (!record.report) throw new Error("该记录不含完整报告")
      onReopen(record)
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setBusyId("")
    }
  }

  if (error && !records) return <p className="empty">{error}</p>
  if (!records) return <p className="empty">加载对比记录…</p>
  if (records.length === 0)
    return <p className="empty">还没有比较记录。执行一次比较后会自动保存到这里。</p>

  return (
    <section>
      {error && <div className="banner banner-error">{error}</div>}
      <table className="profile-table">
        <thead>
          <tr>
            <th>时间</th>
            <th>源文档</th>
            <th>目标文档</th>
            <th>状态</th>
            <th>分数</th>
            <th>页面</th>
            <th>问题</th>
            <th>配置</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {records.map((item) => (
            <tr key={item.record_id}>
              <td className="mono">{item.created_at.slice(0, 19).replace("T", " ")}</td>
              <td>{item.source_display}</td>
              <td>{item.target_display}</td>
              <td>
                <span className={`sev-badge sev-${item.status}`}>{item.status}</span>
              </td>
              <td>{item.document_score.toFixed(1)}</td>
              <td>{item.pages}</td>
              <td>{item.issue_total}</td>
              <td className="mono">{item.rule_profile_reference}</td>
              <td>
                <button
                  className="ghost small"
                  disabled={busyId === item.record_id}
                  onClick={() => void reopen(item.record_id)}
                >
                  {busyId === item.record_id ? "加载中…" : "查看"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
