/** 界面统一文案与颜色 tokens：全应用唯一来源。
 *
 * 状态/严重度/分数的中文文案与配色原先散落在各视图里各写一份，
 * 且大量直接透出英文枚举（fail/critical），对验收客户不友好；
 * 此处集中定义，任何视图只从这里取值。
 */

import type { ReviewDecision } from "./api"

/** 产品色板：基础界面色与业务语义色的唯一来源。 */
export const PALETTE = {
  canvas: "#F9F9FB",
  sidebar: "#14181E",
  critical: "#FF5252",
  criticalSoft: "#FFEAEA",
  warning: "#FFA94D",
  warningSoft: "#FFF1E1",
  success: "#00A878",
  successSoft: "#E5F7F0",
  info: "#1F6FEB",
  infoSoft: "#E5EEFE",
  text: "#18191C",
  textMuted: "#8A94A3",
  textSecondary: "#5F6B7A",
  criticalText: "#B42318",
  warningText: "#8A4500",
  successText: "#006B4D",
  infoText: "#174EA6",
  border: "#E8EBEF",
  surface: "#FFFFFF",
} as const

interface SemanticMeta {
  label: string
  color: string
  background: string
  accent?: string
}

/** 文档/页面状态 → 中文文案与配色（阈值语义见 core profiles）。 */
export const STATUS_META: Record<
  string,
  SemanticMeta & { badge: "success" | "warning" | "error" }
> = {
  pass: {
    label: "通过",
    color: PALETTE.successText,
    background: PALETTE.successSoft,
    accent: PALETTE.success,
    badge: "success",
  },
  review: {
    label: "需复核",
    color: PALETTE.warningText,
    background: PALETTE.warningSoft,
    accent: PALETTE.warning,
    badge: "warning",
  },
  fail: {
    label: "未通过",
    color: PALETTE.criticalText,
    background: PALETTE.criticalSoft,
    accent: PALETTE.critical,
    badge: "error",
  },
}

/** 严重度 → 中文文案与 Tag 颜色。 */
export const SEVERITY_META: Record<
  string,
  SemanticMeta
> = {
  critical: { label: "严重", color: PALETTE.criticalText, background: PALETTE.criticalSoft },
  high: { label: "高", color: PALETTE.criticalText, background: PALETTE.criticalSoft },
  medium: { label: "中", color: PALETTE.warningText, background: PALETTE.warningSoft },
  low: { label: "低", color: PALETTE.successText, background: PALETTE.successSoft },
  info: { label: "提示", color: PALETTE.infoText, background: PALETTE.infoSoft },
}

/** 人工复核判定 → 中文文案与 Tag 颜色。 */
export const DECISION_META: Record<
  ReviewDecision,
  SemanticMeta
> = {
  confirmed: {
    label: "确认问题",
    color: PALETTE.criticalText,
    background: PALETTE.criticalSoft,
  },
  false_positive: {
    label: "误报",
    color: PALETTE.successText,
    background: PALETTE.successSoft,
  },
  ignored: {
    label: "忽略",
    color: PALETTE.textSecondary,
    background: PALETTE.canvas,
  },
}

/** 分数配色：与状态阈值一致（≥90 绿 / 75–90 橙 / <75 红）。 */
export function scoreColor(score: number): string {
  if (score >= 90) return PALETTE.successText
  if (score >= 75) return PALETTE.warningText
  return PALETTE.criticalText
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
  region_resized: "区域尺寸明显变化",
  text_fragmented: "文字被拆散显示",
  text_overflow: "文字超出所在区域",
  text_clipped: "文字显示不完整",
  abnormal_wrap: "文字换行异常",
  line_count_explosion: "译文行数明显增加",
  font_shrink: "字号缩小",
  text_overlap: "文字重叠",
  text_image_overlap: "文字与图片重叠",
  content_out_of_page: "内容越界",
  missing_element: "疑似内容缺失",
  added_element: "疑似多出内容",
  missing_image: "图片缺失",
  typography_changed: "字号明显放大",
  table_structure_changed: "表格结构变化",
  page_missing: "页面缺失",
  number_mismatch: "数字不一致",
  untranslated_text: "疑似漏译",
  glossary_violation: "术语译法不符",
  invisible_text: "文字不可见",
  text_rasterized: "文本改为图片显示",
  text_vectorized: "页面文字改为图形",
  text_alignment_changed: "对齐方式变化",
  other: "其他待确认问题",
}
