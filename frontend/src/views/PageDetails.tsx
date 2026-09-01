/** 逐页详情：页面选择 + 源/目标渲染图对比 + Issue 列表（含人工判定与筛选）。 */

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react"
import {
  DownOutlined,
  PictureOutlined,
  RightOutlined,
  ZoomInOutlined,
  ZoomOutOutlined,
} from "@ant-design/icons"
import {
  Button,
  Col,
  Empty,
  Input,
  Modal,
  Row,
  Segmented,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
} from "antd"
import type { Issue, QAReport, ReviewDecision } from "../api"
import { DECISION_META, ISSUE_TYPE_META, PALETTE, SEVERITY_META, STATUS_META } from "../uiTokens"
import { AiBriefModal } from "./AiBriefModal"
import {
  isDevModeEnabled,
  setDevModeEnabled,
  type BriefIssue,
} from "../features/workbench/model/ai-brief"

const INTEGER_FORMATTER = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 })
const EMPTY_SEVERITIES: string[] = []
const EMPTY_ISSUE_TYPES: string[] = []
const MIN_PAGE_ZOOM = 1
const MAX_PAGE_ZOOM = 2.5
const PAGE_ZOOM_STEP = 0.25
const PDF_RENDER_SCALE = 2
const IMAGE_PREVIEW_PADDING_PT = 12

/** 将逗号、中文逗号或空白分隔的问题编号输入规范化为模糊查询词。 */
function parseIssueNumberQueries(value: string): string[] {
  return [...new Set(
    value
      .split(/[,，\s]+/)
      .map((item) => item.trim().replace(/^#+/, ""))
      .filter(Boolean),
  )]
}

/** 归一化原文文本与查询词：小写化并折叠全部空白（PDF 提取文本常含换行与多余空格）。 */
function normalizeSourceText(value: string): string {
  return value.toLowerCase().replace(/\s+/g, " ").trim()
}

/** 取 Issue 的原文证据文本；重叠类 Issue 有两段原文区域（原文区域 2 = source_other_text），一并纳入匹配。 */
function issueSourceTexts(issue: Issue): string[] {
  const metrics = issue.metrics ?? {}
  const texts: string[] = []
  if (typeof metrics.source_text === "string") texts.push(metrics.source_text)
  if (typeof metrics.source_other_text === "string") texts.push(metrics.source_other_text)
  return texts
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

/** 序号角标：图上红框左上角与 Issue 列表行首共用，保证两侧对应。 */
export function IssueBadge({ index, active }: { index: number; active?: boolean }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: 18,
        height: 18,
        borderRadius: 9,
        background: active ? PALETTE.critical : PALETTE.surface,
        color: active ? PALETTE.surface : PALETTE.critical,
        border: `1.5px solid ${PALETTE.critical}`,
        fontSize: 11,
        fontWeight: 600,
        lineHeight: 1,
        flexShrink: 0,
      }}
    >
      {index + 1}
    </span>
  )
}

/** 源/目标渲染图并排对比，目标图叠加 Issue 红框（BBox 为 PDF point）。 */

/** 缺失类问题没有译文区域：bbox 即源文档坐标，对应框画在源图上。 */
const MISSING_ISSUE_TYPES = new Set(["missing_element", "missing_image"])

