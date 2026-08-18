import { useState } from "react"
import { api, type CompareResponse } from "./api"
import { ReportOverview } from "./views/ReportOverview"
import { PageDetails } from "./views/PageDetails"
import { StageView } from "./views/StageView"
import { ProfileEditor } from "./views/ProfileEditor"
import { PdfPicker } from "./views/PdfPicker"

type Tab = "overview" | "pages" | "stages" | "profile"

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

  const runCompare = async () => {
    setBusy(true)
    setError("")
    try {
      const response = await api.compare(source.path, target.path)
      setResult(response)
      setTab("overview")
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setBusy(false)
    }
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
            ["profile", "规则配置"],
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
            <PageDetails report={result.report} />
          ) : (
            <p className="empty">先执行一次比较，再查看逐页详情。</p>
          ))}
        {tab === "stages" && (
          <StageView source={source.path} target={target.path} />
        )}
        {tab === "profile" && <ProfileEditor />}
      </main>
    </div>
  )
}
