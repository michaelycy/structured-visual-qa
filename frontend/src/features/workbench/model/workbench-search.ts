export type ReviewFilter = "all" | "pending" | "done"

export interface WorkbenchSearch {
  record?: string
  page?: number
  issue?: string
  severity?: string[]
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

  return {
    record: typeof search.record === "string" ? search.record : undefined,
    page: positiveInteger(search.page),
    issue: typeof search.issue === "string" ? search.issue : undefined,
    severity: severity?.length ? severity : undefined,
    review: review === "pending" || review === "done" ? review : undefined,
    issuePage: positiveInteger(search.issuePage),
  }
}