function PageCompare({
  page,
  issues,
  rendered,
  activeIssueId,
  issueNumberById,
}: {
  page: number
  issues: Issue[]
  rendered?: { source: string[]; target: string[] }
  activeIssueId: string | null
  issueNumberById: ReadonlyMap<string, number>
}) {
  const sourceUrl = pageImage("source", page, rendered)
  const targetUrl = pageImage("target", page, rendered)
  // 渲染 dpi=144 即 2px/point；图片加载后由自然宽度反推页面 point 尺寸。
  const [pageWidth, setPageWidth] = useState(0)
  const [pageHeight, setPageHeight] = useState(0)
  const [zoom, setZoom] = useState(MIN_PAGE_ZOOM)
  // 两侧按可滚动距离比例联动；帧级来源锁阻止程序写入再次触发反向同步。
  const sourceCanvasRef = useRef<HTMLDivElement>(null)
  const targetCanvasRef = useRef<HTMLDivElement>(null)
  const scrollOriginRef = useRef<"source" | "target" | null>(null)
  const scrollFrameRef = useRef<number | null>(null)
  const pendingZoomCentersRef = useRef<{
    source: { x: number; y: number } | null
    target: { x: number; y: number } | null
  } | null>(null)
  const restoringZoomRef = useRef(false)
  // 同一目标区域的多个 Issue（同 bbox，如偏移+字号变化）共用一个红框，
  // 角标横排——避免同位置叠出多个框和重叠角标（与列表分组同键）。
  const bboxGroups = useMemo(
    () => groupIssuesByBbox(issues.filter((issue) => issue.bbox), issueNumberById),
    [issueNumberById, issues],
  )
  // 源侧对应框：优先取配对原文区域坐标（metrics.source_bbox）；缺失类
  // 问题没有译文区域，其 bbox 本身就是源侧坐标。源图与目标图共用同一
  // 套序号角标，审阅时两侧同号即为同一问题的原文/译文位置。
  const sourceBboxGroups = useMemo(() => {
    const withSourceBox = issues.flatMap((issue) => {
      const fromMetrics = (issue.metrics ?? {}).source_bbox as
        | Issue["bbox"]
        | undefined
      const box =
        fromMetrics ??
        (MISSING_ISSUE_TYPES.has(issue.type) ? issue.bbox : undefined)
      return box ? [{ ...issue, bbox: box }] : []
    })
    return groupIssuesByBbox(withSourceBox, issueNumberById)
  }, [issueNumberById, issues])
  // M→1 合并块的主框之外框：covered_source_bboxes 中与主框不重合的
  // 其余源区域同样画到源图（浅虚线、无角标），明确"译文框是多个源块
  // 的合并"而不是 1↔1 对应，避免审阅者以为两侧框错位是画框错误。
  const extraSourceBoxes = useMemo(() => {
    const entries: { key: string; box: Issue["bbox"]; issueIds: string[] }[] = []
    for (const issue of issues) {
      const metrics = issue.metrics ?? {}
      const covered = metrics.covered_source_bboxes
      if (!Array.isArray(covered) || covered.length < 2) continue
      const primary = metrics.source_bbox as Issue["bbox"] | undefined
      for (const box of covered as Issue["bbox"][]) {
        if (!box) continue
        if (
          primary &&
          Math.round(primary.x) === Math.round(box.x) &&
          Math.round(primary.y) === Math.round(box.y)
        ) {
          continue
        }
        const key = [box.x, box.y, box.width, box.height]
          .map((value) => Math.round(value))
          .join(",")
        const existing = entries.find((entry) => entry.key === key)
        if (existing) {
          if (!existing.issueIds.includes(issue.id)) {
            existing.issueIds.push(issue.id)
          }
        } else {
          entries.push({ key, box, issueIds: [issue.id] })
        }
      }
    }
    return entries
  }, [issues])

  useEffect(() => () => {
    if (scrollFrameRef.current !== null) cancelAnimationFrame(scrollFrameRef.current)
  }, [])

  useLayoutEffect(() => {
    const centers = pendingZoomCentersRef.current
    if (!centers) return

    restoringZoomRef.current = true
    const restoreCenter = (
      canvas: HTMLDivElement | null,
      center: { x: number; y: number } | null,
    ) => {
      if (!canvas || !center) return
      canvas.scrollLeft = center.x * canvas.scrollWidth - canvas.clientWidth / 2
      canvas.scrollTop = center.y * canvas.scrollHeight - canvas.clientHeight / 2
    }
    restoreCenter(sourceCanvasRef.current, centers.source)
    restoreCenter(targetCanvasRef.current, centers.target)
    pendingZoomCentersRef.current = null

    if (scrollFrameRef.current !== null) cancelAnimationFrame(scrollFrameRef.current)
    scrollFrameRef.current = requestAnimationFrame(() => {
      restoringZoomRef.current = false
      scrollFrameRef.current = null
    })
  }, [zoom])

  const changeZoom = (nextZoom: number) => {
    const boundedZoom = Math.min(Math.max(nextZoom, MIN_PAGE_ZOOM), MAX_PAGE_ZOOM)
    if (boundedZoom === zoom) return

    const captureCenter = (canvas: HTMLDivElement | null) => canvas
      ? {
          x: (canvas.scrollLeft + canvas.clientWidth / 2) / canvas.scrollWidth,
          y: (canvas.scrollTop + canvas.clientHeight / 2) / canvas.scrollHeight,
        }
      : null
    pendingZoomCentersRef.current = {
      source: captureCenter(sourceCanvasRef.current),
      target: captureCenter(targetCanvasRef.current),
    }
    setZoom(boundedZoom)
  }

  const syncScroll = (side: "source" | "target", canvas: HTMLDivElement) => {
    const target = side === "source" ? targetCanvasRef.current : sourceCanvasRef.current
    if (
      restoringZoomRef.current ||
      !target ||
      (scrollOriginRef.current && scrollOriginRef.current !== side)
    ) return

    scrollOriginRef.current = side
    const sourceMaxLeft = Math.max(canvas.scrollWidth - canvas.clientWidth, 0)
    const sourceMaxTop = Math.max(canvas.scrollHeight - canvas.clientHeight, 0)
    const targetMaxLeft = Math.max(target.scrollWidth - target.clientWidth, 0)
    const targetMaxTop = Math.max(target.scrollHeight - target.clientHeight, 0)
    target.scrollLeft = sourceMaxLeft ? (canvas.scrollLeft / sourceMaxLeft) * targetMaxLeft : 0
    target.scrollTop = sourceMaxTop ? (canvas.scrollTop / sourceMaxTop) * targetMaxTop : 0

    if (scrollFrameRef.current !== null) cancelAnimationFrame(scrollFrameRef.current)
    scrollFrameRef.current = requestAnimationFrame(() => {
      scrollOriginRef.current = null
      scrollFrameRef.current = null
    })
  }

  if (!sourceUrl && !targetUrl) {
    return (
      <Empty
        description="本页无渲染图：默认只渲染需复核页面，历史记录回看也不含渲染图（可在工作台重新质检生成）。"
        image={Empty.PRESENTED_IMAGE_SIMPLE}
      />
    )
  }

  return (
    <Row gutter={[14, 14]} className="page-compare">
      {sourceUrl && (
        <Col xs={24} xl={12}>
          <div className="page-compare__panel page-compare__panel--source">
            <div className="page-compare__panel-head">
              <span><i />源文档 · 原文</span>
              <span>
                第 {page} 页
                {sourceBboxGroups.length > 0 || extraSourceBoxes.length > 0
                  ? " · 虚线框为问题的原文侧定位"
                  : ""}
              </span>
            </div>
            <div
              ref={sourceCanvasRef}
              className="page-compare__canvas"
              onScroll={(event) => syncScroll("source", event.currentTarget)}
            >
              <div
                className="page-compare__source-stage"
                style={{ width: `${zoom * 100}%` }}
              >
                <img
                  src={sourceUrl}
                  alt={`源文档第 ${page} 页`}
                  className="page-compare__image"
                  width={1191}
                  height={1684}
                  loading="lazy"
                  decoding="async"
                  onLoad={(event) => {
                    const img = event.currentTarget
                    setPageWidth(img.naturalWidth / 2)
                    setPageHeight(img.naturalHeight / 2)
                  }}
                  style={{ width: `${zoom * 100}%`, maxWidth: "none" }}
                />
                {pageWidth > 0 &&
                  extraSourceBoxes.map((entry) => {
                    const groupActive =
                      activeIssueId !== null &&
                      entry.issueIds.includes(activeIssueId)
                    return (
                      <div
                        key={`source-extra-${entry.key}`}
                        style={{
                          position: "absolute",
                          border: groupActive
                            ? `3px dashed ${PALETTE.critical}`
                            : `1px dashed ${PALETTE.critical}`,
                          background: groupActive
                            ? "rgba(255,82,82,0.12)"
                            : "rgba(255,82,82,0.04)",
                          left: `${(entry.box!.x / pageWidth) * 100}%`,
                          top: `${(entry.box!.y / pageHeight) * 100}%`,
                          width: `${(entry.box!.width / pageWidth) * 100}%`,
                          height: `${(entry.box!.height / pageHeight) * 100}%`,
                          pointerEvents: "none",
                        }}
                      />
                    )
                  })}
                {pageWidth > 0 &&
                  sourceBboxGroups.map((group) => {
                    const first = group[0].issue
                    const groupActive = group.some(
                      ({ issue }) => issue.id === activeIssueId,
                    )
                    return (
                      <div
                        key={`source-${first.id}`}
                        style={{
                          position: "absolute",
                          border: groupActive
                            ? `3px solid ${PALETTE.critical}`
                            : `2px dashed ${PALETTE.critical}`,
                          background: groupActive
                            ? "rgba(255,82,82,0.14)"
                            : "rgba(255,82,82,0.06)",
                          left: `${(first.bbox!.x / pageWidth) * 100}%`,
                          top: `${(first.bbox!.y / pageHeight) * 100}%`,
                          width: `${(first.bbox!.width / pageWidth) * 100}%`,
                          height: `${(first.bbox!.height / pageHeight) * 100}%`,
                          pointerEvents: "none",
                        }}
                      >
                        <span className="page-compare__badges">
                          {group.map(({ issue, index }) => (
                            <IssueBadge
                              key={issue.id}
                              index={index}
                              active={issue.id === activeIssueId}
                            />
                          ))}
                        </span>
                      </div>
                    )
                  })}
              </div>
            </div>
          </div>
        </Col>
      )}
      {targetUrl && (
        <Col xs={24} xl={sourceUrl ? 12 : 24}>
          <div className="page-compare__panel page-compare__panel--target">
            <div className="page-compare__panel-head">
              <span><i />目标文档 · 译文</span>
              <Space size={4}>
                <span>第 {page} 页 · 红框为问题位置 · {Math.round(zoom * 100)}%</span>
                <Tooltip title="缩小文档">
                  <Button
                    type="text"
                    size="small"
                    icon={<ZoomOutOutlined />}
                    aria-label="缩小原文和译文"
                    disabled={zoom <= MIN_PAGE_ZOOM}
                    onClick={() => changeZoom(zoom - PAGE_ZOOM_STEP)}
                  />
                </Tooltip>
                <Tooltip title="放大文档">
                  <Button
                    type="text"
                    size="small"
                    icon={<ZoomInOutlined />}
                    aria-label="放大原文和译文"
                    disabled={zoom >= MAX_PAGE_ZOOM}
                    onClick={() => changeZoom(zoom + PAGE_ZOOM_STEP)}
                  />
                </Tooltip>
              </Space>
            </div>
            <div
              ref={targetCanvasRef}
              className="page-compare__canvas"
              onScroll={(event) => syncScroll("target", event.currentTarget)}
            >
              <div
                className="page-compare__target-stage"
                style={{ width: `${zoom * 100}%` }}
              >
                <img
                  src={targetUrl}
                  alt={`目标文档第 ${page} 页`}
                  className="page-compare__image"
                  width={1191}
                  height={1684}
                  loading="lazy"
                  decoding="async"
                  onLoad={(event) => {
                    const img = event.currentTarget
                    setPageWidth(img.naturalWidth / 2)
                    setPageHeight(img.naturalHeight / 2)
                  }}
                />
                {pageWidth > 0 &&
                  bboxGroups.map((group) => {
                    const first = group[0].issue
                    // 组内任一 Issue 激活即整框加粗，便于定位整组。
                    const groupActive = group.some(
                      ({ issue }) => issue.id === activeIssueId,
                    )
                    return (
                      <div
                        key={first.id}
                        style={{
                          position: "absolute",
                          border: groupActive
                            ? `3px solid ${PALETTE.critical}`
                            : `2px solid ${PALETTE.critical}`,
                          background: groupActive
                            ? "rgba(255,82,82,0.18)"
                            : "rgba(255,82,82,0.08)",
                          left: `${(first.bbox!.x / pageWidth) * 100}%`,
                          top: `${(first.bbox!.y / pageHeight) * 100}%`,
                          width: `${(first.bbox!.width / pageWidth) * 100}%`,
                          height: `${(first.bbox!.height / pageHeight) * 100}%`,
                          pointerEvents: "none",
                        }}
                      >
                        <span className="page-compare__badges">
                          {group.map(({ issue, index }) => (
                            <IssueBadge
                              key={issue.id}
                              index={index}
                              active={issue.id === activeIssueId}
                            />
                          ))}
                        </span>
                      </div>
                    )
                  })}
              </div>
            </div>
          </div>
        </Col>
      )}
    </Row>
  )
}

