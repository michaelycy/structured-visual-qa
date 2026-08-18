/** 与后端 api/dto.py 对齐的请求类型与轻量 fetch 封装。 */

export interface ReportSummary {
  pages: number
  passed_pages: number
  review_pages: number
  failed_pages: number
  issue_counts: Record<string, number>
}

export interface Issue {
  id: string
  page: number
  type: string
  severity: "info" | "low" | "medium" | "high" | "critical"
  description: string
  bbox?: { x: number; y: number; width: number; height: number }
  metrics?: Record<string, unknown>
}

export interface PageResult {
  page: number
  score: number
  status: "pass" | "review" | "fail"
  issues: Issue[]
}

export interface QAReport {
  source_document_id: string
  target_document_id: string
  rule_profile_reference: string
  document_score: number
  status: "pass" | "review" | "fail"
  summary: ReportSummary
  pages: PageResult[]
}

export interface CompareResponse {
  report: QAReport
  rendered: { source: string[]; target: string[] }
}

export interface StageItem {
  stage: string
  summary: string
  data: Record<string, unknown>
  artifact: string
}

export interface RuleProfile {
  schema_version: number
  profile_id: string
  name: string
  version: number
  [key: string]: unknown
}

export type ReviewDecision = "confirmed" | "false_positive" | "ignored"

export interface ReviewRecord {
  source_document_id: string
  target_document_id: string
  rule_profile_reference: string
  decisions: Record<string, { issue_id: string; decision: ReviewDecision; note: string; reviewed_at: string }>
  updated_at: string
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  })
  if (!response.ok) {
    let detail = `HTTP ${response.status}`
    try {
      const body = await response.json()
      if (body?.detail) detail = String(body.detail)
    } catch {
      /* 保留状态码信息 */
    }
    throw new Error(detail)
  }
  return response.json() as Promise<T>
}

export const api = {
  compare: (source: string, target: string, render = true) =>
    request<CompareResponse>("/api/compare", {
      method: "POST",
      body: JSON.stringify({ source, target, render, render_scope: "issues" }),
    }),
  verify: (source: string, target: string, stopAfter: string) =>
    request<{ stages: StageItem[] }>("/api/verify", {
      method: "POST",
      body: JSON.stringify({ source, target, stop_after: stopAfter }),
    }),
  defaultProfile: () => request<RuleProfile>("/api/profile/default"),
  profileSchema: () => request<Record<string, unknown>>("/api/profile/schema"),
  saveProfile: (profile: RuleProfile) =>
    request<{ path: string; reference: string }>("/api/profile/save", {
      method: "POST",
      body: JSON.stringify({ profile }),
    }),
  sampleFiles: () =>
    request<{ samples: string[] }>("/api/files/samples").then((r) => r.samples),
  reviewDecision: (
    taskId: string,
    report: QAReport,
    issueId: string,
    decision: ReviewDecision,
    note = "",
  ) =>
    request<ReviewRecord>("/api/review/decision", {
      method: "POST",
      body: JSON.stringify({
        task_id: taskId,
        report_summary: {
          source_document_id: report.source_document_id,
          target_document_id: report.target_document_id,
          rule_profile_reference: report.rule_profile_reference,
        },
        issue_id: issueId,
        decision,
        note,
      }),
    }),
  reviewTask: (taskId: string) => request<ReviewRecord>(`/api/review/task/${taskId}`),
}
