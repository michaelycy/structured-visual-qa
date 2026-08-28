export type ReviewFilter = "all" | "pending" | "done"

export interface WorkbenchSearch {
  record?: string
  page?: number
  issue?: string
  issueNumber?: string
  sourceText?: string
  severity?: string[]
  issueType?: string[]
  review?: ReviewFilter
  issuePage?: number
}

const positiveInteger = (value: unknown): number | undefined => {
  const parsed = typeof value === "number" ? value : Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined
}

/** 将未知查询参数收窄为可分享的工作台查看状态。 */
export const validateWorkbenchSearch = (search: Record<string, unknown>): WorkbenchSearch => {
  const review = search.review
  const severity = Array.isArray(search.severity)
    ? search.severity.filter((value): value is string => typeof value === "string")
    : typeof search.severity === "string"
      ? [search.severity]
      : undefined
  const issueType = Array.isArray(search.issueType)
    ? search.issueType.filter((value): value is string => typeof value === "string")
    : typeof search.issueType === "string"
      ? [search.issueType]
      : undefined

  return {
    record: typeof search.record === "string" ? search.record : undefined,
    page: positiveInteger(search.page),
    issue: typeof search.issue === "string" ? search.issue : undefined,
    issueNumber: typeof search.issueNumber === "string" && search.issueNumber
      ? search.issueNumber
      : undefined,
    sourceText: typeof search.sourceText === "string" && search.sourceText
      ? search.sourceText
      : undefined,
    severity: severity?.length ? severity : undefined,
    issueType: issueType?.length ? issueType : undefined,
    review: review === "pending" || review === "done" ? review : undefined,
    issuePage: positiveInteger(search.issuePage),
  }
}