/** 复核状态筛选选项。 */
export type ReviewFilter = "all" | "pending" | "done"

export interface PageDetailsViewState {
  page?: number
  issue?: string
  issueNumber?: string
  sourceText?: string
  severity?: string[]
  issueType?: string[]
  review?: ReviewFilter
  issuePage?: number
}

interface RelatedIssueEvidence {
  issue: Issue
  number: number
}

const METRIC_LABELS: Record<string, string> = {
  region_type: "区域类型",
  source_region_type: "原文区域类型",
  target_region_type: "译文区域类型",
  x_shift_ratio: "水平位置变化",
  y_shift_ratio: "垂直位置变化",
  width_change_ratio: "宽度变化",
  height_change_ratio: "高度变化",
  font_size_change_ratio: "字号变化",
  overlap_ratio: "译文重叠比例",
  horizontal_intrusion_ratio: "水平侵入比例",
  vertical_intrusion_ratio: "垂直侵入比例",
  source_overlap_ratio: "原文重叠比例",
  overlap_increase_ratio: "新增重叠比例",
  source_language_ratio: "源语言保留比例",
  source_script: "原文主导文字体系",
  target_script: "译文主导文字体系",
  unchanged_image_count: "未变化图片数量",
  unchanged_image_bbox_area_ratio: "疑似漏译区域占页面比例",
  unchanged_image_area_ratio: "未变化图片占页面比例",
  ocr_status: "OCR 状态",
  detection_mode: "检测方式",
  ocr_provider: "OCR 引擎",
  ocr_model: "OCR 模型",
  source_ocr_script_chars: "原图源语言字符数",
  target_ocr_source_script_chars: "译图残留源语言字符数",
  target_ocr_target_script_chars: "译图目标语言字符数",
  ocr_high_source_chars_threshold: "高危残留字符阈值",
  target_source_script_ratio: "译图源语言残留比例",
  ocr_confidence: "OCR 平均置信度",
  ocr_line_count: "OCR 文字行数",
  ocr_residue_line_count: "源语言残留行数",
  ocr_text_snippet: "识别到的残留文字",
  candidate_bbox_area_ratio: "OCR 候选区域占页面比例",
  threshold: "触发阈值",
  bbox_width: "区域宽度",
  letter_count: "字母数量",
  text_color: "文字颜色",
  background_color: "页面背景色",
  page_width: "页面宽度",
  page_height: "页面高度",
  diff_count: "差异数量",
  term: "命中术语",
  allowed_translations: "允许译法",
  glossary_reference: "术语库版本",
  source_alignment: "原文对齐方式",
  target_alignment: "译文对齐方式",
  source_line_count: "原文行数",
  target_line_count: "译文行数",
  group_match_count: "配对行数",
  group_match_ratio: "文本流配对比例",
  match_score: "区域匹配综合分",
  match_position_similarity: "位置相似度",
  match_size_similarity: "尺寸相似度",
  match_type_similarity: "类型相似度",
  match_order_similarity: "阅读顺序相似度",
  primary_text: "第一个区域文本",
  other_text: "第二个区域文本",
  primary_region_type: "第一个区域类型",
  other_region_type: "第二个区域类型",
  type_change: "区域类型变化",
  text_opacity: "目标文本透明度",
  image_overlap_ratio: "图片与文本重叠比例",
  invisible_text_region: "透明文本区域",
  invisible_text_bbox: "透明文本坐标",
  visible_image_region: "可见图片区域",
  merged_source_count: "合并源区域数量",
  merged_region_compare: "多对一合并对照",
}

const EVIDENCE_ONLY_KEYS = new Set([
  "source_text",
  "target_text",
  "source_bbox",
  "target_bbox",
  "other_bbox",
  "covered_source_bboxes",
  "source_other_region",
  "source_other_text",
  "source_other_bbox",
  "source_other_region_type",
  "source_numbers",
  "target_numbers",
  "normalized_source_numbers",
  "normalized_target_numbers",
  "missing_numbers",
  "extra_numbers",
  "resize_magnitude",
  "sample",
  "text",
  "note",
  "source_spreads",
  "target_spreads",
  "other_region",
  "primary_text",
  "other_text",
  "source_region_ids",
  "target_region_ids",
])

const RATIO_METRICS = new Set([
  "x_shift_ratio",
  "y_shift_ratio",
  "width_change_ratio",
  "height_change_ratio",
  "font_size_change_ratio",
  "overlap_ratio",
  "horizontal_intrusion_ratio",
  "vertical_intrusion_ratio",
  "source_overlap_ratio",
  "overlap_increase_ratio",
  "source_language_ratio",
  "unchanged_image_bbox_area_ratio",
  "unchanged_image_area_ratio",
  "target_source_script_ratio",
  "ocr_confidence",
  "candidate_bbox_area_ratio",
  "threshold",
  "group_match_ratio",
  "match_score",
  "match_position_similarity",
  "match_size_similarity",
  "match_type_similarity",
  "match_order_similarity",
  "text_opacity",
  "image_overlap_ratio",
])

const REGION_TYPE_LABELS: Record<string, string> = {
  text: "文本",
  image: "图片",
  vector: "图形",
  group: "组合内容",
  unknown: "未知类型",
}

