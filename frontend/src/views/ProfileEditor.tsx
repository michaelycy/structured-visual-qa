/** 规则配置编辑器：按业务规则分组，服务端 Pydantic 校验兜底。 */

import { useEffect, useId, useState } from "react"
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Form,
  Input,
  InputNumber,
  Popconfirm,
  Row,
  Select,
  Space,
  Switch,
  Tag,
  Typography,
  message,
} from "antd"
import type { RuleProfile } from "../api"
import { api } from "../services/queryClient"

export interface ProfileEditorProps {
  /** 外部初始配置；缺省时使用内置默认值。 */
  initial?: RuleProfile
  /** 表单被用户修改时回调（用于关闭前未保存拦截）。 */
  onDirtyChange?: (dirty: boolean) => void
  /** 保存成功回调，参数为版本引用。 */
  onSaved?: (reference: string) => void
}

type RasterizedPolicy = "disabled" | "info" | "low" | "medium" | "high" | "critical"

type ProfileForm = {
  name: string
  description: string
  profile_id: string
  version: number
  "matching.minimum_score": number
  "matching.merged_text_coverage_ratio": number
  "alignment.max_shift": number
  "alignment.skip_penalty": number
  "detectors.enabled.missing_element": boolean
  "detectors.enabled.region_shifted": boolean
  "detectors.enabled.font_shrink": boolean
  "detectors.enabled.content_out_of_page": boolean
  "detectors.enabled.overlap": boolean
  "detectors.enabled.number_mismatch": boolean
  "detectors.enabled.untranslated_text": boolean
  "detectors.enabled.region_resized": boolean
  "detectors.enabled.text_fragmented": boolean
  "detectors.enabled.font_grow": boolean
  "detectors.enabled.invisible_text": boolean
  "detectors.enabled.text_alignment_changed": boolean
  text_rasterized_policy: RasterizedPolicy
  "detectors.thresholds.shifted_ratio": number
  "detectors.thresholds.severely_shifted_ratio": number
  "detectors.thresholds.font_shrink_ratio": number
  "detectors.thresholds.overlap_ratio": number
  "detectors.thresholds.region_resize_ratio": number
  "detectors.thresholds.font_grow_ratio": number
  "detectors.thresholds.untranslated_ratio": number
  "detectors.thresholds.untranslated_min_letters": number
  "detectors.thresholds.rasterized_image_overlap_ratio": number
  "detectors.thresholds.conversion_noise_ratio": number
  "scoring.pass_score": number
  "scoring.fail_score": number
}

interface RuleToggleProps {
  name: keyof ProfileForm
  label: string
  description: string
}

/** 嵌套路径取值。 */
function get(obj: unknown, path: string): unknown {
  return path.split(".").reduce<unknown>((node, key) => (node as Record<string, unknown>)?.[key], obj)
}

/** 嵌套路径赋值。 */
function set(obj: Record<string, unknown>, path: string, value: unknown) {
  const keys = path.split(".")
  let node = obj
  for (const key of keys.slice(0, -1)) {
    node = node[key] as Record<string, unknown>
  }
  node[keys[keys.length - 1]] = value
}

/** 将栅格化开关与严重度组合为面向业务的处理策略。 */
function rasterizedPolicy(profile: RuleProfile): RasterizedPolicy {
  if (!get(profile, "detectors.enabled.text_rasterized")) return "disabled"
  const severity = get(profile, "detectors.severity_overrides.text_rasterized")
  if (["info", "low", "medium", "high", "critical"].includes(String(severity))) {
    return severity as RasterizedPolicy
  }
  return "high"
}

/** 带解释的检测规则开关：说明文字整体可点（label 关联 Switch）。 */
function RuleToggle(props: RuleToggleProps) {
  const { name, label, description } = props
  const switchId = useId()
  return (
    <div className="rule-editor__rule">
      <label className="rule-editor__rule-content" htmlFor={switchId}>
        <Typography.Text strong>{label}</Typography.Text>
        <Typography.Text type="secondary">{description}</Typography.Text>
      </label>
      <Form.Item name={name} valuePropName="checked" noStyle>
        <Switch id={switchId} aria-label={label} />
      </Form.Item>
    </div>
  )
}

