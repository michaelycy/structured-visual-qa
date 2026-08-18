/** PDF 选择组件：文件选择/拖放上传 + 服务器样例下拉。 */

import { useRef, useState } from "react"
import { api } from "../api"

export interface PdfPickerProps {
  label: string
  /** 当前选中的服务器端路径；空表示未选择。 */
  value: string
  display: string
  onPicked: (path: string, display: string) => void
}

/** 把 File 上传到后端，返回服务器端路径。 */
async function uploadFile(file: File): Promise<{ path: string; name: string }> {
  const body = new FormData()
  body.append("file", file)
  const response = await fetch("/api/files/upload", { method: "POST", body })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail ?? `上传失败 (HTTP ${response.status})`)
  }
  return response.json()
}

export function PdfPicker({ label, value, display, onPicked }: PdfPickerProps) {
  const input_ref = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [samples, setSamples] = useState<string[] | null>(null)

  const handleFiles = async (files: FileList | null) => {
    const file = files?.[0]
    if (!file) return
    setBusy(true)
    setError("")
    try {
      const uploaded = await uploadFile(file)
      onPicked(uploaded.path, uploaded.name)
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setBusy(false)
    }
  }

  const pickSample = async (name: string) => {
    if (!name) return
    setBusy(true)
    setError("")
    try {
      const response = await fetch(
        `/api/files/sample?name=${encodeURIComponent(name)}`,
        { method: "POST" },
      )
      if (!response.ok) throw new Error(`样例加载失败 (HTTP ${response.status})`)
      const payload = await response.json()
      onPicked(payload.path, payload.name)
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setBusy(false)
    }
  }

  const loadSamples = () => {
    if (samples) return
    api
      .sampleFiles()
      .then((list) => setSamples(list))
      .catch(() => setError("无法加载样例列表"))
  }

  return (
    <div className="picker">
      <span className="picker-label">{label}</span>

      <div
        className={dragging ? "picker-drop dragging" : "picker-drop"}
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault()
          setDragging(false)
          void handleFiles(event.dataTransfer.files)
        }}
        onClick={() => input_ref.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") input_ref.current?.click()
        }}
      >
        {busy ? (
          <span className="picker-hint">上传中…</span>
        ) : value ? (
          <span className="picker-file">{display}</span>
        ) : (
          <span className="picker-hint">点击选择或拖入 PDF 文件</span>
        )}
      </div>
      <input
        ref={input_ref}
        type="file"
        accept="application/pdf,.pdf"
        hidden
        onChange={(event) => void handleFiles(event.target.files)}
      />

      <select
        className="picker-samples"
        value=""
        onFocus={loadSamples}
        onClick={loadSamples}
        onChange={(event) => void pickSample(event.target.value)}
        aria-label={`${label}：从服务器样例选择`}
      >
        <option value="">
          {samples ? "从服务器样例选择…" : "加载服务器样例…"}
        </option>
        {(samples ?? []).map((name) => (
          <option key={name} value={name}>
            {name}
          </option>
        ))}
      </select>

      {error && <span className="picker-error">{error}</span>}
    </div>
  )
}