const ALIGNMENT_LABELS: Record<string, string> = {
  left: "左对齐",
  center: "居中对齐",
  right: "右对齐",
  justify: "两端对齐",
  other: "其他对齐方式",
  unknown: "无法判断",
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

function formatDimensionChange(value: number, dimension: string): string {
  const direction = value < 0 ? "缩小" : "增加"
  return `${dimension}${direction} ${formatPercent(Math.abs(value))}`
}

/** 单条原文或译文证据，统一展示文本与可选坐标。 */
function EvidenceTextLine({
  label,
  text,
  bbox,
  danger = false,
}: {
  label: string
  text: string
  bbox: string | null
  danger?: boolean
}) {
  return (
    <div>
      <Typography.Text type="secondary">{label}：</Typography.Text>
      <Typography.Text type={danger ? "danger" : undefined}>{text}</Typography.Text>
      {bbox && (
        <Typography.Text type="secondary">（BBox：{bbox}）</Typography.Text>
      )}
    </div>
  )
}

/** 根据 Issue 类型把机器指标转成列表中可直接理解的一句话。 */
function issueDisplayDescription(issue: Issue): string {
  const metrics = issue.metrics ?? {}
  const regionType = typeof metrics.region_type === "string" ? metrics.region_type : null
  const regionTypeLabel = regionType ? REGION_TYPE_LABELS[regionType] ?? regionType : ""
  const xShift = typeof metrics.x_shift_ratio === "number" ? metrics.x_shift_ratio : null
  const yShift = typeof metrics.y_shift_ratio === "number" ? metrics.y_shift_ratio : null
  const widthChange = typeof metrics.width_change_ratio === "number"
    ? metrics.width_change_ratio
    : null
  const heightChange = typeof metrics.height_change_ratio === "number"
    ? metrics.height_change_ratio
    : null
  const fontChange = typeof metrics.font_size_change_ratio === "number"
    ? metrics.font_size_change_ratio
    : null
  const sourceAlignment = typeof metrics.source_alignment === "string"
    ? metrics.source_alignment
    : null
  const targetAlignment = typeof metrics.target_alignment === "string"
    ? metrics.target_alignment
    : null

  if (issue.type === "region_shifted" && xShift !== null && yShift !== null) {
    const horizontal = `${xShift < 0 ? "向左" : "向右"} ${formatPercent(Math.abs(xShift))}`
    const vertical = `${yShift < 0 ? "向上" : "向下"} ${formatPercent(Math.abs(yShift))}`
    return `目标区域相对页面${horizontal}、${vertical}。`
  }
  if (issue.type === "region_resized" && widthChange !== null && heightChange !== null) {
    return `目标区域${formatDimensionChange(widthChange, "宽度")}，${formatDimensionChange(heightChange, "高度")}。`
  }
  if (
    (issue.type === "font_shrink" || issue.type === "typography_changed") &&
    fontChange !== null
  ) {
    return `目标区域${formatDimensionChange(fontChange, "字号")}。`
  }
  if (issue.type === "text_rasterized") {
    return "目标文档改用图片显示这段文字。该项不代表翻译错误，请核对文字内容、清晰度，以及交付规范是否允许文字转为图片。"
  }
  if (issue.type === "text_vectorized") {
    return "目标页面把文字改成了图形，系统无法继续检查数字、漏译和术语。请人工核对页面文字内容是否正确。"
  }
  if (issue.type === "untranslated_raster") {
    if (metrics.detection_mode === "ocr_partial") {
      return "目标图片内部仍识别到较多源语言文字，疑似图片标签只翻译了一部分。系统已按 OCR 文字位置标出残留区域，请逐项核对。"
    }
    return "目标页面有一大片图像化文字与原文完全一致，疑似没有翻译。系统已标出整片区域，建议结合 OCR 或人工核对图片中的文字。"
  }
  if (issue.type === "text_fragmented") {
    return "目标文字被拆成窄列、竖排或零散字符，阅读顺序可能异常。请核对文字是否完整且排列正确。"
  }
  if (issue.type === "invisible_text") {
    return "目标文档中存在页面上看不到的文字。请核对文字是否遗漏显示，以及交付文件是否符合预期。"
  }
  if (issue.type === "text_image_overlap") {
    return "目标文档中的文字与图片明显重叠，可能影响阅读。请核对文字或图片是否被遮挡。"
  }
  if (issue.type === "text_overflow") {
    return "目标文字超出所在文本区域，可能挤到其他内容。请核对换行、间距和遮挡情况。"
  }
  if (issue.type === "text_clipped") {
    return "目标文字没有完整显示，部分内容可能被裁切。请核对句尾和区域边缘。"
  }
  if (issue.type === "abnormal_wrap") {
    return "目标文字的换行方式与原文差异明显。请核对断句、段落高度和阅读顺序。"
  }
  if (issue.type === "line_count_explosion") {
    return "译文行数相对原文明显增加，可能导致版面拥挤。请核对换行和文字区域高度。"
  }
  if (issue.type === "text_alignment_changed" && sourceAlignment && targetAlignment) {
    const sourceLabel = ALIGNMENT_LABELS[sourceAlignment] ?? sourceAlignment
    const targetLabel = ALIGNMENT_LABELS[targetAlignment] ?? targetAlignment
    return `目标段落由${sourceLabel}变为${targetLabel}。请确认是否符合原版式要求。`
  }
  if (issue.type === "missing_element") {
    const typeHint = regionTypeLabel ? `${regionTypeLabel}内容` : "内容"
    return `目标文档未找到与原文对应的${typeHint}。请确认内容是否确实缺失，或只是位置变化导致未能对应。`
  }
  if (issue.type === "added_element") {
    const typeHint = regionTypeLabel ? `${regionTypeLabel}内容` : "内容"
    return `目标文档中存在未与原文对应的${typeHint}。请确认是否确实多出内容，或只是位置变化导致未能对应。`
  }
  return issue.description
}

function formatMetricValue(key: string, value: unknown): string {
  if (key === "ocr_status" && value === "not_run") {
    return "未运行（当前使用图像指纹判断）"
  }
  if (key === "ocr_status" && value === "confirmed") return "已确认"
  if (key === "detection_mode" && value === "ocr_partial") return "图片局部 OCR"
  if (typeof value === "number") {
    if (RATIO_METRICS.has(key)) return formatPercent(value)
    return Number.isInteger(value) ? String(value) : value.toFixed(2)
  }
  if (Array.isArray(value)) return value.join("、")
  if (value && typeof value === "object") return JSON.stringify(value)
  return String(value ?? "—")
}

function issueMetricRows(issue: Issue): { label: string; value: string }[] {
  return Object.entries(issue.metrics ?? {})
    .filter(([key, value]) => !EVIDENCE_ONLY_KEYS.has(key) && value !== null)
    .map(([key, value]) => ({
      label: METRIC_LABELS[key] ? `${METRIC_LABELS[key]}（${key}）` : key,
      value: formatMetricValue(key, value),
    }))
}

function formatEvidenceBbox(value: unknown): string | null {
  if (!value || typeof value !== "object") return null
  const bbox = value as Record<string, unknown>
  const values = [bbox.x, bbox.y, bbox.width, bbox.height]
  if (!values.every((item) => typeof item === "number")) return null
  const [x, y, width, height] = values as number[]
  return `x ${x.toFixed(1)}，y ${y.toFixed(1)}，宽 ${width.toFixed(1)} pt，高 ${height.toFixed(1)} pt`
}

interface ImageEvidence {
  key: string
  side: "source" | "target"
  label: string
  description: string
  url: string
  originalUrl: string | null
  bbox: NonNullable<Issue["bbox"]>
}

function evidenceBbox(value: unknown): NonNullable<Issue["bbox"]> | null {
  if (!value || typeof value !== "object") return null
  const bbox = value as Record<string, unknown>
  if (![bbox.x, bbox.y, bbox.width, bbox.height].every((item) => typeof item === "number")) {
    return null
  }
  return bbox as NonNullable<Issue["bbox"]>
}

/** 从 Issue 的区域类型、文档侧和 BBox 解析可查看的图片证据。 */
function imageEvidenceFor(
  issue: Issue,
  historyRecordId: string | null,
  rendered?: { source: string[]; target: string[] },
): ImageEvidence[] {
  const metrics = issue.metrics ?? {}
  const sourceIsImage = metrics.source_region_type === "image"
    || (metrics.region_type === "image" && issue.type === "missing_element")
  const targetIsImage = metrics.target_region_type === "image"
    || (metrics.region_type === "image" && issue.type !== "missing_element")
  const evidence: ImageEvidence[] = []

  const addEvidence = (
    key: string,
    side: "source" | "target",
    label: string,
    description: string,
    regionIdValue: unknown,
    bboxValue: unknown,
  ) => {
    const url = pageImage(side, issue.page, rendered)
    const bbox = evidenceBbox(bboxValue) ?? issue.bbox ?? null
    const regionId = typeof regionIdValue === "string" ? regionIdValue : null
    const originalUrl = historyRecordId && regionId
      ? `/api/history/item/${encodeURIComponent(historyRecordId)}/image/${side}/${encodeURIComponent(regionId)}`
      : null
    if ((!url || !bbox) && !originalUrl) return
    evidence.push({
      key,
      side,
      label,
      description,
      url: url ?? "",
      originalUrl,
      bbox: bbox ?? { x: 0, y: 0, width: 0, height: 0 },
    })
  }

  if (sourceIsImage) {
    const description = issue.type === "missing_element"
      ? "这是源 PDF 中未在目标文档找到对应内容的内嵌图片。"
      : "这是该问题涉及的源 PDF 内嵌图片，用于与目标文档对应区域复核。"
    addEvidence(
      "source",
      "source",
      "源文档图片证据",
      description,
      issue.source_region,
      metrics.source_bbox,
    )
  }
  if (targetIsImage) {
    let label = "目标文档图片证据"
    let description = "这是该问题涉及的目标 PDF 内嵌图片，用于核对实际保存的图片内容。"
    if (issue.type === "text_rasterized") {
      label = "目标文档中用于显示这段文字的图片"
      description = "目标文档中的这段文字通过图片显示。请核对图片中的文字是否完整、清晰，并与原文内容一致。"
    } else if (issue.type === "added_element") {
      description = "这是目标 PDF 中未与源文档内容匹配的新增内嵌图片。"
    }
    addEvidence(
      "target",
      "target",
      label,
      description,
      metrics.visible_image_region ?? issue.target_region,
      metrics.target_bbox,
    )
  }
  if (metrics.primary_region_type === "image") {
    addEvidence(
      "primary",
      "target",
      "重叠区域中的第一个图片",
      "这是参与当前区域重叠问题的第一个目标 PDF 内嵌图片。",
      issue.target_region,
      metrics.target_bbox,
    )
  }
  if (metrics.other_region_type === "image") {
    addEvidence(
      "other",
      "target",
      "重叠区域中的第二个图片",
      "这是参与当前区域重叠问题的第二个目标 PDF 内嵌图片。",
      metrics.other_region,
      metrics.other_bbox,
    )
  }
  return evidence
}

/** 图片类型 Issue 的局部截图入口；默认只显示图标，点击后放大对应 PDF 区域。 */
function IssueImageEvidence({
  issue,
  historyRecordId,
  rendered,
}: {
  issue: Issue
  historyRecordId: string | null
  rendered?: { source: string[]; target: string[] }
}) {
  const evidence = imageEvidenceFor(issue, historyRecordId, rendered)
  const [activeEvidence, setActiveEvidence] = useState<ImageEvidence | null>(null)
  const [originalImageError, setOriginalImageError] = useState(false)
  const [previewError, setPreviewError] = useState(false)
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    setOriginalImageError(false)
    setPreviewError(false)
  }, [activeEvidence])

  useEffect(() => {
    if (!activeEvidence) return
    if (activeEvidence.originalUrl && !originalImageError) return
    if (!activeEvidence.url) {
      setPreviewError(true)
      return
    }
    const image = new Image()
    let cancelled = false
    image.onload = () => {
      if (cancelled || !canvasRef.current) return
      const padding = IMAGE_PREVIEW_PADDING_PT * PDF_RENDER_SCALE
      const rawX = activeEvidence.bbox.x * PDF_RENDER_SCALE
      const rawY = activeEvidence.bbox.y * PDF_RENDER_SCALE
      const rawWidth = activeEvidence.bbox.width * PDF_RENDER_SCALE
      const rawHeight = activeEvidence.bbox.height * PDF_RENDER_SCALE
      const sourceX = Math.min(image.naturalWidth - 1, Math.max(0, rawX - padding))
      const sourceY = Math.min(image.naturalHeight - 1, Math.max(0, rawY - padding))
      const sourceWidth = Math.max(
        1,
        Math.min(image.naturalWidth - sourceX, rawWidth + padding * 2),
      )
      const sourceHeight = Math.max(
        1,
        Math.min(image.naturalHeight - sourceY, rawHeight + padding * 2),
      )
      const displayScale = Math.min(3, 720 / Math.max(sourceWidth, 1))
      const canvas = canvasRef.current
      canvas.width = Math.max(1, Math.round(sourceWidth * displayScale))
      canvas.height = Math.max(1, Math.round(sourceHeight * displayScale))
      const context = canvas.getContext("2d")
      if (!context) return
      context.imageSmoothingEnabled = false
      context.drawImage(
        image,
        sourceX,
        sourceY,
        sourceWidth,
        sourceHeight,
        0,
        0,
        canvas.width,
        canvas.height,
      )
    }
    image.onerror = () => {
      if (!cancelled) setPreviewError(true)
    }
    image.src = activeEvidence.url
    return () => {
      cancelled = true
    }
  }, [activeEvidence, originalImageError])

  if (!evidence.length) return null
  const showingOriginalImage = Boolean(activeEvidence?.originalUrl && !originalImageError)
  return (
    <>
      <Space wrap size={8}>
        {evidence.map((item) => (
          <Space key={item.key} size={4}>
            <Typography.Text type="secondary">{item.label}：</Typography.Text>
            <Tooltip title={`查看：${item.label}`}>
              <Button
                type="text"
                icon={<PictureOutlined />}
                aria-label={`查看${item.label}详情`}
                onClick={(event) => {
                  event.stopPropagation()
                  setActiveEvidence(item)
                }}
              />
            </Tooltip>
          </Space>
        ))}
      </Space>
      <Modal
        title={activeEvidence ? `${activeEvidence.label}详情 · 第 ${issue.page} 页` : "图片详情"}
        open={Boolean(activeEvidence)}
        footer={null}
        width={800}
        destroyOnHidden
        onCancel={() => setActiveEvidence(null)}
      >
        {showingOriginalImage ? (
          <div className="issue-image-preview">
            <img
              src={activeEvidence?.originalUrl ?? undefined}
              alt={activeEvidence?.description}
              onError={() => setOriginalImageError(true)}
            />
          </div>
        ) : previewError ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="图片区域加载失败" />
        ) : (
          <div className="issue-image-preview">
            <canvas ref={canvasRef} aria-label="问题图片区域放大预览" />
          </div>
        )}
        {activeEvidence && (
          <Space orientation="vertical" size={4}>
            <div>
              <Typography.Text strong>证据说明：</Typography.Text>
              <Typography.Text>{activeEvidence.description}</Typography.Text>
            </div>
            <Typography.Text type="secondary">
              {showingOriginalImage
                ? "图片来源：PDF 中实际保存的内嵌图片原始内容。"
                : originalImageError
                ? "内嵌原图提取失败，当前显示页面区域裁剪。"
                : "图片来源：当前页面渲染图的对应区域裁剪。"}
            </Typography.Text>
            {activeEvidence.bbox.width > 0 && (
              <Typography.Text type="secondary">
                区域坐标：{formatEvidenceBbox(activeEvidence.bbox)}
              </Typography.Text>
            )}
          </Space>
        )}
      </Modal>
    </>
  )
}

