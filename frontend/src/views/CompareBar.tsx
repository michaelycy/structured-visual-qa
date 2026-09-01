/** 比较任务栏：源/目标文档选择 + 规则配置/术语库 + 提交按钮。 */

import { useId, useState } from "react"
import { Button, Collapse, Input, Select, Space, Upload, message } from "antd"
import {
  ArrowRightOutlined,
  FileTextOutlined,
  SearchOutlined,
  SettingOutlined,
} from "@ant-design/icons"
type UploadRequestOption = Parameters<NonNullable<import("antd/es/upload").UploadProps["customRequest"]>>[0]
import { api } from "../services/queryClient"
import type { GlossarySummary } from "../api"
import { PALETTE } from "../uiTokens"

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
  sourcePassword: string
  targetPassword: string
  onGlossary: (reference: string | null) => void
  onProfile: (filename: string | null) => void
  onSourcePassword: (value: string) => void
  onTargetPassword: (value: string) => void
  onSource: (doc: DocumentRef) => void
  onTarget: (doc: DocumentRef) => void
  onSubmit: () => void
}

/** 上传自定义请求：直接调后端 /api/files/upload。 */
async function customUpload(options: UploadRequestOption) {
  const { file, onSuccess, onError } = options
  try {
    onSuccess?.(await api.uploadDocument(file as File))
  } catch (exc) {
    onError?.(exc as Error)
  }
}

const PICKER_LABEL_STYLE: React.CSSProperties = {
  fontSize: 12,
  color: PALETTE.textSecondary,
}

/** 与服务端 FileService 的上限保持一致（100 MiB）。 */
const MAX_UPLOAD_MB = 100

/** 密码输入：仅在文档受打开密码保护时填写，不持久化。 */
function PasswordField({
  label,
  name,
  value,
  disabled,
  onChange,
}: {
  label: string
  name: string
  value: string
  disabled: boolean
  onChange: (value: string) => void
}) {
  const inputId = useId()
  return (
    <Space orientation="vertical" size={4}>
      <label htmlFor={inputId} style={PICKER_LABEL_STYLE}>{label}</label>
      <Input.Password
        id={inputId}
        name={name}
        placeholder="无密码时留空…"
        style={{ minWidth: 160 }}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        autoComplete="new-password"
      />
    </Space>
  )
}

/** 单个文档选择：上传按钮 + 服务器样例下拉。 */
function DocumentPicker({
  label,
  value,
  disabled,
  onChange,
}: {
  label: string
  value: DocumentRef
  disabled: boolean
  onChange: (doc: DocumentRef) => void
}) {
  const [samples, setSamples] = useState<string[]>([])
  const [messageApi, contextHolder] = message.useMessage()

  const loadSamples = () => {
    if (samples.length) return
    api.sampleFiles().then(setSamples).catch((error) => {
      const reason = error instanceof Error ? error.message : String(error)
      messageApi.error(`示例文档加载失败：${reason}。请检查服务状态后重试。`)
    })
  }

  return (
    <div className="document-picker">
      {contextHolder}
      <span className="document-picker__label">{label}</span>
      <Space.Compact style={{ width: "100%" }}>
        <Upload
          name="file"
          accept=".pdf,.docx,.doc,.pptx,.ppt,.xlsx,.xls,.odt,.odp"
          showUploadList={false}
          disabled={disabled}
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
          <Button
            className="document-picker__button"
            icon={<FileTextOutlined aria-hidden="true" />}
            disabled={disabled}
          >
            <span className="document-picker__filename">
              {value.display || "点击选择文档"}
            </span>
          </Button>
        </Upload>
        <Select
          aria-label={`${label}：从示例文档中选择`}
          placeholder="使用示例…"
          className="document-picker__sample"
          value={null}
          disabled={disabled}
          // 触发框固定 40px（只放下拉箭头）；面板若跟随触发器宽度，
          // 长样例名会被裁成不可读，这里让面板按内容自适应。
          popupMatchSelectWidth={false}
          onOpenChange={(open) => open && loadSamples()}
          onChange={(name) => {
            if (!name) return
            api.samplePath(name)
              .then((payload) => onChange({ path: payload.path, display: payload.name }))
              .catch(() =>
                messageApi.error(`载入样例「${name}」失败，请重试`),
              )
          }}
          options={samples.map((name) => ({ value: name, label: name }))}
        />
      </Space.Compact>
    </div>
  )
}

