import { useState } from "react"
import { api, type StageItem } from "../api"

const STAGES = ["parse", "group", "alignment", "match", "detect", "report"] as const

const STAGE_NAME: Record<string, string> = {
  parse: "解析",
  group: "分组",
  alignment: "页对齐",
  match: "匹配",
  detect: "检测",
  report: "报告",
}

/**
 * 分阶段验证：逐阶段执行并在阶段之间停下等用户确认，与 AGENTS.md
 * 约定的开发验证流程一致。已完成阶段展示摘要，可展开原始数据。
 */
export function StageView({ source, target }: { source: string; target: string }) {
  const [stages, setStages] = useState<StageItem[]>([])
  const [busy, setBusy] = useState(false)
  const [openStage, setOpenStage] = useState<string | null>(null)
  const [error, setError] = useState("")

  const nextStage = STAGES[stages.length] as (typeof STAGES)[number] | undefined

  const runNext = async () => {
    if (!nextStage) return
    setBusy(true)
    setError("")
    try {
      const response = await api.verify(source, target, nextStage)
      setStages(response.stages)
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="stages">
      <div className="stage-controls">
        <button onClick={() => void runNext()} disabled={busy || !nextStage}>
          {busy
            ? "执行中…"
            : nextStage
              ? `执行到「${STAGE_NAME[nextStage]}」阶段`
              : "全部阶段已完成"}
        </button>
        {stages.length > 0 && (
          <button className="ghost" onClick={() => setStages([])}>
            重新开始
          </button>
        )}
      </div>

      {error && <div className="banner banner-error">{error}</div>}

      <ol className="stage-list">
        {stages.map((item) => (
          <li key={item.stage} className="stage-item">
            <button
              className="stage-head"
              onClick={() =>
                setOpenStage(openStage === item.stage ? null : item.stage)
              }
            >
              <span className="stage-index">
                {STAGES.indexOf(item.stage as (typeof STAGES)[number]) + 1}
              </span>
              <span className="stage-name">{STAGE_NAME[item.stage]}</span>
              <span className="stage-summary">{item.summary}</span>
            </button>
            {openStage === item.stage && (
              <pre className="stage-data">
                {JSON.stringify(item.data, null, 2)}
              </pre>
            )}
          </li>
        ))}
      </ol>

      {stages.length === 0 && (
        <p className="empty">尚未执行。每个阶段执行后会显示摘要，点击可展开原始数据。</p>
      )}
    </section>
  )
}
