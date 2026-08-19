/** 逐页详情：页面选择 + 源/目标渲染图对比 + Issue 列表（含人工判定）。 */

import { useState } from "react"
import {
  Button,
  Col,
  Collapse,
  Empty,
  Progress,
  Row,
  Select,
  Space,
  Tag,
  Typography,
} from "antd"
import type { Issue, QAReport, ReviewDecision } from "../api"

const SEVERITY_COLOR: Record<string, string> = {
  critical: "red",
  high: "volcano",
  medium: "orange",
  low: "green",
  info: "default",
}

const DECISION_LABEL: Record<ReviewDecision, string> = {
  confirmed: "确认问题",
  false_positive: "误报",
  ignored: "忽略",
}

const DECISION_COLOR: Record<ReviewDecision, string> = {
  confirmed: "red",
  false_positive: "green",
  ignored: "default",
}

function pageImage(
  side: "source" | "target",
  page: number,
  rendered: { source: string[]; target: string[] } | undefined,
): string | null {
  // rendered 元素是相对 pages/ 根的完整路径（task-xxx/side/page-0001.png）。
  const name = `page-${String(page).padStart(4, "0")}.png`
  const match = rendered?.[side].find((entry) => entry.endsWith(`/${side}/${name}`))
  return match ? `/api/pages/${match}` : null
}

/** 源/目标渲染图并排对比，目标图叠加 Issue 红框（BBox 为 PDF point）。 */
function PageCompare({
  page,
  issues,
  rendered,
  activeIssueId,
}: {
  page: number
  issues: Issue[]
  rendered?: { source: string[]; target: string[] }
  activeIssueId: string | null
}) {
  const sourceUrl = pageImage("source", page, rendered)
  const targetUrl = pageImage("target", page, rendered)
  // 渲染 dpi=144 即 2px/point；图片加载后由自然宽度反推页面 point 尺寸。
  const [pageWidth, setPageWidth] = useState(0)
  const [pageHeight, setPageHeight] = useState(0)

  if (!sourceUrl && !targetUrl) {
    return (
      <Empty
        description="本页状态为 PASS，未生成渲染图（默认只渲染需复核页面）。"
        image={Empty.PRESENTED_IMAGE_SIMPLE}
      />
    )
  }

  return (
    <Row gutter={12}>
      {sourceUrl && (
        <Col span={12}>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            源文档 · 第 {page} 页
          </Typography.Text>
          <div style={{ marginTop: 4 }}>
            <img
              src={sourceUrl}
              alt={`源文档第 ${page} 页`}
              style={{ width: "100%", border: "1px solid #d9d9d9", borderRadius: 6 }}
            />
          </div>
        </Col>
      )}
      {targetUrl && (
        <Col span={sourceUrl ? 12 : 24}>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            目标文档 · 第 {page} 页（红框为问题位置）
          </Typography.Text>
          <div style={{ marginTop: 4, position: "relative" }}>
            <img
              src={targetUrl}
              alt={`目标文档第 ${page} 页`}
              style={{ width: "100%", border: "1px solid #d9d9d9", borderRadius: 6 }}
              onLoad={(event) => {
                const img = event.currentTarget
                setPageWidth(img.naturalWidth / 2)
                setPageHeight(img.naturalHeight / 2)
              }}
            />
            {pageWidth > 0 &&
              issues
                .filter((issue) => issue.bbox)
                .map((issue) => (
                  <div
                    key={issue.id}
                    style={{
                      position: "absolute",
                      border:
                        issue.id === activeIssueId
                          ? "3px solid #cf1322"
                          : "2px solid rgba(180,35,24,0.75)",
                      background:
                        issue.id === activeIssueId
                          ? "rgba(180,35,24,0.2)"
                          : "rgba(180,35,24,0.08)",
                      left: `${(issue.bbox!.x / pageWidth) * 100}%`,
                      top: `${(issue.bbox!.y / pageHeight) * 100}%`,
                      width: `${(issue.bbox!.width / pageWidth) * 100}%`,
                      height: `${(issue.bbox!.height / pageHeight) * 100}%`,
                      pointerEvents: "none",
                    }}
                  />
                ))}
          </div>
        </Col>
      )}
    </Row>
  )
}

