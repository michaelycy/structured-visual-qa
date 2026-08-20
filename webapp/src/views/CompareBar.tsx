/** 比较任务栏：源/目标文档选择 + 规则配置/术语库 + 提交按钮。 */

import { useState } from "react"
import { Button, Collapse, Select, Space, Upload, message } from "antd"
import { InboxOutlined, SettingOutlined } from "@ant-design/icons"
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
  profileFilename: string | null
  onGlossary: (reference: string | null) => void
  onProfile: (filename: string | null) => void
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

const PICKER_LABEL_STYLE: React.CSSProperties = {
  fontSize: 12,
  color: "rgba(0,0,0,0.45)",
}

/** 与服务端 FileService 的上限保持一致（100 MiB）。 */
const MAX_UPLOAD_MB = 100

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
  const [messageApi, contextHolder] = message.useMessage()

  const loadSamples = () => {
    if (samples.length) return
    api.sampleFiles().then(setSamples).catch(() => undefined)
  }

  return (
    <Space direction="vertical" size={4} style={{ flex: 1, minWidth: 220 }}>
      {contextHolder}
      <span style={PICKER_LABEL_STYLE}>{label}</span>
      <Space.Compact style={{ width: "100%" }}>
        <Upload
          name="file"
          accept=".pdf,.docx,.doc,.pptx,.ppt,.xlsx,.xls,.odt,.odp"
          showUploadList={false}
          // 大文件先在前端拦截（后端同样限额），避免白传上百 MB 才报错。
          beforeUpload={(file) => {
            if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
              messageApi.error(
                `「${file.name}」超过 ${MAX_UPLOAD_MB} MiB 限制，请压缩后再上传`,
              )
              return Upload.LIST_IGNORE
            }
            return true
          }}
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
              // 上传失败必须给出可见反馈（此前静默吞掉，用户无从得知）。
              messageApi.error(
                info.file.error?.message ?? `「${info.file.name}」上传失败`,
              )
            }
          }}
        >
          <Button icon={<InboxOutlined />} style={{ width: "100%" }}>
            {value.display || "点击选择文档"}
          </Button>
        </Upload>
        <Select
          placeholder="使用示例"
          style={{ minWidth: 120 }}
          value={null}
          onDropdownVisibleChange={loadSamples}
          onChange={(name) => {
            if (!name) return
            fetch(`/api/files/sample?name=${encodeURIComponent(name)}`, {
              method: "POST",
            })
              .then((r) => r.json())
              .then((payload) => onChange({ path: payload.path, display: payload.name }))
              .catch(() =>
                messageApi.error(`载入样例「${name}」失败，请重试`),
              )
          }}
          options={samples.map((name) => ({ value: name, label: name }))}
        />
      </Space.Compact>
    </Space>
  )
}

/** 顶部任务栏：两侧选择器 + 规则/术语 + 开始比较。 */
export function CompareBar({
  source,
  target,
  busy,
  glossaryReference,
  profileFilename,
  onGlossary,
  onProfile,
  onSource,
  onTarget,
  onSubmit,
}: CompareBarProps) {
  const [glossaries, setGlossaries] = useState<GlossarySummary[]>([])
  const [profiles, setProfiles] = useState<
    { filename: string; name: string; version: number }[]
  >([])
  const loadGlossaries = () => {
    if (glossaries.length) return
    api.glossaryList().then(setGlossaries).catch(() => undefined)
  }
  const loadProfiles = () => {
    if (profiles.length) return
    api
      .profileList()
      .then(setProfiles)
      .catch(() => undefined)
  }
  return (
    <Space direction="vertical" size={12} style={{ width: "100%" }}>
      <Space align="start" style={{ width: "100%" }} size={16} wrap>
        <DocumentPicker label="源文档（原文）" value={source} onChange={onSource} />
        <DocumentPicker label="目标文档（译文）" value={target} onChange={onTarget} />
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
      {/* 规则配置与术语库属于进阶能力，默认收起；普通用户开箱即用内置规则。 */}
      <Collapse
        size="small"
        items={[
          {
            key: "advanced",
            label: (
              <span style={{ fontSize: 13 }}>
                <SettingOutlined /> 高级选项（规则配置 / 术语库）
              </span>
            ),
            children: (
              <Space wrap size={16}>
                <Space direction="vertical" size={4}>
                  <span style={PICKER_LABEL_STYLE}>规则配置</span>
                  <Select
                    allowClear
                    placeholder="内置平衡配置（推荐）"
                    style={{ minWidth: 200 }}
                    value={profileFilename}
                    onDropdownVisibleChange={loadProfiles}
                    onChange={(value) => onProfile(value ?? null)}
                    options={profiles.map((item) => ({
                      value: item.filename,
                      label: `${item.name} v${item.version}`,
                    }))}
                  />
                </Space>
                <Space direction="vertical" size={4}>
                  <span style={PICKER_LABEL_STYLE}>术语库</span>
                  <Select
                    allowClear
                    placeholder="不启用"
                    style={{ minWidth: 200 }}
                    value={glossaryReference}
                    onDropdownVisibleChange={loadGlossaries}
                    onChange={(value) => onGlossary(value ?? null)}
                    options={glossaries.map((item) => ({
                      value: item.reference,
                      label: `${item.name} (${item.entry_count} 条)`,
                    }))}
                  />
                </Space>
              </Space>
            ),
          },
        ]}
      />
    </Space>
  )
}