/** 编辑完整规则配置；纯展示单元不承担请求和版本决策。 */
export function ProfileEditor(props: ProfileEditorProps) {
  const { initial, onDirtyChange, onSaved } = props
  const [form] = Form.useForm<ProfileForm>()
  const [profile, setProfile] = useState<RuleProfile | null>(initial ?? null)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const [messageApi, contextHolder] = message.useMessage()

  useEffect(() => {
    if (initial) {
      setProfile(initial)
      return
    }
    api.defaultProfile().then(setProfile).catch(() => setError("无法加载默认配置"))
  }, [initial])

  useEffect(() => {
    if (!profile) return
    form.setFieldsValue({
      name: String(profile.name ?? ""),
      description: String(profile.description ?? ""),
      profile_id: String(profile.profile_id ?? ""),
      version: Number(profile.version ?? 1),
      "matching.minimum_score": Number(get(profile, "matching.minimum_score") ?? 0.45),
      "matching.merged_text_coverage_ratio": Number(
        get(profile, "matching.merged_text_coverage_ratio") ?? 0.4,
      ),
      "alignment.max_shift": Number(get(profile, "alignment.max_shift") ?? 3),
      "alignment.skip_penalty": Number(get(profile, "alignment.skip_penalty") ?? 0.5),
      "detectors.enabled.missing_element": Boolean(get(profile, "detectors.enabled.missing_element")),
      "detectors.enabled.region_shifted": Boolean(get(profile, "detectors.enabled.region_shifted")),
      "detectors.enabled.font_shrink": Boolean(get(profile, "detectors.enabled.font_shrink")),
      "detectors.enabled.content_out_of_page": Boolean(
        get(profile, "detectors.enabled.content_out_of_page"),
      ),
      "detectors.enabled.overlap": Boolean(get(profile, "detectors.enabled.overlap")),
      "detectors.enabled.number_mismatch": Boolean(get(profile, "detectors.enabled.number_mismatch")),
      "detectors.enabled.untranslated_text": Boolean(get(profile, "detectors.enabled.untranslated_text")),
      "detectors.enabled.region_resized": Boolean(get(profile, "detectors.enabled.region_resized")),
      "detectors.enabled.text_fragmented": Boolean(get(profile, "detectors.enabled.text_fragmented")),
      "detectors.enabled.font_grow": Boolean(get(profile, "detectors.enabled.font_grow")),
      "detectors.enabled.invisible_text": Boolean(get(profile, "detectors.enabled.invisible_text")),
      "detectors.enabled.text_alignment_changed": Boolean(
        get(profile, "detectors.enabled.text_alignment_changed"),
      ),
      text_rasterized_policy: rasterizedPolicy(profile),
      "detectors.thresholds.shifted_ratio": Number(get(profile, "detectors.thresholds.shifted_ratio") ?? 0.05),
      "detectors.thresholds.severely_shifted_ratio": Number(
        get(profile, "detectors.thresholds.severely_shifted_ratio") ?? 0.15,
      ),
      "detectors.thresholds.font_shrink_ratio": Number(
        get(profile, "detectors.thresholds.font_shrink_ratio") ?? -0.2,
      ),
      "detectors.thresholds.overlap_ratio": Number(get(profile, "detectors.thresholds.overlap_ratio") ?? 0.05),
      "detectors.thresholds.region_resize_ratio": Number(
        get(profile, "detectors.thresholds.region_resize_ratio") ?? 0.5,
      ),
      "detectors.thresholds.font_grow_ratio": Number(get(profile, "detectors.thresholds.font_grow_ratio") ?? 0.25),
      "detectors.thresholds.untranslated_ratio": Number(
        get(profile, "detectors.thresholds.untranslated_ratio") ?? 0.7,
      ),
      "detectors.thresholds.untranslated_min_letters": Number(
        get(profile, "detectors.thresholds.untranslated_min_letters") ?? 8,
      ),
      "detectors.thresholds.rasterized_image_overlap_ratio": Number(
        get(profile, "detectors.thresholds.rasterized_image_overlap_ratio") ?? 0.8,
      ),
      "detectors.thresholds.conversion_noise_ratio": Number(
        get(profile, "detectors.thresholds.conversion_noise_ratio") ?? 0.03,
      ),
      "scoring.pass_score": Number(get(profile, "scoring.pass_score") ?? 90),
      "scoring.fail_score": Number(get(profile, "scoring.fail_score") ?? 75),
    })
  }, [profile, form])

  if (!profile) {
    return error ? (
      <Alert type="error" showIcon message={error} />
    ) : (
      <span role="status">加载默认配置…</span>
    )
  }

  const save = async (values: ProfileForm) => {
    setBusy(true)
    setError("")
    try {
      const next = structuredClone(profile)
      next.name = values.name
      next.description = values.description
      next.profile_id = values.profile_id
      next.version = values.version
      next.status = "draft"
      for (const [field, value] of Object.entries(values)) {
        if (!field.includes(".") || field === "text_rasterized_policy") continue
        set(next, field, value)
      }
      const policy = values.text_rasterized_policy
      set(next, "detectors.enabled.text_rasterized", policy !== "disabled")
      if (policy !== "disabled") {
        set(next, "detectors.severity_overrides.text_rasterized", policy)
      }
      const saved = await api.saveProfile(next)
      messageApi.success(`已保存草稿 ${saved.reference}`)
      onDirtyChange?.(false)
      onSaved?.(saved.reference)
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setBusy(false)
    }
  }

  const resetToDefault = async () => {
    try {
      const defaults = await api.defaultProfile()
      setProfile({
        ...defaults,
        profile_id: profile.profile_id,
        name: profile.name,
        version: profile.version,
        status: "draft",
        description: profile.description,
      })
    } catch {
      setError("无法加载默认配置")
    }
  }

  const numberField = (
    label: string,
    name: keyof ProfileForm,
    tooltip?: string,
    step = 0.05,
    min?: number,
    max?: number,
  ) => (
    <Col xs={24} sm={12} lg={6}>
      <Form.Item label={label} name={name} tooltip={tooltip}>
        <InputNumber
          className="rule-editor__number"
          name={String(name)}
          autoComplete="off"
          step={step}
          min={min}
          max={max}
        />
      </Form.Item>
    </Col>
  )

  return (
    <Form
      className="rule-editor"
      form={form}
      layout="vertical"
      scrollToFirstError
      onChange={() => onDirtyChange?.(true)}
      onFinish={(values) => void save(values)}
    >
      {contextHolder}
      {error && <Alert type="error" showIcon message={error} />}

      <Card size="small" title="配置说明">
        <Row className="rule-editor__form-grid" gutter={16}>
          <Col xs={24} md={10}>
            <Form.Item label="配置名称" name="name" rules={[{ required: true }]}>
              <Input name="name" autoComplete="off" />
            </Form.Item>
          </Col>
          <Col xs={24} md={14}>
            <Form.Item label="适用说明" name="description">
              <Input name="description" autoComplete="off" />
            </Form.Item>
          </Col>
        </Row>
      </Card>

      <Card size="small" title="内容完整性与翻译内容">
        <RuleToggle
          name="detectors.enabled.missing_element"
          label="内容完整性"
          description="检查原文内容或图片在目标文档中缺失，以及目标文档新增内容。"
        />
        <RuleToggle
          name="detectors.enabled.number_mismatch"
          label="数字一致性"
          description="检查数字、日期、百分比等关键信息是否发生变化。"
        />
        <RuleToggle
          name="detectors.enabled.untranslated_text"
          label="疑似未翻译"
          description="检查目标文字中是否仍大量保留原语言内容。"
        />
      </Card>

      <Card size="small" title="版面与文字显示">
        <RuleToggle name="detectors.enabled.region_shifted" label="位置变化" description="检查内容位置是否明显偏离原版。" />
        <RuleToggle name="detectors.enabled.region_resized" label="区域尺寸变化" description="检查内容区域是否被异常拉伸、压缩、合并或拆分。" />
        <RuleToggle name="detectors.enabled.font_shrink" label="字号明显缩小" description="检查目标文字是否因排版空间不足而过度缩小。" />
        <RuleToggle name="detectors.enabled.font_grow" label="字号明显放大" description="检查目标文字是否异常放大并引发换行或溢出风险。" />
        <RuleToggle name="detectors.enabled.text_alignment_changed" label="段落对齐变化" description="检查左对齐、右对齐或居中方式是否改变。" />
        <RuleToggle name="detectors.enabled.text_fragmented" label="文字异常拆散" description="检查文字是否被拆成窄列、单字或单字母碎片。" />
        <RuleToggle name="detectors.enabled.content_out_of_page" label="内容超出页面" description="检查文字或图片是否超出页面可见范围。" />
        <RuleToggle name="detectors.enabled.overlap" label="内容遮挡" description="检查文字之间、文字与图片之间是否出现异常遮挡。" />
        <RuleToggle name="detectors.enabled.invisible_text" label="文字不可见" description="检查文字是否因透明或与背景同色而无法看到。" />
      </Card>

      <Card size="small" title="文档结构策略">
        <div className="rule-editor__policy">
          <div className="rule-editor__rule-content">
            <Typography.Text strong>可见文字变成图片</Typography.Text>
            <Typography.Text type="secondary">
              原文可编辑、可检索的文字在目标文档中变成图片；选择是否报告及风险等级。
            </Typography.Text>
          </div>
          <Form.Item name="text_rasterized_policy" noStyle>
            <Select
              className="rule-editor__policy-select"
              aria-label="可见文字变成图片处理策略"
              options={[
                { value: "disabled", label: "不报告" },
                { value: "info", label: "仅提示" },
                { value: "low", label: "低风险" },
                { value: "medium", label: "一般问题" },
                { value: "high", label: "高风险" },
                { value: "critical", label: "严重问题" },
              ]}
            />
          </Form.Item>
        </div>
        <div className="rule-editor__policy">
          <div className="rule-editor__rule-content">
            <Typography.Text strong>目标文字全部转为图形</Typography.Text>
            <Typography.Text type="secondary">
              系统必须识别该结构，避免把无法直接读取的内容误报为大量漏译或缺失。
            </Typography.Text>
          </div>
          <Tag color="blue">系统保护 · 始终启用</Tag>
        </div>
      </Card>

      <Card size="small" title="常用判断阈值">
        <Row className="rule-editor__form-grid" gutter={16}>
          {numberField("位置变化比例", "detectors.thresholds.shifted_ratio", undefined, 0.01, 0, 1)}
          {numberField("严重位置变化比例", "detectors.thresholds.severely_shifted_ratio", undefined, 0.01, 0, 1)}
          {numberField("字号缩小比例", "detectors.thresholds.font_shrink_ratio", "负数，如 -0.2 表示缩小超过 20%", 0.01, -1, 0)}
          {numberField("内容遮挡比例", "detectors.thresholds.overlap_ratio", undefined, 0.01, 0, 1)}
          {numberField("区域尺寸变化比例", "detectors.thresholds.region_resize_ratio", undefined, 0.05, 0, 1)}
          {numberField("字号放大比例", "detectors.thresholds.font_grow_ratio", undefined, 0.05, 0, 2)}
          {numberField("未翻译文字比例", "detectors.thresholds.untranslated_ratio", undefined, 0.05, 0, 1)}
          {numberField("未翻译最少字母数", "detectors.thresholds.untranslated_min_letters", undefined, 1, 1, 100)}
        </Row>
      </Card>

      <Card size="small" title="结果判定">
        <Row className="rule-editor__form-grid" gutter={16}>
          {numberField("通过分数线", "scoring.pass_score", "达到此分数且无阻断问题时判为通过", 1, 0, 100)}
          {numberField("未通过分数线", "scoring.fail_score", "低于此分数时判为未通过", 1, 0, 100)}
        </Row>
      </Card>

      <Collapse
        className="rule-editor__expert"
        items={[
          {
            key: "expert",
            label: "专家设置",
            children: (
              <Row className="rule-editor__form-grid" gutter={16}>
                {numberField("最低匹配分", "matching.minimum_score", undefined, 0.05, 0, 1)}
                {numberField("合并文本覆盖率", "matching.merged_text_coverage_ratio", undefined, 0.05, 0, 1)}
                {numberField("最大页码偏移", "alignment.max_shift", undefined, 1, 0, 50)}
                {numberField("跳页代价", "alignment.skip_penalty", undefined, 0.1, 0, 10)}
                {numberField("文字图片重叠比例", "detectors.thresholds.rasterized_image_overlap_ratio", undefined, 0.05, 0, 1)}
                {numberField("格式转换噪声容差", "detectors.thresholds.conversion_noise_ratio", undefined, 0.01, 0, 0.2)}
              </Row>
            ),
          },
          {
            key: "identity",
            label: "标识与版本",
            children: (
              <Row className="rule-editor__form-grid" gutter={16}>
                <Col xs={24} md={12}>
                  <Form.Item label="配置标识" name="profile_id" rules={[{ required: true }]}>
                    <Input name="profile_id" autoComplete="off" disabled />
                  </Form.Item>
                </Col>
                <Col xs={24} md={6}>
                  <Form.Item label="版本号" name="version">
                    <InputNumber
                      className="rule-editor__number"
                      name="version"
                      autoComplete="off"
                      step={1}
                      min={1}
                      disabled
                    />
                  </Form.Item>
                </Col>
              </Row>
            ),
          },
        ]}
      />

      <Space className="rule-editor__actions">
        <Button type="primary" htmlType="submit" loading={busy}>
          保存草稿
        </Button>
        <Popconfirm
          title="重置为默认配置？"
          description="当前表单中所有未保存的修改都会被内置平衡配置覆盖。"
          okText="重置"
          okButtonProps={{ danger: true }}
          cancelText="取消"
          onConfirm={() => void resetToDefault()}
        >
          <Button>重置为默认</Button>
        </Popconfirm>
      </Space>
    </Form>
  )
}
