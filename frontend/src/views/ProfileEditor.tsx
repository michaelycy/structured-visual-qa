/** 规则配置编辑器：antd Form，服务端 Pydantic 校验兜底。 */

import { useEffect, useState } from "react"
import { Alert, Button, Card, Col, Collapse, Form, Input, InputNumber, Row, Space, message } from "antd"
import type { RuleProfile } from "../api"
import { api } from "../services/queryClient"

export interface ProfileEditorProps {
  /** 外部初始配置（规则管理页加载的已有 Profile）；缺省用内置默认值。 */
  initial?: RuleProfile
  /** 保存成功回调，参数为版本引用（如 translation-balanced@1）。 */
  onSaved?: (reference: string) => void
}

type ProfileForm = {
  name: string
  profile_id: string
  version: number
  "matching.minimum_score": number
  "matching.merged_text_coverage_ratio": number
  "alignment.max_shift": number
  "alignment.skip_penalty": number
  "detectors.thresholds.shifted_ratio": number
  "detectors.thresholds.severely_shifted_ratio": number
  "detectors.thresholds.font_shrink_ratio": number
  "detectors.thresholds.overlap_ratio": number
  "scoring.pass_score": number
  "scoring.fail_score": number
}

/** 嵌套路径取值。 */
function get(obj: unknown, path: string): unknown {
  return path.split(".").reduce<unknown>((node, key) => (node as Record<string, unknown>)?.[key], obj)
}

export function ProfileEditor({ initial, onSaved }: ProfileEditorProps) {
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
      profile_id: String(profile.profile_id ?? ""),
      version: Number(profile.version ?? 1),
      "matching.minimum_score": Number(get(profile, "matching.minimum_score") ?? 0),
      "matching.merged_text_coverage_ratio": Number(get(profile, "matching.merged_text_coverage_ratio") ?? 0),
      "alignment.max_shift": Number(get(profile, "alignment.max_shift") ?? 3),
      "alignment.skip_penalty": Number(get(profile, "alignment.skip_penalty") ?? 0.5),
      "detectors.thresholds.shifted_ratio": Number(get(profile, "detectors.thresholds.shifted_ratio") ?? 0),
      "detectors.thresholds.severely_shifted_ratio": Number(get(profile, "detectors.thresholds.severely_shifted_ratio") ?? 0),
      "detectors.thresholds.font_shrink_ratio": Number(get(profile, "detectors.thresholds.font_shrink_ratio") ?? 0),
      "detectors.thresholds.overlap_ratio": Number(get(profile, "detectors.thresholds.overlap_ratio") ?? 0),
      "scoring.pass_score": Number(get(profile, "scoring.pass_score") ?? 90),
      "scoring.fail_score": Number(get(profile, "scoring.fail_score") ?? 75),
    })
  }, [profile, form])

  if (!profile) return <span>{error || "加载默认配置…"}</span>

  const save = async (values: ProfileForm) => {
    setBusy(true)
    setError("")
    try {
      const next = structuredClone(profile)
      next.name = values.name
      next.profile_id = values.profile_id
      next.version = values.version
      for (const [field, value] of Object.entries(values)) {
        if (!field.includes(".")) continue
        const keys = field.split(".")
        let node = next as unknown as Record<string, unknown>
        for (const key of keys.slice(0, -1)) {
          node = node[key] as Record<string, unknown>
        }
        node[keys[keys.length - 1]] = value
      }
      const saved = await api.saveProfile(next)
      messageApi.success(`已保存 ${saved.reference}`)
      onSaved?.(saved.reference)
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setBusy(false)
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
    <Col xs={12} md={6}>
      <Form.Item label={label} name={name} tooltip={tooltip} style={{ marginBottom: 8 }}>
        <InputNumber style={{ width: "100%" }} step={step} min={min} max={max} />
      </Form.Item>
    </Col>
  )

  return (
    <Form form={form} layout="vertical" onFinish={(values) => void save(values)}>
      {contextHolder}
      {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} />}

      <Row gutter={12}>
        <Col xs={24} md={12}>
          <Form.Item label="配置名称" name="name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
        </Col>
      </Row>
      {/* 标识与版本是系统内部概念（保存文件名由它们组成），默认收起。 */}
      <Collapse
        size="small"
        style={{ marginBottom: 12 }}
        items={[
          {
            key: "identity",
            label: (
              <span style={{ fontSize: 13 }}>高级（标识与版本）</span>
            ),
            children: (
              <Row gutter={12}>
                <Col xs={12} md={12}>
                  <Form.Item
                    label="标识（英文，用于引用）"
                    name="profile_id"
                    rules={[{ required: true }]}
                    style={{ marginBottom: 8 }}
                  >
                    <Input />
                  </Form.Item>
                </Col>
                <Col xs={12} md={8}>
                  <Form.Item label="版本号" name="version" style={{ marginBottom: 8 }}>
                    <InputNumber style={{ width: "100%" }} step={1} min={1} />
                  </Form.Item>
                </Col>
              </Row>
            ),
          },
        ]}
      />

      <Card size="small" title="匹配设置" style={{ marginBottom: 12 }}>
        <Row gutter={12}>
          {numberField("最低匹配分", "matching.minimum_score", "相似度低于该值的区域对不会配对；调高更严格", 0.05, 0, 1)}
          {numberField("合并文本覆盖率", "matching.merged_text_coverage_ratio", "两段文本需重叠的比例，用于判定属于同一区域", 0.05, 0, 1)}
        </Row>
      </Card>

      <Card size="small" title="页对齐" style={{ marginBottom: 12 }}>
        <Row gutter={12}>
          {numberField("最大页码偏移", "alignment.max_shift", "允许原文与译文相差几页（应对目录、版权页等增删）", 1, 0, 50)}
          {numberField("跳页代价", "alignment.skip_penalty", "越大越倾向于不跳过任何一页", 0.1, 0, 10)}
        </Row>
      </Card>

      <Card size="small" title="检测阈值" style={{ marginBottom: 12 }}>
        <Row gutter={12}>
          {numberField("偏移阈值", "detectors.thresholds.shifted_ratio", "位置偏移超过该比例判为「位置偏移」", 0.01, 0, 1)}
          {numberField("严重偏移阈值", "detectors.thresholds.severely_shifted_ratio", "超过该比例判为严重偏移（严重度更高）", 0.01, 0, 1)}
          {numberField("字号缩小阈值", "detectors.thresholds.font_shrink_ratio", "负数：如 -0.15 表示字号缩小超过 15% 判为问题", 0.01, -1, 0)}
          {numberField("重叠比例阈值", "detectors.thresholds.overlap_ratio", "文字互相压盖超过该比例判为「文字重叠」", 0.01, 0, 1)}
        </Row>
      </Card>

      <Card size="small" title="评分线" style={{ marginBottom: 12 }}>
        <Row gutter={12}>
          {numberField("通过分数线", "scoring.pass_score", "文档得分不低于此值且无高严重度问题才算「通过」", 1, 0, 100)}
          {numberField("未通过分数线", "scoring.fail_score", "低于此值判为「未通过」；两者之间为「需复核」", 1, 0, 100)}
        </Row>
      </Card>

      <Space>
        <Button type="primary" htmlType="submit" loading={busy}>
          校验并保存
        </Button>
        <Button onClick={() => api.defaultProfile().then(setProfile)}>
          重置为默认
        </Button>
      </Space>
    </Form>
  )
}