/** 按页内 Issue 列表生成分组：同 bbox 的多条合并为一组（与图上红框
 * 分组同键），无 bbox 的独立成组。返回 [(组键, [issue, index][])]。
 */
function groupIssuesByBbox(
  issues: Issue[],
  issueNumberById?: ReadonlyMap<string, number>,
): { issue: Issue; index: number }[][] {
  const groups = new Map<string, { issue: Issue; index: number }[]>()
  issues.forEach((issue, localIndex) => {
    const index = issueNumberById?.get(issue.id) ?? localIndex
    const key = issue.bbox
      ? [
          issue.bbox.x,
          issue.bbox.y,
          issue.bbox.width,
          issue.bbox.height,
        ]
          .map((value) => Math.round(value))
          .join(",")
      : `solo-${issue.id}`
    const bucket = groups.get(key)
    if (bucket) bucket.push({ issue, index })
    else groups.set(key, [{ issue, index }])
  })
  return [...groups.values()]
}

/** Issue 展开详情：定位状态 + 阈值/差异明细，让"哪里出的问题"可读。 */
function IssueDetails({
  issue,
  decisions,
  onDecide,
  onHighlight,
  relatedIssues,
  historyRecordId,
  rendered,
  onAiInvestigate,
  hideLocation = false,
}: {
  issue: Issue
  decisions: Record<string, ReviewDecision>
  onDecide: (issueId: string, decision: ReviewDecision) => void
  onHighlight: (issueId: string) => void
  relatedIssues: RelatedIssueEvidence[]
  historyRecordId: string | null
  rendered?: { source: string[]; target: string[] }
  /** 开发者模式下的 AI 排查入口；未开启时为 undefined，不渲染按钮。 */
  onAiInvestigate?: () => void
  /** 合并组内非首条不重复"位置"行。 */
  hideLocation?: boolean
}) {
  // 数字不一致的差集明细按"缺失/多余"分组展示，比原始 metrics 更直观。
  const metrics = issue.metrics ?? {}
  // 原文/译文对照：先取局部变量再收窄类型，避免 Record<string, unknown>
  // 索引访问的 typeof 收窄不生效。
  const sourceText = typeof metrics.source_text === "string" ? metrics.source_text : null
  const targetText = typeof metrics.target_text === "string" ? metrics.target_text : null
  const sourceBbox = formatEvidenceBbox(metrics.source_bbox)
  const targetBbox = formatEvidenceBbox(metrics.target_bbox)
  const sourceOtherText = typeof metrics.source_other_text === "string"
    ? metrics.source_other_text
    : null
  const sourceOtherBbox = formatEvidenceBbox(metrics.source_other_bbox)
  const targetOtherText = typeof metrics.other_text === "string" ? metrics.other_text : null
  const targetOtherBbox = formatEvidenceBbox(metrics.other_bbox)
  const isTextOverlap = issue.type === "text_overlap"
  const metricRows = issueMetricRows(issue)
  // M→1 合并块提示：译文区域由多个源区域内容合并时必须显式说明，
  // 否则审阅者会以为源图/译文图两个框错位是画框错误。
  const mergedSourceCount =
    typeof metrics.merged_source_count === "number"
      ? metrics.merged_source_count
      : 0
  const isMatchedGeometry = [
    "region_shifted",
    "region_resized",
    "font_shrink",
    "typography_changed",
  ].includes(issue.type)
  const numberDetail = (
    ["missing_numbers", "extra_numbers"] as const
  ).filter((key) => Array.isArray(metrics[key]) && metrics[key].length)
  return (
    <Space orientation="vertical" size={6} onClick={(e) => e.stopPropagation()}>
      <Typography.Text strong>{issueDisplayDescription(issue)}</Typography.Text>
      <IssueImageEvidence
        issue={issue}
        historyRecordId={historyRecordId}
        rendered={rendered}
      />
      {!hideLocation && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {issue.bbox
            ? `位置：目标文档第 ${issue.page} 页红框处（点击列表项可在图中高亮）`
            : "位置：无法定位到具体区域（差异为页面级，请对照左右两页人工检查）"}
        </Typography.Text>
      )}
      {mergedSourceCount >= 2 && (
        <Typography.Text type="warning" style={{ fontSize: 12 }}>
          该译文区域由 {mergedSourceCount}{" "}
          个源区域的内容合并而来；源图中全部虚线框均为其对应区域，与译文框不是
          1↔1 对应。
        </Typography.Text>
      )}
      {issue.type === "number_mismatch" && (
        <Typography.Text type="warning" style={{ fontSize: 12 }}>
          数字不一致为页面级对比：源图虚线框是缺失数字所在的原文区域，译文红框是多出数字所在的译文区域——两个框各自锚定证据位置，不是同一内容的两侧。
        </Typography.Text>
      )}
      {numberDetail.length > 0 && (
        <Space wrap size={8}>
          {numberDetail.map((key) => (
            <Tag
              key={key}
              style={{
                color: key === "missing_numbers" ? PALETTE.critical : PALETTE.warning,
                background:
                  key === "missing_numbers" ? PALETTE.criticalSoft : PALETTE.warningSoft,
                borderColor:
                  key === "missing_numbers" ? PALETTE.criticalSoft : PALETTE.warningSoft,
              }}
            >
              {key === "missing_numbers"
                ? "源有目标无（missing_numbers）"
                : "目标多出（extra_numbers）"}
              ：
              {(metrics[key] as (string | number)[]).join("、")}
            </Tag>
          ))}
        </Space>
      )}
      {/* 原文 → 译文对照：文本类问题（漏译/碎片化/隐形）必须能看到
          两侧内容，否则无法判断是翻译错还是渲染错。 */}
      {isTextOverlap && (sourceText || sourceOtherText || targetText || targetOtherText) && (
        <Space orientation="vertical" size={2} style={{ fontSize: 12 }}>
          {sourceText && (
            <EvidenceTextLine label="原文区域 1" text={sourceText} bbox={sourceBbox} />
          )}
          {sourceOtherText && (
            <EvidenceTextLine
              label="原文区域 2"
              text={sourceOtherText}
              bbox={sourceOtherBbox}
            />
          )}
          {targetText && (
            <EvidenceTextLine
              label="译文区域 1"
              text={targetText}
              bbox={targetBbox}
              danger
            />
          )}
          {targetOtherText && (
            <EvidenceTextLine
              label="译文区域 2"
              text={targetOtherText}
              bbox={targetOtherBbox}
              danger
            />
          )}
        </Space>
      )}
      {!isTextOverlap && (sourceText || targetText) && (
        <Space orientation="vertical" size={2} style={{ fontSize: 12 }}>
          {sourceText && (
            <div>
              <Typography.Text type="secondary">原文（source_text）：</Typography.Text>
              <Typography.Text>{sourceText}</Typography.Text>
              {sourceBbox && (
                <Typography.Text type="secondary">
                  （source_bbox：{sourceBbox}）
                </Typography.Text>
              )}
            </div>
          )}
          {targetText && (
            <div>
              <Typography.Text type="secondary">译文（target_text）：</Typography.Text>
              <Typography.Text type="danger">{targetText}</Typography.Text>
              {targetBbox && (
                <Typography.Text type="secondary">
                  （target_bbox：{targetBbox}）
                </Typography.Text>
              )}
            </div>
          )}
        </Space>
      )}
      {isMatchedGeometry && sourceText && targetText && (
        <Typography.Text type="warning" style={{ fontSize: 12 }}>
          请先确认原文与译文是否为正确对应区域，再判断位置、尺寸或字号变化。
        </Typography.Text>
      )}
      {metricRows.map((item) => (
        <Typography.Text key={item.label} type="secondary" style={{ fontSize: 12 }}>
          {item.label}：{item.value}
        </Typography.Text>
      ))}
      {relatedIssues.length > 0 && (
        <Space wrap size={4}>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            同一配对的关联问题：
          </Typography.Text>
          {relatedIssues.map(({ issue: related, number }) => (
            <Tag key={related.id}>
              #{number} {ISSUE_TYPE_META[related.type] ?? related.type}
            </Tag>
          ))}
        </Space>
      )}
      <Space>
        {(Object.keys(DECISION_META) as ReviewDecision[]).map((key) => (
          <Button
            key={key}
            size="small"
            type={decisions[issue.id] === key ? "primary" : "default"}
            onClick={() => {
              onHighlight(issue.id)
              onDecide(issue.id, key)
            }}
          >
            {DECISION_META[key].label}
          </Button>
        ))}
        {onAiInvestigate && (
          <Button size="small" onClick={onAiInvestigate}>
            AI 排查
          </Button>
        )}
      </Space>
    </Space>
  )
}

