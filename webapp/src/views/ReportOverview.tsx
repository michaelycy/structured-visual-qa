/** 报告总览：antd Statistic + 严重度 Tag 列表 + 交付物导出。 */

import { useState } from "react"
import { Button, Card, Col, message, Row, Space, Statistic, Tag } from "antd"
import { FileExcelOutlined, FileTextOutlined } from "@ant-design/icons"
import { api, type QAReport } from "../api"
import { SEVERITY_META, SEVERITY_ORDER, STATUS_META, scoreColor } from "../uiTokens"

/** 触发浏览器下载导出产物。 */
function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

export function ReportOverview({
  report,
  historyRecordId,
}: {
  report: QAReport
  historyRecordId: string | null
}) {
  const { summary } = report
  const [exporting, setExporting] = useState<"xlsx" | "html" | null>(null)
  const [messageApi, contextHolder] = message.useMessage()

  const doExport = async (format: "xlsx" | "html") => {
    if (!historyRecordId) {
      messageApi.warning("当前报告来自历史回看之前的会话，无导出锚点")
      return
    }
    setExporting(format)
    try {
      const blob = await api.exportReport(historyRecordId, format)
      download(blob, `${historyRecordId}.${format}`)
      messageApi.success(`${format.toUpperCase()} 已导出`)
    } catch (exc) {
      messageApi.error(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setExporting(null)
    }
  }

  return (
    <div>
      {contextHolder}
      <Row gutter={[12, 12]}>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic
              title="文档状态"
              value={STATUS_META[report.status]?.label ?? report.status}
              valueStyle={{
                color: STATUS_META[report.status]?.color,
              }}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic
              title="文档分数"
              value={report.document_score}
              precision={2}
              valueStyle={{ fontWeight: 600, color: scoreColor(report.document_score) }}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic title="页面" value={summary.pages} suffix="页" />
            <span style={{ fontSize: 12, color: "rgba(0,0,0,0.45)" }}>
              {summary.passed_pages} 通过 / {summary.review_pages} 复核 /{" "}
              {summary.failed_pages} 失败
            </span>
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic
              title="问题总数"
              value={Object.values(summary.issue_counts).reduce(
                (a, b) => a + b,
                0,
              )}
            />
          </Card>
        </Col>
      </Row>

      <Card
        size="small"
        title="问题严重度分布"
        style={{ marginTop: 12 }}
        extra={
          <Space>
            <Tag>{report.rule_profile_reference}</Tag>
            <Button
              size="small"
              icon={<FileExcelOutlined />}
              loading={exporting === "xlsx"}
              disabled={!historyRecordId}
              onClick={() => void doExport("xlsx")}
            >
              导出 XLSX
            </Button>
            <Button
              size="small"
              icon={<FileTextOutlined />}
              loading={exporting === "html"}
              disabled={!historyRecordId}
              onClick={() => void doExport("html")}
            >
              导出 HTML
            </Button>
          </Space>
        }
      >
        {Object.entries(summary.issue_counts)
          .filter(([, count]) => count > 0)
          .sort((a, b) => (SEVERITY_ORDER[a[0]] ?? 99) - (SEVERITY_ORDER[b[0]] ?? 99))
          .map(([severity, count]) => (
            <Tag
              key={severity}
              color={SEVERITY_META[severity]?.color}
              style={{ fontSize: 13, padding: "2px 10px" }}
            >
              {SEVERITY_META[severity]?.label ?? severity} × {count}
            </Tag>
          ))}
        {Object.values(summary.issue_counts).every((c) => c === 0) && (
          <span style={{ color: "rgba(0,0,0,0.45)" }}>没有发现任何问题。</span>
        )}
      </Card>

      {(report.metadata as Record<string, unknown> | undefined)
        ?.normalized_from ? (
        <Card size="small" style={{ marginTop: 12 }}>
          <Tag color="gold">归一化转换</Tag>
          <span style={{ fontSize: 13 }}>
            输入含 Office 文档转换（
            {JSON.stringify(
              (report.metadata as Record<string, unknown>).normalized_from,
            )}
            ），版面结论已叠加转换容差。
          </span>
        </Card>
      ) : null}
    </div>
  )
}
