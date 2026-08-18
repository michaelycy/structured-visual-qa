import { useState } from "react"
import {
  api,
  type CompareResponse,
  type HistoryRecord,
  type ReviewDecision,
} from "./api"
import { ReportOverview } from "./views/ReportOverview"
import { PageDetails } from "./views/PageDetails"
import { StageView } from "./views/StageView"
import { ProfileEditor } from "./views/ProfileEditor"
import { ProfileManager } from "./views/ProfileManager"
import { PdfPicker } from "./views/PdfPicker"
import { HistoryView } from "./views/HistoryView"

type View =
  | "overview"
  | "pages"
  | "stages"
  | "history"
  | "manager"
  | "profile"

const NAV_ITEMS: [View, string, string][] = [
  ["overview", "报告总览", "当前比较任务的状态、分数与严重度分布"],
  ["pages", "逐页详情", "源/目标页面对比、问题定位与人工判定"],
  ["stages", "分阶段验证", "parse → group → … 逐阶段执行与产物"],
  ["history", "对比记录", "历史比较任务列表，可回看完整报告"],
  ["manager", "规则管理", "规则配置的创建、编辑、派生与删除"],
  ["profile", "快速配置", "基于内置默认配置的一次性阈值调整"],
]

/** 应用骨架：左侧菜单 + 右侧内容区，顶部为当前任务的比较入口。 */
export function App() {
  // 浏览器安全模型不允许读取本地路径，选择器走上传模式：
  // state 保存服务器端路径，display 只用于界面展示。
  const [source, setSource] = useState({ path: "", display: "" })
  const [target, setTarget] = useState({ path: "", display: "" })
  const [view, setView] = useState<View>("overview")
  const [result, setResult] = useState<CompareResponse | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  // 复核闭环：比较完成后生成任务 ID，判定按 Issue 粒度持久化。
  const [taskId, setTaskId] = useState<string | null>(null)
  const [decisions, setDecisions] = useState<Record<string, ReviewDecision>>({})

  const applyReport = (response: CompareResponse) => {
    setResult(response)
    setView("overview")
    // 任务 ID 由双方文档摘要组成，同一对文档的复核记录自然延续。
    const id = `${response.report.source_document_id.slice(0, 12)}-${response.report.target_document_id.slice(0, 12)}`
    setTaskId(id)
    setDecisions({})
    api
      .reviewTask(id)
      .then((record) =>
        setDecisions(
          Object.fromEntries(
            Object.entries(record.decisions).map(([k, v]) => [k, v.decision]),
          ),
        ),
      )
      .catch(() => undefined)
  }

  const runCompare = async () => {
    setBusy(true)
    setError("")
    try {
      const response = await api.compare(source.path, target.path, source.display, target.display)
      applyReport(response)
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setBusy(false)
    }
  }

  const decide = (issueId: string, decision: ReviewDecision) => {
    if (!taskId || !result) return
    setDecisions((prev) => ({ ...prev, [issueId]: decision }))
    api
      .reviewDecision(taskId, result.report, issueId, decision)
      .catch((exc) => setError(exc instanceof Error ? exc.message : String(exc)))
  }

  const reopenHistory = (record: HistoryRecord) => {
    if (!record.report) return
    applyReport({ report: record.report, rendered: { source: [], target: [] } })
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <h1>Structured Visual QA</h1>
          <span>翻译文档验收工作台</span>
        </div>
        <nav className="sidebar-nav" role="navigation">
          {NAV_ITEMS.map(([key, label, hint]) => (
            <button
              key={key}
              className={view === key ? "nav-item active" : "nav-item"}
              onClick={() => setView(key)}
              title={hint}
            >
              {label}
            </button>
          ))}
        </nav>
      </aside>

      <div className="main-col">
        <form
          className="run-bar"
          onSubmit={(event) => {
            event.preventDefault()
            void runCompare()
          }}
        >
          <PdfPicker
            label="源文档"
            value={source.path}
            display={source.display}
            onPicked={(path, display) => setSource({ path, display })}
          />
          <PdfPicker
            label="目标文档"
            value={target.path}
            display={target.display}
            onPicked={(path, display) => setTarget({ path, display })}
          />
          <button type="submit" disabled={busy || !source.path || !target.path}>
            {busy ? "比较中…" : "开始比较"}
          </button>
        </form>

        {error && <div className="banner banner-error">{error}</div>}

        <main>
          {view === "overview" &&
            (result ? (
              <ReportOverview report={result.report} />
            ) : (
              <p className="empty">选择源文档与目标文档后点击「开始比较」。</p>
            ))}
          {view === "pages" &&
            (result ? (
              <PageDetails
                report={result.report}
                rendered={result.rendered}
                taskId={taskId}
                decisions={decisions}
                onDecide={decide}
              />
            ) : (
              <p className="empty">先执行一次比较，再查看逐页详情。</p>
            ))}
          {view === "stages" && (
            <StageView source={source.path} target={target.path} />
          )}
          {view === "history" && <HistoryView onReopen={reopenHistory} />}
          {view === "manager" && <ProfileManager />}
          {view === "profile" && <ProfileEditor />}
        </main>
      </div>
    </div>
  )
}