export function PageDetails({
  report,
  rendered,
  taskId,
  decisions,
  onDecide,
}: {
  report: QAReport
  rendered?: { source: string[]; target: string[] }
  taskId: string | null
  decisions: Record<string, ReviewDecision>
  onDecide: (issueId: string, decision: ReviewDecision) => void
}) {
  const problems = report.pages.filter((page) => page.status !== "pass")
  const [selected, setSelected] = useState<number | null>(
    problems[0]?.page ?? report.pages[0]?.page ?? null,
  )
  const [activeIssueId, setActiveIssueId] = useState<string | null>(null)
  const page = report.pages.find((item) => item.page === selected)
  const totalIssues = report.pages.reduce((sum, p) => sum + p.issues.length, 0)
  const reviewed = Object.keys(decisions).length

  return (
    <Space direction="vertical" size={12} style={{ width: "100%" }}>
      <Space wrap>
        <Select
          style={{ minWidth: 220 }}
          value={selected}
          onChange={(value) => {
            setSelected(value)
            setActiveIssueId(null)
          }}
          options={report.pages.map((item) => ({
            value: item.page,
            label: `第 ${item.page} 页 · ${item.score.toFixed(0)} 分 · ${item.status}`,
          }))}
          showSearch
          optionFilterProp="label"
        />
        {taskId && (
          <Progress
            percent={totalIssues ? Math.round((reviewed / totalIssues) * 100) : 100}
            size="small"
            style={{ width: 180 }}
            format={() => `复核 ${reviewed}/${totalIssues}`}
          />
        )}
      </Space>

      {page ? (
        <>
          <PageCompare
            page={page.page}
            issues={page.issues}
            rendered={rendered}
            activeIssueId={activeIssueId}
          />
          {page.issues.length ? (
            <Collapse
              size="small"
              activeKey={activeIssueId ?? undefined}
              onChange={(keys) =>
                setActiveIssueId(
                  Array.isArray(keys) ? keys[0] ?? null : keys ?? null,
                )
              }
              items={page.issues.map((issue) => ({
                key: issue.id,
                label: (
                  <Space wrap size={8}>
                    <Tag color={SEVERITY_COLOR[issue.severity]}>
                      {issue.severity}
                    </Tag>
                    <Typography.Text code style={{ fontSize: 12 }}>
                      {issue.type}
                    </Typography.Text>
                    <span>{issue.description}</span>
                    {decisions[issue.id] && (
                      <Tag color={DECISION_COLOR[decisions[issue.id]]}>
                        {DECISION_LABEL[decisions[issue.id]]}
                      </Tag>
                    )}
                  </Space>
                ),
                children: (
                  <Space direction="vertical" size={8} style={{ width: "100%" }}>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      指标 {JSON.stringify(issue.metrics)}
                    </Typography.Text>
                    <Space onClick={(e) => e.stopPropagation()}>
                      {(Object.keys(DECISION_LABEL) as ReviewDecision[]).map(
                        (key) => (
                          <Button
                            key={key}
                            size="small"
                            type={
                              decisions[issue.id] === key ? "primary" : "default"
                            }
                            onClick={() => {
                              setActiveIssueId(issue.id)
                              onDecide(issue.id, key)
                            }}
                          >
                            {DECISION_LABEL[key]}
                          </Button>
                        ),
                      )}
                    </Space>
                  </Space>
                ),
              }))}
            />
          ) : (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="本页没有发现问题。"
            />
          )}
        </>
      ) : (
        <Empty
          description="选择页面查看详情。"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      )}
    </Space>
  )
}
