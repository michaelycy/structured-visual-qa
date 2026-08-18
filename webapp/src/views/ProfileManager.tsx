import { useCallback, useEffect, useState } from "react"
import { api, type RuleProfile } from "../api"
import { ProfileEditor } from "./ProfileEditor"

interface ProfileListItem {
  filename: string
  profile_id: string
  name: string
  version: number
  status: string
  reference: string
}

/**
 * 规则管理页：已保存 Profile 的列表 + 生命周期操作。
 * 新建从内置默认配置起步；编辑某项时加载完整配置进入表单；
 * 复制派生保留全部阈值、只换 ID 与版本，便于调参对照。
 */
export function ProfileManager() {
  const [profiles, setProfiles] = useState<ProfileListItem[]>([])
  const [editing, setEditing] = useState<RuleProfile | null>(null)
  const [error, setError] = useState("")
  const [message, setMessage] = useState("")

  const refresh = useCallback(() => {
    api
      .profileList()
      .then(setProfiles)
      .catch((exc) => setError(exc instanceof Error ? exc.message : String(exc)))
  }, [])

  useEffect(refresh, [refresh])

  const startNew = () => {
    api
      .defaultProfile()
      .then((profile) => {
        setEditing({ ...profile, profile_id: "custom-rules", name: "自定义规则", version: 1 })
        setMessage("")
      })
      .catch((exc) => setError(exc instanceof Error ? exc.message : String(exc)))
  }

  const startEdit = (filename: string) => {
    api
      .profileItem(filename)
      .then((profile) => {
        setEditing(profile)
        setMessage("")
      })
      .catch((exc) => setError(exc instanceof Error ? exc.message : String(exc)))
  }

  const startFork = (filename: string) => {
    api
      .profileItem(filename)
      .then((profile) =>
        setEditing({
          ...profile,
          profile_id: `${profile.profile_id}-copy`,
          name: `${profile.name}（副本）`,
        }),
      )
      .catch((exc) => setError(exc instanceof Error ? exc.message : String(exc)))
  }

  const remove = async (filename: string, reference: string) => {
    if (!window.confirm(`确定删除 ${reference}？此操作不可恢复。`)) return
    try {
      await api.profileDelete(filename)
      setMessage(`已删除 ${reference}`)
      refresh()
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    }
  }

  return (
    <section className="profile-manager">
      <div className="manager-header">
        <h2>规则配置管理</h2>
        <button onClick={startNew}>新建配置</button>
      </div>

      {error && <div className="banner banner-error">{error}</div>}
      {message && <div className="banner banner-ok">{message}</div>}

      {profiles.length === 0 ? (
        <p className="empty">
          尚未保存任何规则配置。点击「新建配置」从内置平衡配置起步。
        </p>
      ) : (
        <table className="profile-table">
          <thead>
            <tr>
              <th>名称</th>
              <th>标识</th>
              <th>版本</th>
              <th>状态</th>
              <th>引用</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {profiles.map((item) => (
              <tr key={item.filename}>
                <td>{item.name}</td>
                <td className="mono">{item.profile_id}</td>
                <td>v{item.version}</td>
                <td>
                  <span className={`status-pill st-${item.status}`}>{item.status}</span>
                </td>
                <td className="mono">{item.reference}</td>
                <td>
                  <button className="ghost small" onClick={() => startEdit(item.filename)}>
                    编辑
                  </button>
                  <button className="ghost small" onClick={() => startFork(item.filename)}>
                    复制派生
                  </button>
                  <button
                    className="ghost small danger"
                    onClick={() => void remove(item.filename, item.reference)}
                  >
                    删除
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {editing && (
        <div className="manager-editor">
          <h3>编辑配置</h3>
          <ProfileEditor
            initial={editing}
            onSaved={(reference) => {
              setMessage(`已保存 ${reference}`)
              setEditing(null)
              refresh()
            }}
          />
        </div>
      )}
    </section>
  )
}
