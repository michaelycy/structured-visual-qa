import { useState } from "react"
import {
  api,
  type CompareResponse,
  type ReviewDecision,
} from "./api"
import { ReportOverview } from "./views/ReportOverview"
import { PageDetails } from "./views/PageDetails"
import { StageView } from "./views/StageView"
import { ProfileEditor } from "./views/ProfileEditor"
import { ProfileManager } from "./views/ProfileManager"
import { PdfPicker } from "./views/PdfPicker"

type Tab = "overview" | "pages" | "stages" | "profile" | "manager"

/** 共享的任务输入状态：三个视图都围绕同一对 PDF 工作。 */
export function App() {
  // 浏览器安全模型不允许读取本地路径，选择器走上传模式：
  // state 保存服务器端路径，display 只用于界面展示。
  const [source, setSource] = useState({ path: "", display: "" })
  const [target, setTarget] = useState({ path: "", display: "" })
  const [tab, setTab] = useState<Tab>("overview")
  const [result, setResult] = useState<CompareResponse | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  // 复核闭环：比较完成后生成任务 ID，判定按 Issue 粒度持久化。
  const [taskId, setTaskId] = useState<string | null>(null)
  const [decisions, setDecisions] = useState<Record<string, ReviewDecision>>({})

  const runCompare = async () => {
    setBusy(true)
    setError("")
    try {
      const response = await api.compare(source.path, target.path)
      setResult(response)
      setTab("overview")
      // 任务 ID 由双方文档摘要组成，同一对文档的复核记录自然延续。
      const srcId = response.report.source_document_id.slice(0, 12)
      const tgtId = response.report.target_document_id.slice(0, 12)
      const id = `${srcId}-${tgtId}`
      setTaskId(id)
      setDecisions({})
      // 尝试恢复该文档对的历史判定。
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

  return (
    <div className="app">
      <header className="app-header">
        <h1>Structured Visual QA</h1>
        <span className="app-sub">翻译 PDF 结构与视觉保真度检查</span>
      </header>

      <form
        className="run-bar"
        onSubmit={(event) => {
          event.preventDefault()
          void runCompare()
        }}
      >
        <PdfPicker
          label="源 PDF"
          value={source.path}
          display={source.display}
          onPicked={(path, display) => setSource({ path, display })}
        />
        <PdfPicker
          label="目标 PDF"
          value={target.path}
          display={target.display}
          onPicked={(path, display) => setTarget({ path, display })}
        />
        <button type="submit" disabled={busy || !source.path || !target.path}>
          {busy ? "比较中…" : "开始比较"}
        </button>
      </form>

      {error && <div className="banner banner-error">{error}</div>}

      <nav className="tabs" role="tablist">
        {(
          [
            ["overview", "报告总览"],
            ["pages", "逐页详情"],
            ["stages", "分阶段验证"],
            ["manager", "规则管理"],
            ["profile", "快速配置"],
          ] as [Tab, string][]
        ).map(([key, label]) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            className={tab === key ? "tab active" : "tab"}
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
      </nav>

      <main>
        {tab === "overview" &&
          (result ? (
            <ReportOverview report={result.report} />
          ) : (
            <p className="empty">输入路径后点击「开始比较」生成报告。</p>
          ))}
        {tab === "pages" &&
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
        {tab === "stages" && (
          <StageView source={source.path} target={target.path} />
        )}
        {tab === "manager" && <ProfileManager />}
        {tab === "profile" && <ProfileEditor />}
      </main>
    </div>
  )
}
