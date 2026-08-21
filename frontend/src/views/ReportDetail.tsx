/** 报告详情聚合组件：总览 + 逐页复核，工作台与历史记录抽屉共用。
 *
 * 复核闭环逻辑（taskId 派生、判定加载与提交）原先散在 App.tsx，
 * 历史抽屉要展示同样能力就必须复制一份；此处收拢为单一所有者，
 * 两个入口共享同一份状态与行为。
 */

import { useCallback, useEffect, useState } from "react"
import { message } from "antd"
import type { QAReport, ReviewDecision } from "../api"
import { api } from "../services/queryClient"
import { ReportOverview } from "./ReportOverview"
import { PageDetails } from "./PageDetails"
import type { PageDetailsViewState } from "./PageDetails"

export function ReportDetail({
  report,
  rendered,
  historyRecordId,
  viewState,
  onViewStateChange,
}: {
  report: QAReport
  rendered?: { source: string[]; target: string[] }
  historyRecordId: string | null
  viewState?: PageDetailsViewState
  onViewStateChange?: (state: PageDetailsViewState) => void
}) {
  const [decisions, setDecisions] = useState<Record<string, ReviewDecision>>({})
  const [messageApi, contextHolder] = message.useMessage()

  // 复核任务 ID 由双方文档摘要组成，同一对文档的判定自然延续——
  // 无论从工作台还是历史记录进入，看到的是同一份复核进度。
  const taskId = `${report.source_document_id.slice(0, 12)}-${report.target_document_id.slice(0, 12)}`

  // 报告对象切换时重置并拉取已有判定；无记录时静默忽略。
  useEffect(() => {
    setDecisions({})
    api
      .reviewTask(taskId)
      .then((record) =>
        setDecisions(
          Object.fromEntries(
            Object.entries(record.decisions).map(([k, v]) => [k, v.decision]),
          ),
        ),
      )
      .catch(() => undefined)
  }, [taskId])

  const decide = useCallback(
    (issueId: string, decision: ReviewDecision) => {
      const previousDecision = decisions[issueId]
      setDecisions((prev) => ({ ...prev, [issueId]: decision }))
      api
        .reviewDecision(taskId, report, issueId, decision)
        .catch((exc) => {
          // 请求失败时只回滚本次仍在展示的乐观结果，避免覆盖用户随后提交的新判定。
          setDecisions((current) => {
            if (current[issueId] !== decision) return current
            const next = { ...current }
            if (previousDecision) next[issueId] = previousDecision
            else delete next[issueId]
            return next
          })
          const reason = exc instanceof Error ? exc.message : String(exc)
          messageApi.error(`复核结果保存失败：${reason}。请检查服务状态后重试。`)
        })
    },
    [taskId, report, decisions, messageApi],
  )

  return (
    <>
      {contextHolder}
      <div className="report-dashboard">
        <ReportOverview
          report={report}
          historyRecordId={historyRecordId}
          reviewedCount={Object.keys(decisions).length}
        />
        <PageDetails
          report={report}
          rendered={rendered}
          taskId={taskId}
          decisions={decisions}
          onDecide={decide}
          viewState={viewState}
          onViewStateChange={onViewStateChange}
        />
      </div>
    </>
  )
}
