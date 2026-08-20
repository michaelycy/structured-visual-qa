/** 界面统一文案与颜色 tokens：全应用唯一来源。
 *
 * 状态/严重度/分数的中文文案与配色原先散落在各视图里各写一份，
 * 且大量直接透出英文枚举（fail/critical），对验收客户不友好；
 * 此处集中定义，任何视图只从这里取值。
 */

import type { ReviewDecision } from "./api"

/** 文档/页面状态 → 中文文案与配色（阈值语义见 core profiles）。 */
export const STATUS_META: Record<
  string,
  { label: string; color: string; badge: "success" | "warning" | "error" }
> = {
  pass: { label: "通过", color: "#389e0d", badge: "success" },
  review: { label: "需复核", color: "#d46b08", badge: "warning" },
  fail: { label: "未通过", color: "#cf1322", badge: "error" },
}

/** 严重度 → 中文文案与 Tag 颜色。 */
export const SEVERITY_META: Record<
  string,
  { label: string; color: string }
> = {
  critical: { label: "严重", color: "red" },
  high: { label: "高", color: "volcano" },
  medium: { label: "中", color: "orange" },
  low: { label: "低", color: "green" },
  info: { label: "提示", color: "default" },
}

/** 人工复核判定 → 中文文案与 Tag 颜色。 */
export const DECISION_META: Record<
  ReviewDecision,
  { label: string; color: string }
> = {
  confirmed: { label: "确认问题", color: "red" },
  false_positive: { label: "误报", color: "green" },
  ignored: { label: "忽略", color: "default" },
}

/** 分数配色：与状态阈值一致（≥90 绿 / 75–90 橙 / <75 红）。 */
export function scoreColor(score: number): string {
  if (score >= 90) return "#389e0d"
  if (score >= 75) return "#d46b08"
  return "#cf1322"
}

/** 严重度排序权重：筛选下拉按严重 → 轻微排列。 */
export const SEVERITY_ORDER: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  info: 4,
}

/** 问题类型 → 中文标签（与 core schemas/issue.py 的 IssueType 一一对应）。
 *
 * 面向验收用户的界面不透出英文枚举代码，此表是唯一翻译点；
 * core 新增类型时此表未覆盖会回退显示原始代码，便于发现遗漏。
 */
export const ISSUE_TYPE_META: Record<string, string> = {
  region_shifted: "位置偏移",
  region_resized: "尺寸剧变",
  text_fragmented: "文字碎片化",
  text_overflow: "文本溢出",
  text_clipped: "文本被裁切",
  abnormal_wrap: "换行异常",
  line_count_explosion: "行数暴增",
  font_shrink: "字号缩小",
  text_overlap: "文字重叠",
  text_image_overlap: "文字压图",
  content_out_of_page: "内容越界",
  missing_element: "内容缺失",
  added_element: "多出内容",
  missing_image: "图片缺失",
  typography_changed: "排版变化",
  table_structure_changed: "表格结构变化",
  page_missing: "页面缺失",
  number_mismatch: "数字不一致",
  untranslated_text: "疑似漏译",
  invisible_text: "隐形文字",
}
