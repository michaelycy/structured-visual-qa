/** 分阶段验证：Steps 指示进度，逐阶段执行-确认-展开原始数据。 */

import { useState } from "react"
import { Alert, Button, Card, Space, Steps, Typography } from "antd"
import type { StageItem } from "../api"
import { api } from "../services/queryClient"

const STAGES = ["parse", "group", "alignment", "match", "detect", "report"] as const

const STAGE_NAME: Record<string, string> = {
  parse: "解析",
  group: "分组",
  alignment: "页对齐",
  match: "匹配",
  detect: "检测",
  report: "报告",
}

export function StageView({
  source,
  target,
}: {
  source: string
  target: string
}) {
  const [stages, setStages] = useState<StageItem[]>([])
  const [busy, setBusy] = useState(false)
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
    <Space direction="vertical" size={12} style={{ width: "100%" }}>
      <Steps
        size="small"
        current={stages.length}
        items={STAGES.map((key) => ({ title: STAGE_NAME[key] }))}
      />
      <Space>
        <Button
          type="primary"
          loading={busy}
          disabled={!nextStage || !source || !target}
          onClick={() => void runNext()}
        >
          {nextStage ? `执行到「${STAGE_NAME[nextStage]}」` : "全部阶段已完成"}
        </Button>
        {stages.length > 0 && (
          <Button onClick={() => setStages([])}>重新开始</Button>
        )}
      </Space>
      {error && <Alert type="error" showIcon message={error} />}
      {stages.map((item) => (
        <Card
          key={item.stage}
          size="small"
          title={`${STAGE_NAME[item.stage]} · ${item.stage}`}
          extra={
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {item.artifact.split("/").pop()}
            </Typography.Text>
          }
        >
          <Typography.Text>{item.summary}</Typography.Text>
          <pre
            style={{
              marginTop: 8,
              marginBottom: 0,
              maxHeight: 260,
              overflow: "auto",
              fontSize: 12,
            }}
          >
            {JSON.stringify(item.data, null, 2)}
          </pre>
        </Card>
      ))}
      {stages.length === 0 && !error && (
        <Typography.Text type="secondary">
          尚未执行。每个阶段执行后展示摘要，卡片内可查看原始数据产物。
        </Typography.Text>
      )}
    </Space>
  )
}
