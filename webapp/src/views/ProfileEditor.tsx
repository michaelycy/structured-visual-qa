import { useEffect, useState } from "react"
import { api, type RuleProfile } from "../api"

/**
 * 规则配置编辑器：加载内置默认值，编辑关键数字项后交由服务端
 * Pydantic 严格校验保存。完整 Schema 项以只读分组展示，避免
 * 自制表单与核心校验规则漂移。
 */
export function ProfileEditor() {
  const [profile, setProfile] = useState<RuleProfile | null>(null)
  const [message, setMessage] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.defaultProfile().then(setProfile).catch(() => setError("无法加载默认配置"))
  }, [])

  if (!profile) {
    return <p className="empty">{error || "加载默认配置…"}</p>
  }

  /** 数值字段的受控更新；非法输入保持原值，由服务端校验兜底。 */
  const setNumber = (path: string[], value: string) => {
    const next = structuredClone(profile)
    let node: Record<string, unknown> = next
    for (const key of path.slice(0, -1)) {
      node = node[key] as Record<string, unknown>
    }
    const num = Number(value)
    node[path[path.length - 1]] = Number.isFinite(num) ? num : value
    setProfile(next)
  }

  const save = async () => {
    setBusy(true)
    setError("")
    setMessage("")
    try {
      const saved = await api.saveProfile(profile)
      setMessage(`已保存 ${saved.reference} → ${saved.path}`)
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setBusy(false)
    }
  }

  const numberField = (label: string, path: string[], value: number, step = 0.05) => (
    <label key={path.join(".")} className="field">
      <span>{label}</span>
      <input
        type="number"
        step={step}
        value={value}
        onChange={(e) => setNumber(path, e.target.value)}
      />
    </label>
  )

  return (
    <section className="profile">
      <div className="profile-meta">
        <label className="field">
          <span>配置名称</span>
          <input
            value={String(profile.name ?? "")}
            onChange={(e) => setProfile({ ...profile, name: e.target.value })}
          />
        </label>
        <label className="field">
          <span>profile_id</span>
          <input
            value={String(profile.profile_id ?? "")}
            onChange={(e) => setProfile({ ...profile, profile_id: e.target.value })}
          />
        </label>
        <label className="field">
          <span>版本号</span>
          <input
            type="number"
            step={1}
            value={Number(profile.version ?? 1)}
            onChange={(e) => setNumber(["version"], e.target.value)}
          />
        </label>
      </div>

      <h3>匹配设置</h3>
      <div className="field-grid">
        {numberField("最低匹配分", ["matching", "minimum_score"], Number((profile.matching as Record<string, number>).minimum_score))}
        {numberField("合并文本覆盖率", ["matching", "merged_text_coverage_ratio"], Number((profile.matching as Record<string, number>).merged_text_coverage_ratio))}
      </div>

      <h3>页对齐</h3>
      <div className="field-grid">
        {numberField("最大页码偏移", ["alignment", "max_shift"], Number((profile.alignment as Record<string, number>).max_shift), 1)}
        {numberField("跳页代价", ["alignment", "skip_penalty"], Number((profile.alignment as Record<string, number>).skip_penalty))}
      </div>

      <h3>检测阈值</h3>
      <div className="field-grid">
        {numberField("偏移阈值", ["detectors", "thresholds", "shifted_ratio"], Number(((profile.detectors as Record<string, never>).thresholds as Record<string, number>).shifted_ratio))}
        {numberField("严重偏移阈值", ["detectors", "thresholds", "severely_shifted_ratio"], Number(((profile.detectors as Record<string, never>).thresholds as Record<string, number>).severely_shifted_ratio))}
        {numberField("字号缩小阈值", ["detectors", "thresholds", "font_shrink_ratio"], Number(((profile.detectors as Record<string, never>).thresholds as Record<string, number>).font_shrink_ratio), 0.01)}
        {numberField("重叠比例阈值", ["detectors", "thresholds", "overlap_ratio"], Number(((profile.detectors as Record<string, never>).thresholds as Record<string, number>).overlap_ratio))}
      </div>

      <h3>评分线</h3>
      <div className="field-grid">
        {numberField("PASS 分数线", ["scoring", "pass_score"], Number((profile.scoring as Record<string, number>).pass_score), 1)}
        {numberField("FAIL 分数线", ["scoring", "fail_score"], Number((profile.scoring as Record<string, number>).fail_score), 1)}
      </div>

      <div className="stage-controls">
        <button onClick={() => void save()} disabled={busy}>
          {busy ? "保存中…" : "校验并保存"}
        </button>
        <button
          className="ghost"
          onClick={() => {
            api.defaultProfile().then(setProfile)
            setMessage("")
          }}
        >
          重置为默认
        </button>
      </div>

      {message && <div className="banner banner-ok">{message}</div>}
      {error && <div className="banner banner-error">{error}</div>}
    </section>
  )
}