export function PageDetails({
  report,
  rendered,
  taskId,
  historyRecordId,
  decisions,
  onDecide,
  onDecideMany,
  viewState,
  onViewStateChange,
  sourceDisplay,
  targetDisplay,
}: {
  report: QAReport
  rendered?: { source: string[]; target: string[] }
  taskId: string | null
  historyRecordId: string | null
  decisions: Record<string, ReviewDecision>
  onDecide: (issueId: string, decision: ReviewDecision) => void
  onDecideMany: (issueIds: string[], decision: ReviewDecision) => Promise<string[]>
  viewState?: PageDetailsViewState
  onViewStateChange?: (state: PageDetailsViewState) => void
  /** 文档对显示名：仅用于任务书环境锚点，由路由页传入。 */
  sourceDisplay: string
  targetDisplay: string
}) {
  const problems = report.pages.filter((page) => page.status !== "pass")
  const defaultPage = problems[0]?.page ?? report.pages[0]?.page ?? null
  const [localSelected, setLocalSelected] = useState<number | null>(defaultPage)
  const [localActiveIssueId, setLocalActiveIssueId] = useState<string | null>(null)
  // 复核工作流筛选：只看某种严重度 / 只看未复核，处理上百条 Issue 时定位更快。
  const [localIssueNumberFilter, setLocalIssueNumberFilter] = useState("")
  const [localSourceTextFilter, setLocalSourceTextFilter] = useState("")
  const [localSeverityFilter, setLocalSeverityFilter] = useState<string[]>([])
  const [localIssueTypeFilter, setLocalIssueTypeFilter] = useState<string[]>([])
  const [localReviewFilter, setLocalReviewFilter] = useState<ReviewFilter>("all")
  const [localIssuePage, setLocalIssuePage] = useState(1)
  const [selectedIssueIds, setSelectedIssueIds] = useState<string[]>([])
  const [batchDecision, setBatchDecision] = useState<ReviewDecision | null>(null)
  const selected = viewState ? viewState.page ?? defaultPage : localSelected
  const activeIssueId = viewState ? viewState.issue ?? null : localActiveIssueId
  const issueNumberFilter = viewState
    ? viewState.issueNumber ?? ""
    : localIssueNumberFilter
  const sourceTextFilter = viewState
    ? viewState.sourceText ?? ""
    : localSourceTextFilter
  const severityFilter = viewState ? viewState.severity ?? EMPTY_SEVERITIES : localSeverityFilter
  const issueTypeFilter = viewState
    ? viewState.issueType ?? EMPTY_ISSUE_TYPES
    : localIssueTypeFilter
  const reviewFilter = viewState ? viewState.review ?? "all" : localReviewFilter
  const issuePage = viewState ? viewState.issuePage ?? 1 : localIssuePage

  const updateViewState = (patch: Partial<PageDetailsViewState>) => {
    onViewStateChange?.({ ...viewState, ...patch })
  }

  const selectPage = (value: number | null) => {
    setLocalSelected(value)
    setLocalActiveIssueId(null)
    updateViewState({ page: value ?? undefined, issue: undefined })
  }

  const highlightIssue = (value: string | null) => {
    setLocalActiveIssueId(value)
    updateViewState({ issue: value ?? undefined })
  }
  const page = report.pages.find((item) => item.page === selected)
  const allIssues = useMemo(() => report.pages.flatMap((item) => item.issues), [report.pages])
  const issueNumberById = useMemo(
    () => new Map(allIssues.map((issue, index) => [issue.id, index])),
    [allIssues],
  )
  const issueTypeOptions = useMemo(
    () => [...new Set(allIssues.map((issue) => issue.type))].map((type) => ({
      value: type,
      label: ISSUE_TYPE_META[type] ?? type,
    })),
    [allIssues],
  )
  const relatedIssuesFor = (issue: Issue): RelatedIssueEvidence[] => {
    if (!issue.source_region || !issue.target_region) return []
    return allIssues
      .filter(
        (candidate) =>
          candidate.id !== issue.id &&
          candidate.source_region === issue.source_region &&
          candidate.target_region === issue.target_region,
      )
      .map((candidate) => ({
        issue: candidate,
        number: (issueNumberById.get(candidate.id) ?? 0) + 1,
      }))
  }

  // 开发者模式：AI 排查任务书入口的总开关；持久化到 localStorage，
  // 刷新保持。不属于可分享状态，不进 URL 路由。
  const [devMode, setDevMode] = useState(() => isDevModeEnabled())
  const [briefIssues, setBriefIssues] = useState<BriefIssue[] | null>(null)

  const toggleDevMode = (value: boolean) => {
    setDevMode(value)
    setDevModeEnabled(value)
  }

  const openAiBrief = (issueIds: string[]) => {
    const byId = new Map(allIssues.map((issue) => [issue.id, issue]))
    const targets: BriefIssue[] = issueIds
      .map((id) => byId.get(id))
      .filter((issue): issue is Issue => Boolean(issue))
      .map((issue) => ({ issue, number: (issueNumberById.get(issue.id) ?? 0) + 1 }))
    if (targets.length) setBriefIssues(targets)
  }

  // 规则命中列表覆盖整份文档；点击行会同步切换双栏页码并高亮目标区域。
  const visibleIssues = useMemo(() => {
    let list = allIssues
    const issueNumberQueries = parseIssueNumberQueries(issueNumberFilter)
    if (issueNumberQueries.length) {
      // 用户看到的是全报告连续编号，因此筛选必须基于展示编号而不是内部 Issue ID。
      list = list.filter((issue) => {
        const issueNumber = String((issueNumberById.get(issue.id) ?? 0) + 1)
        return issueNumberQueries.some((query) => issueNumber.includes(query))
      })
    }
    if (severityFilter.length) {
      list = list.filter((issue) => severityFilter.includes(issue.severity))
    }
    // 原文文本模糊过滤：逐词 AND 收窄；换行/多余空白归一后再比对，
    // 避免"UN Entity"匹配不上源文本里的换行断词。
    const sourceTextQuery = normalizeSourceText(sourceTextFilter)
    if (sourceTextQuery) {
      const tokens = [...new Set(sourceTextQuery.split(" ").filter(Boolean))]
      list = list.filter((issue) => {
        const haystacks = issueSourceTexts(issue).map(normalizeSourceText)
        return tokens.every((token) => haystacks.some((text) => text.includes(token)))
      })
    }
    if (issueTypeFilter.length) {
      list = list.filter((issue) => issueTypeFilter.includes(issue.type))
    }
    if (reviewFilter === "pending") {
      list = list.filter((issue) => !decisions[issue.id])
    } else if (reviewFilter === "done") {
      list = list.filter((issue) => decisions[issue.id])
    }
    return list
  }, [
    allIssues,
    issueNumberById,
    issueNumberFilter,
    sourceTextFilter,
    severityFilter,
    issueTypeFilter,
    reviewFilter,
    decisions,
  ])
  const pageVisibleIssues = visibleIssues.filter((issue) => issue.page === selected)

  useEffect(() => {
    const visibleIssueIds = new Set(visibleIssues.map((issue) => issue.id))
    setSelectedIssueIds((current) => current.filter((issueId) => visibleIssueIds.has(issueId)))
  }, [visibleIssues])

  useEffect(() => {
    setSelectedIssueIds([])
  }, [taskId])

  const applyBatchDecision = async (decision: ReviewDecision) => {
    if (!selectedIssueIds.length || batchDecision) return
    const submittedIssueIds = [...selectedIssueIds]
    setBatchDecision(decision)
    try {
      const failedIssueIds = await onDecideMany(submittedIssueIds, decision)
      setSelectedIssueIds(failedIssueIds)
    } finally {
      setBatchDecision(null)
    }
  }

  return (
    <section className="page-review">
      <div className="report-section-heading report-section-heading--compare">
        <Space wrap size={10}>
          <Typography.Title level={5}>双语对照</Typography.Title>
          <Tag variant="filled" className="report-count-tag">{report.summary.pages} 页</Tag>
          {taskId && <span className="page-review__state"><i />复核任务已开启</span>}
        </Space>
        <Select
          aria-label="选择对照页码"
          className="page-review__page-select"
          value={selected}
          onChange={(value) => {
            selectPage(value)
          }}
          options={report.pages.map((item) => ({
            value: item.page,
            label: `第 ${item.page} 页 · ${INTEGER_FORMATTER.format(item.score)} 分 · ${
              STATUS_META[item.status]?.label ?? item.status
            }${item.issues.length ? ` · ${item.issues.length} 条规则命中` : ""}`,
          }))}
          showSearch
          optionFilterProp="label"
        />
      </div>
      {page ? (
        <div className="page-review__compare-body">
          {/* key 按页重挂载：换页时清掉上一页的尺寸状态，避免红框按旧尺寸错位闪现。 */}
          <PageCompare
            key={page.page}
            page={page.page}
            issues={pageVisibleIssues}
            rendered={rendered}
            activeIssueId={activeIssueId}
            issueNumberById={issueNumberById}
          />
        </div>
      ) : (
        <Empty
          description="选择页面查看详情。"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      )}

      <div className="issue-list-heading">
        <Space wrap size={10}>
          <Typography.Title level={5}>规则命中列表</Typography.Title>
          <Tag variant="filled" className="issue-list-count">{allIssues.length}</Tag>
        </Space>
        <Space wrap size={8} className="issue-list-filters">
          <Input
            aria-label="按问题编号筛选问题"
            allowClear
            placeholder="例如：83,84,130"
            className="issue-list-number-filter"
            value={issueNumberFilter}
            onChange={(event) => {
              const value = event.target.value
              setLocalIssueNumberFilter(value)
              setLocalIssuePage(1)
              updateViewState({ issueNumber: value || undefined, issuePage: undefined })
            }}
          />
          <Input
            aria-label="按原文文本筛选问题"
            allowClear
            placeholder="按原文文本筛选…"
            className="issue-list-text-filter"
            value={sourceTextFilter}
            onChange={(event) => {
              const value = event.target.value
              setLocalSourceTextFilter(value)
              setLocalIssuePage(1)
              updateViewState({ sourceText: value || undefined, issuePage: undefined })
            }}
          />
          <Select
            aria-label="按严重度筛选问题"
            mode="multiple"
            allowClear
            placeholder="按严重度筛选…"
            className="issue-list-filter"
            value={severityFilter}
            onChange={(value) => {
              setLocalSeverityFilter(value)
              setLocalIssuePage(1)
              updateViewState({ severity: value.length ? value : undefined, issuePage: undefined })
            }}
            options={Object.entries(SEVERITY_META).map(([key, meta]) => ({
              value: key,
              label: meta.label,
            }))}
          />
          <Select
            aria-label="按问题类型筛选问题"
            mode="multiple"
            allowClear
            placeholder="按问题类型筛选…"
            className="issue-list-filter"
            value={issueTypeFilter}
            onChange={(value) => {
              setLocalIssueTypeFilter(value)
              setLocalIssuePage(1)
              updateViewState({
                issueType: value.length ? value : undefined,
                issuePage: undefined,
              })
            }}
            options={issueTypeOptions}
          />
          <Segmented
            aria-label="按复核状态筛选问题"
            value={reviewFilter}
            onChange={(value) => {
              const next = value as ReviewFilter
              setLocalReviewFilter(next)
              setLocalIssuePage(1)
              updateViewState({ review: next === "all" ? undefined : next, issuePage: undefined })
            }}
            options={[
              { value: "all", label: `全部 ${allIssues.length}` },
              {
                value: "pending",
                label: `待处理 ${allIssues.filter((issue) => !decisions[issue.id]).length}`,
              },
              {
                value: "done",
                label: `已复核 ${allIssues.filter((issue) => decisions[issue.id]).length}`,
              },
            ]}
          />
          <label className="issue-list-dev-toggle">
            <Switch
              size="small"
              checked={devMode}
              onChange={toggleDevMode}
              aria-label="切换开发者模式"
            />
            开发者模式
          </label>
        </Space>
      </div>

      {selectedIssueIds.length > 0 && (
        <div className="issue-batch-bar" aria-live="polite">
          <Typography.Text strong>
            已选择 {selectedIssueIds.length} 项，共 {visibleIssues.length} 项
          </Typography.Text>
          <Space wrap size={8}>
            {(Object.keys(DECISION_META) as ReviewDecision[]).map((decision) => (
              <Button
                key={decision}
                size="small"
                type={decision === "confirmed" ? "primary" : "default"}
                loading={batchDecision === decision}
                disabled={batchDecision !== null && batchDecision !== decision}
                onClick={() => void applyBatchDecision(decision)}
              >
                批量{DECISION_META[decision].label}
              </Button>
            ))}
            {devMode && (
              <Button
                size="small"
                onClick={() => openAiBrief(selectedIssueIds)}
              >
                生成 AI 排查任务书
              </Button>
            )}
            <Button
              size="small"
              type="text"
              disabled={batchDecision !== null}
              onClick={() => setSelectedIssueIds([])}
            >
              取消选择
            </Button>
          </Space>
        </div>
      )}

      <Table<Issue>
        className="issue-table"
        rowKey="id"
        size="middle"
        dataSource={visibleIssues}
        rowSelection={{
          selectedRowKeys: selectedIssueIds,
          preserveSelectedRowKeys: true,
          columnWidth: 48,
          onChange: (selectedRowKeys) => {
            setSelectedIssueIds(selectedRowKeys.map(String))
          },
          getCheckboxProps: (issue) => ({
            "aria-label": `选择问题 #${(issueNumberById.get(issue.id) ?? 0) + 1}`,
          }),
        }}
        pagination={{
          current: issuePage,
          pageSize: 8,
          hideOnSinglePage: true,
          showSizeChanger: false,
          onChange: (value) => {
            setLocalIssuePage(value)
            updateViewState({ issuePage: value === 1 ? undefined : value })
          },
        }}
        locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前筛选条件下没有问题" /> }}
        columns={[
          {
            title: "问题标号",
            key: "issueNumber",
            width: 96,
            render: (_, issue) => `#${(issueNumberById.get(issue.id) ?? 0) + 1}`,
          },
          {
            title: "级别",
            dataIndex: "severity",
            width: 104,
            render: (severity: string) => (
              <Tag
                variant="filled"
                style={{
                  color: SEVERITY_META[severity]?.color,
                  background: SEVERITY_META[severity]?.background,
                }}
              >
                <i className="issue-severity-dot" style={{ background: SEVERITY_META[severity]?.color }} />
                {SEVERITY_META[severity]?.label ?? severity}
              </Tag>
            ),
          },
          {
            title: "问题类型",
            dataIndex: "type",
            width: 138,
            render: (type: string, issue) => (
              <Tag
                variant="filled"
                style={{
                  color: SEVERITY_META[issue.severity]?.color,
                  background: SEVERITY_META[issue.severity]?.background,
                }}
              >
                {ISSUE_TYPE_META[type] ?? type}
              </Tag>
            ),
          },
          {
            title: "位置",
            dataIndex: "page",
            width: 118,
            render: (issuePage: number, issue) =>
              `第 ${issuePage} 页${issue.bbox ? " · 已定位" : " · 页级"}`,
          },
          {
            title: "问题描述",
            dataIndex: "description",
            ellipsis: { showTitle: false },
            render: (_, issue) => {
              const description = issueDisplayDescription(issue)
              return <Tooltip title={description}>{description}</Tooltip>
            },
          },
          {
            title: "状态",
            width: 104,
            render: (_, issue) => {
              const decision = decisions[issue.id]
              return decision ? (
                <Tag
                  variant="filled"
                  style={{
                    color: DECISION_META[decision].color,
                    background: DECISION_META[decision].background,
                  }}
                >
                  {DECISION_META[decision].label}
                </Tag>
              ) : (
                <Tag variant="filled" className="issue-pending-tag">待处理</Tag>
              )
            },
          },
        ]}
        expandable={{
          expandedRowKeys: activeIssueId ? [activeIssueId] : [],
          expandIcon: ({ expanded, onExpand, record }) => (
            <Tooltip title={expanded ? "收起问题详情" : "展开问题详情"}>
              <Button
                type="text"
                size="small"
                icon={expanded ? <DownOutlined /> : <RightOutlined />}
                aria-label={expanded ? "收起问题详情" : "展开问题详情"}
                onClick={(event) => {
                  event.stopPropagation()
                  onExpand(record, event)
                }}
              />
            </Tooltip>
          ),
          onExpand: (expanded, issue) => {
            setLocalSelected(issue.page)
            setLocalActiveIssueId(expanded ? issue.id : null)
            updateViewState({ page: issue.page, issue: expanded ? issue.id : undefined })
          },
          expandedRowRender: (issue) => (
            <IssueDetails
              issue={issue}
              decisions={decisions}
              onDecide={onDecide}
              onHighlight={(issueId) => highlightIssue(issueId)}
              relatedIssues={relatedIssuesFor(issue)}
              historyRecordId={historyRecordId}
              rendered={rendered}
              onAiInvestigate={devMode ? () => openAiBrief([issue.id]) : undefined}
            />
          ),
        }}
        onRow={(issue) => ({
          className: issue.id === activeIssueId ? "issue-table__row--active" : "",
          tabIndex: 0,
          "aria-label": `查看第 ${issue.page} 页问题：${issueDisplayDescription(issue)}`,
          onClick: () => {
            setLocalSelected(issue.page)
            setLocalActiveIssueId(issue.id)
            updateViewState({ page: issue.page, issue: issue.id })
          },
          onKeyDown: (event) => {
            if (event.key !== "Enter" && event.key !== " ") return
            event.preventDefault()
            setLocalSelected(issue.page)
            setLocalActiveIssueId(issue.id)
            updateViewState({ page: issue.page, issue: issue.id })
          },
        })}
      />

      <AiBriefModal
        open={briefIssues !== null}
        issues={briefIssues ?? []}
        report={report}
        historyRecordId={historyRecordId}
        sourceDisplay={sourceDisplay}
        targetDisplay={targetDisplay}
        onClose={() => setBriefIssues(null)}
      />
    </section>
  )
}
