/** 报告总览：报告上下文、四项核心指标与交付物导出。 */

import { useState } from "react"
import { Button, Card, Col, message, Progress, Row, Space, Tag, Typography } from "antd"
import {
  CheckCircleFilled,
  DownloadOutlined,
  ExclamationCircleFilled,
  FileExcelOutlined,
  FileTextOutlined,
  WarningFilled,
} from "@ant-design/icons"
import type { QAReport } from "../api"
import { api } from "../services/queryClient"
import { PALETTE, STATUS_META, scoreColor } from "../uiTokens"

const SCORE_FORMATTER = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 })

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
  reviewedCount,
}: {
  report: QAReport
  historyRecordId: string | null
  reviewedCount: number
}) {
  const { summary } = report
  const [exporting, setExporting] = useState<"xlsx" | "html" | null>(null)
  const [messageApi, contextHolder] = message.useMessage()
  const issueTotal = Object.values(summary.issue_counts).reduce((sum, count) => sum + count, 0)
  const problemTotal = summary.problem_total ?? issueTotal
  // 交付风险卡与默认判定一致：High/Critical 归为严重，其余为一般提示。
  const severeTotal = (summary.issue_counts.critical ?? 0) + (summary.issue_counts.high ?? 0)
  const generalTotal = Math.max(issueTotal - severeTotal, 0)
  const reviewedPercent = issueTotal ? Math.round((reviewedCount / issueTotal) * 100) : 100
  const ocr = (report.metadata as Record<string, unknown> | undefined)?.ocr as
    | Record<string, unknown>
    | undefined

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
    <section className="report-overview">
      {contextHolder}
      <div className="report-section-heading">
        <Space wrap size={10}>
          <Typography.Title level={5}>报告概览</Typography.Title>
          <Tag variant="filled" className="report-profile-tag">
            <span translate="no">{report.rule_profile_reference}</span>
          </Tag>
          <Typography.Text type="secondary" className="report-page-summary">
            共 {summary.pages} 页 · {problemTotal} 个问题组 · {issueTotal} 条规则命中 · {summary.passed_pages} 页通过 · {summary.review_pages} 页复核 · {summary.failed_pages} 页失败
          </Typography.Text>
        </Space>
        <Space wrap size={8}>
          <span className="report-sync"><i />报告已同步</span>
          <Button
            size="small"
            icon={<FileExcelOutlined aria-hidden="true" />}
            loading={exporting === "xlsx"}
            disabled={!historyRecordId}
            onClick={() => void doExport("xlsx")}
          >
            XLSX
          </Button>
          <Button
            size="small"
            icon={<FileTextOutlined aria-hidden="true" />}
            loading={exporting === "html"}
            disabled={!historyRecordId}
            onClick={() => void doExport("html")}
          >
            HTML
          </Button>
        </Space>
      </div>

      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} xl={6}>
          <Card className="metric-card metric-card--score" variant="borderless">
            <div className="metric-card__label">
              综合得分
              <Tag
                variant="filled"
                style={{
                  color: STATUS_META[report.status]?.color,
                  background: STATUS_META[report.status]?.background,
                }}
              >
                {STATUS_META[report.status]?.label ?? report.status}
              </Tag>
            </div>
            <div className="metric-card__body">
              <span className="metric-card__value" style={{ color: scoreColor(report.document_score) }}>
                {SCORE_FORMATTER.format(report.document_score)}
              </span>
              <span className="metric-card__unit">/100</span>
            </div>
            <Progress
              percent={report.document_score}
              showInfo={false}
              strokeColor={scoreColor(report.document_score)}
              railColor={PALETTE.border}
              size="small"
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} xl={6}>
          <Card className="metric-card metric-card--critical" variant="borderless">
            <div className="metric-card__label">
              <span><ExclamationCircleFilled aria-hidden="true" /> 严重命中</span>
              <span>Critical / High</span>
            </div>
            <div className="metric-card__body">
              <span className="metric-card__value">{severeTotal}</span>
              <span className="metric-card__unit">个</span>
            </div>
            <span className="metric-card__hint">需优先处理的交付风险</span>
          </Card>
        </Col>
        <Col xs={24} sm={12} xl={6}>
          <Card className="metric-card metric-card--warning" variant="borderless">
            <div className="metric-card__label">
              <span><WarningFilled aria-hidden="true" /> 一般命中</span>
              <span>Medium / Low / Info</span>
            </div>
            <div className="metric-card__body">
              <span className="metric-card__value">{generalTotal}</span>
              <span className="metric-card__unit">个</span>
            </div>
            <span className="metric-card__hint">建议结合页面上下文复核</span>
          </Card>
        </Col>
        <Col xs={24} sm={12} xl={6}>
          <Card className="metric-card metric-card--review" variant="borderless">
            <div className="metric-card__label">
              <span><CheckCircleFilled aria-hidden="true" /> 复核进度</span>
              <span>{reviewedPercent}%</span>
            </div>
            <div className="metric-card__body">
              <span className="metric-card__value">{reviewedCount}</span>
              <span className="metric-card__unit">/ {issueTotal}</span>
            </div>
            <Progress
              percent={reviewedPercent}
              showInfo={false}
              strokeColor={PALETTE.info}
              railColor={PALETTE.infoSoft}
              size="small"
            />
          </Card>
        </Col>
      </Row>

      {(report.metadata as Record<string, unknown> | undefined)?.normalized_from ? (
        <div className="report-normalized-note">
          <DownloadOutlined aria-hidden="true" /> 输入含 Office 文档归一化转换，版面结论已叠加转换容差。
        </div>
      ) : null}
      {ocr ? (
        <div className="report-normalized-note">
          <WarningFilled aria-hidden="true" />
          {ocr.status === "completed"
            ? `图片文字 OCR 已完成：处理 ${String(ocr.processed_count ?? 0)} / ${String(ocr.candidate_count ?? 0)} 个候选区域。`
            : `图片文字 OCR 未完整执行（${String(ocr.error ?? ocr.status ?? "unknown")}），请勿将未检查的图片视为正常。`}
        </div>
      ) : null}
    </section>
  )
}
