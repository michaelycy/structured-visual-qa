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
  metadata?: Record<string, unknown>
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

export interface Glossary {
  schema_version: number
  glossary_id: string
  name: string
  version: number
  description: string
  entries: { term: string; translations: string[]; note: string; case_sensitive: boolean }[]
}

export interface GlossarySummary {
  filename: string
  glossary_id: string
  name: string
  version: number
  entry_count: number
  reference: string
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

export interface HistoryRecord {
  record_id: string
  created_at: string
  source_display: string
  target_display: string
  status: string
  document_score: number
  pages: number
  issue_total: number
  rule_profile_reference: string
  normalized_from?: Record<string, string | null> | null
  rendered?: { source: string[]; target: string[] } | null
  report?: QAReport
}

export interface CompareSubmitResponse {
  task_id: string | null
  status?: string
  report?: QAReport
  rendered?: { source: string[]; target: string[] }
}

export interface TaskPollResponse {
  task_id: string
  status: "queued" | "running" | "done" | "error"
  error: string | null
  report: QAReport | null
  rendered: { source: string[]; target: string[] } | null
  history_record_id: string | null
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
  compare: (
    source: string,
    target: string,
    sourceDisplay = "",
    targetDisplay = "",
    glossaryReference: string | null = null,
    render = true,
    profilePath: string | null = null,
  ) =>
    request<CompareSubmitResponse>("/api/compare", {
      method: "POST",
      body: JSON.stringify({
        source,
        target,
        source_display: sourceDisplay,
        target_display: targetDisplay,
        glossary_reference: glossaryReference,
        render,
        render_scope: "issues",
        profile_path: profilePath,
      }),
    }),
  glossaryDefault: () => request<Glossary>("/api/glossary/default"),
  glossaryList: () =>
    request<{ glossaries: GlossarySummary[] }>("/api/glossary/list").then(
      (r) => r.glossaries,
    ),
  glossaryItem: (filename: string) =>
    request<Glossary>(`/api/glossary/item/${encodeURIComponent(filename)}`),
  glossarySave: (glossary: Glossary) =>
    request<{ path: string; reference: string }>("/api/glossary/save", {
      method: "POST",
      body: JSON.stringify({ glossary }),
    }),
  glossaryDelete: (filename: string) =>
    request<{ deleted: string }>(
      `/api/glossary/item/${encodeURIComponent(filename)}`,
      { method: "DELETE" },
    ),
  task: (taskId: string) =>
    request<TaskPollResponse>(`/api/tasks/${encodeURIComponent(taskId)}`),
  exportReport: (recordId: string, format: "xlsx" | "html") =>
    fetch("/api/report/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ record_id: recordId, format }),
    }).then(async (response) => {
      if (!response.ok) {
        const payload = await response.json().catch(() => null)
        throw new Error(payload?.detail ?? `导出失败 (HTTP ${response.status})`)
      }
      return response.blob()
    }),
  verify: (source: string, target: string, stopAfter: string) =>
    request<{ stages: StageItem[] }>("/api/verify", {
      method: "POST",
      body: JSON.stringify({ source, target, stop_after: stopAfter }),
    }),
  defaultProfile: () => request<RuleProfile>("/api/profile/default"),
  profileSchema: () => request<Record<string, unknown>>("/api/profile/schema"),
  profileList: () =>
    request<{
      profiles: {
        filename: string
        profile_id: string
        name: string
        version: number
        status: string
        reference: string
      }[]
    }>("/api/profile/list").then((r) => r.profiles),
  profileItem: (filename: string) =>
    request<RuleProfile>(`/api/profile/item/${encodeURIComponent(filename)}`),
  profileDelete: (filename: string) =>
    request<{ deleted: string }>(
      `/api/profile/item/${encodeURIComponent(filename)}`,
      { method: "DELETE" },
    ),
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
  historyList: () =>
    request<{ records: Omit<HistoryRecord, "report">[] }>("/api/history/list").then(
      (r) => r.records,
    ),
  historyItem: (recordId: string) =>
    request<HistoryRecord>(`/api/history/item/${encodeURIComponent(recordId)}`),
}