/** 顶部任务栏：两侧选择器 + 规则/术语 + 开始比较。 */
export function CompareBar({
  source,
  target,
  busy,
  glossaryReference,
  profileFilename,
  sourcePassword,
  targetPassword,
  onGlossary,
  onProfile,
  onSourcePassword,
  onTargetPassword,
  onSource,
  onTarget,
  onSubmit,
}: CompareBarProps) {
  const [glossaries, setGlossaries] = useState<GlossarySummary[]>([])
  const [profiles, setProfiles] = useState<
    { filename: string; name: string; version: number; status: string }[]
  >([])
  const [messageApi, contextHolder] = message.useMessage()
  const loadGlossaries = () => {
    if (glossaries.length) return
    api.glossaryList().then(setGlossaries).catch((error) => {
      const reason = error instanceof Error ? error.message : String(error)
      messageApi.error(`术语库加载失败：${reason}。请检查服务状态后重试。`)
    })
  }
  const loadProfiles = () => {
    if (profiles.length) return
    api
      .profileList()
      .then((items) => setProfiles(items.filter((item) => item.status === "published")))
      .catch((error) => {
        const reason = error instanceof Error ? error.message : String(error)
        messageApi.error(`规则配置加载失败：${reason}。请检查服务状态后重试。`)
      })
  }
  return (
    <div className="compare-bar">
      {contextHolder}
      <div className="compare-bar__main">
        <DocumentPicker label="源文档（原文）" value={source} disabled={busy} onChange={onSource} />
        <ArrowRightOutlined className="compare-bar__arrow" aria-hidden="true" />
        <DocumentPicker label="目标文档（译文）" value={target} disabled={busy} onChange={onTarget} />
        <Button
          className="compare-bar__submit"
          type="primary"
          size="large"
          icon={<SearchOutlined aria-hidden="true" />}
          loading={busy}
          disabled={!source.path || !target.path}
          onClick={onSubmit}
        >
          开始质检
        </Button>
      </div>
      {/* 规则配置与术语库属于进阶能力，默认收起；普通用户开箱即用内置规则。 */}
      <Collapse
        className="compare-bar__advanced"
        ghost
        size="small"
        items={[
          {
            key: "advanced",
            label: (
              <span className="compare-bar__advanced-label">
                <SettingOutlined aria-hidden="true" /> 高级选项（规则配置 / 术语库）
              </span>
            ),
            children: (
              <Space wrap size={16}>
                <Space orientation="vertical" size={4}>
                  <label htmlFor="workbench-profile-select" style={PICKER_LABEL_STYLE}>规则配置</label>
                  <Select
                    id="workbench-profile-select"
                    aria-label="选择规则配置"
                    allowClear
                    placeholder="内置平衡配置（推荐）…"
                    style={{ minWidth: 200 }}
                    value={profileFilename}
                    disabled={busy}
                    onOpenChange={(open) => open && loadProfiles()}
                    onChange={(value) => onProfile(value ?? null)}
                    options={profiles.map((item) => ({
                      value: item.filename,
                      label: `${item.name} v${item.version}`,
                    }))}
                  />
                </Space>
                <Space orientation="vertical" size={4}>
                  <label htmlFor="workbench-glossary-select" style={PICKER_LABEL_STYLE}>术语库</label>
                  <Select
                    id="workbench-glossary-select"
                    aria-label="选择术语库"
                    allowClear
                    placeholder="不启用…"
                    style={{ minWidth: 200 }}
                    value={glossaryReference}
                    disabled={busy}
                    onOpenChange={(open) => open && loadGlossaries()}
                    onChange={(value) => onGlossary(value ?? null)}
                    options={glossaries.map((item) => ({
                      value: item.reference,
                      label: `${item.name} (${item.entry_count} 条)`,
                    }))}
                  />
                </Space>
                {/* 打开密码只在受保护文档时填写；权限密码文档无需密码。 */}
                <PasswordField
                  label="源文档打开密码"
                  name="source-document-password"
                  value={sourcePassword}
                  disabled={busy}
                  onChange={onSourcePassword}
                />
                <PasswordField
                  label="目标文档打开密码"
                  name="target-document-password"
                  value={targetPassword}
                  disabled={busy}
                  onChange={onTargetPassword}
                />
              </Space>
            ),
          },
        ]}
      />
    </div>
  )
}
