/** 比较任务栏：源/目标文档选择 + 提交按钮（antd 风格）。 */

import { useState } from "react"
import { Button, Select, Space, Upload } from "antd"
import { InboxOutlined } from "@ant-design/icons"
type UploadRequestOption = Parameters<NonNullable<import("antd/es/upload").UploadProps["customRequest"]>>[0]
import { api } from "../api"
import type { GlossarySummary } from "../api"

export interface DocumentRef {
  path: string
  display: string
}

export interface CompareBarProps {
  source: DocumentRef
  target: DocumentRef
  busy: boolean
  glossaryReference: string | null
  onGlossary: (reference: string | null) => void
  onSource: (doc: DocumentRef) => void
  onTarget: (doc: DocumentRef) => void
  onSubmit: () => void
}

/** 上传自定义请求：直接调后端 /api/files/upload。 */
async function customUpload(options: UploadRequestOption) {
  const { file, onSuccess, onError } = options
  const body = new FormData()
  body.append("file", file as File)
  try {
    const response = await fetch("/api/files/upload", { method: "POST", body })
    if (!response.ok) {
      const payload = await response.json().catch(() => null)
      throw new Error(payload?.detail ?? `上传失败 (HTTP ${response.status})`)
    }
    onSuccess?.(await response.json())
  } catch (exc) {
    onError?.(exc as Error)
  }
}

/** 单个文档选择：上传按钮 + 服务器样例下拉。 */
function DocumentPicker({
  label,
  value,
  onChange,
}: {
  label: string
  value: DocumentRef
  onChange: (doc: DocumentRef) => void
}) {
  const [samples, setSamples] = useState<string[]>([])

  const loadSamples = () => {
    if (samples.length) return
    api.sampleFiles().then(setSamples).catch(() => undefined)
  }

  return (
    <Space direction="vertical" size={4} style={{ flex: 1, minWidth: 220 }}>
      <span style={{ fontSize: 12, color: "rgba(0,0,0,0.45)" }}>{label}</span>
      <Space.Compact style={{ width: "100%" }}>
        <Upload
          name="file"
          accept=".pdf,.docx,.doc,.pptx,.ppt,.xlsx,.xls,.odt,.odp"
          showUploadList={false}
          customRequest={(options) =>
            void customUpload(options).then(() => undefined)
          }
          onChange={(info) => {
            if (info.file.status === "done" && info.file.response) {
              onChange({
                path: info.file.response.path,
                display: info.file.response.name,
              })
            } else if (info.file.status === "error") {
              // 错误由 Upload 自身状态呈现，这里不重复弹层。
            }
          }}
        >
          <Button icon={<InboxOutlined />} style={{ width: "100%" }}>
            {value.display || "点击或拖入文档"}
          </Button>
        </Upload>
        <Select
          placeholder="服务器样例"
          style={{ minWidth: 140 }}
          value={null}
          onDropdownVisibleChange={loadSamples}
          onChange={(name) => {
            if (!name) return
            fetch(`/api/files/sample?name=${encodeURIComponent(name)}`, {
              method: "POST",
            })
              .then((r) => r.json())
              .then((payload) => onChange({ path: payload.path, display: payload.name }))
              .catch(() => undefined)
          }}
          options={samples.map((name) => ({ value: name, label: name }))}
        />
      </Space.Compact>
    </Space>
  )
}

/** 顶部任务栏：两侧选择器 + 开始比较。 */
export function CompareBar({
  source,
  target,
  busy,
  glossaryReference,
  onGlossary,
  onSource,
  onTarget,
  onSubmit,
}: CompareBarProps) {
  const [glossaries, setGlossaries] = useState<GlossarySummary[]>([])
  const loadGlossaries = () => {
    if (glossaries.length) return
    api.glossaryList().then(setGlossaries).catch(() => undefined)
  }
  return (
    <Space align="start" style={{ width: "100%" }} size={16} wrap>
      <DocumentPicker label="源文档（原文）" value={source} onChange={onSource} />
      <DocumentPicker label="目标文档（译文）" value={target} onChange={onTarget} />
      <Space direction="vertical" size={4}>
        <span style={{ fontSize: 12, color: "rgba(0,0,0,0.45)" }}>术语库</span>
        <Select
          allowClear
          placeholder="不启用"
          style={{ minWidth: 180 }}
          value={glossaryReference}
          onDropdownVisibleChange={loadGlossaries}
          onChange={(value) => onGlossary(value ?? null)}
          options={glossaries.map((item) => ({
            value: item.reference,
            label: `${item.name} (${item.entry_count} 条)`,
          }))}
        />
      </Space>
      <Button
        type="primary"
        loading={busy}
        disabled={!source.path || !target.path}
        onClick={onSubmit}
        style={{ marginTop: 20 }}
      >
        开始比较
      </Button>
    </Space>
  )
}
