/** 与后端 api/dto.py 对齐的 DTO 与无状态业务服务。 */

import { httpClient } from "./services/httpClient"

export interface ReportSummary {
  pages: number
  passed_pages: number
  review_pages: number
  failed_pages: number
  issue_counts: Record<string, number>
  problem_total?: number | null
}

export interface Issue {
  id: string
  page: number
  type: string
  severity: "info" | "low" | "medium" | "high" | "critical"
  description: string
  source_region?: string | null
  target_region?: string | null
  bbox?: { x: number; y: number; width: number; height: number }
  metrics?: Record<string, unknown>
  /** 产出该问题的检测器标识；与 core schemas/issue.py 的 detector 字段对齐。 */
  detector?: string | null
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

/** 误报归因统计：单一 Issue 类型的复核结论分布（T21 P0）。 */
export interface IssueTypeInsight {
  issue_type: string
  detector: string
  severity: string
  confirmed: number
  false_positive: number
  ignored: number
  reviewed: number
  fp_rate: number
}

/** 复核判定的误报归因总览（/api/insights/review）。 */
export interface ReviewInsight {
  generated_at: string
  pair_count: number
  confirmed: number
  false_positive: number
  ignored: number
  unmatched: number
  by_type: IssueTypeInsight[]
}

/** 一条调优建议：阈值调整或严重度降级（/api/insights/review/suggestions）。 */
export interface TuningSuggestion {
  issue_type: string
  kind: "threshold" | "severity"
  field: string
  current_value: number | string | null
  proposed_value: number | string | null
  fp_samples: number
  confirmed_samples: number
  rationale: string
}

/** 调优建议总览：建议列表 + 可直接保存的 DRAFT Profile 草案。 */
export interface TuningAdvice {
  base_reference: string
  profile_basis: "stored" | "default"
  sample_count: number
  unmatched: number
  suggestions: TuningSuggestion[]
  proposed_profile: RuleProfile | null
  notes: string[]
}

/** AI 修复报告中的一组误报诊断任务。 */
export interface RepairCluster {
  cluster_id: string
  issue_type: string
  detector: string
  false_positive_count: number
  confirmed_count: number
  root_cause_status: "unverified"
  evidence_status: "ready" | "partial"
  suspected_stage: "parse" | "group" | "alignment" | "match" | "detect" | "report"
  suspected_code_locations: string[]
  investigation_questions: string[]
  metrics_summary: Record<string, { count: number; min: number | null; max: number | null }>
  representative_false_positives: Record<string, unknown>[]
  representative_confirmed: Record<string, unknown>[]
  rule_adjustment_available: boolean
  recommended_action: string
  regression_expectations: string[]
}

/** 面向代码修复 AI 的结构化误报诊断报告。 */
export interface AIRepairReport {
  schema_version: number
  purpose: "code_repair"
  generated_at: string
  pair_count: number
  reviewed: number
  confirmed: number
  false_positive: number
  ignored: number
  unmatched: number
  profile_references: string[]
  clusters: RepairCluster[]
  content_safety_notice: string
  operating_constraints: string[]
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
  problem_total?: number
  rule_profile_reference: string
  normalized_from?: Record<string, string | null> | null
  rendered?: { source: string[]; target: string[] } | null
  report?: QAReport
  /** 完整记录（historyItem）携带的服务器端路径，用于重新执行比较。 */
  source_path?: string | null
  target_path?: string | null
}

export interface SampleRecord {
  sample_id: string
  name: string
  description: string
  origin: "builtin" | "user"
  status: "active" | "archived"
  source_name: string
  source_path: string
  source_format: string
  target_name: string
  target_path: string
  target_format: string
  source_language: string
  target_language: string
  created_at: string
  updated_at: string
}

export interface CompareSubmitResponse {
  task_id: string | null
  status?: string
  report?: QAReport
  rendered?: { source: string[]; target: string[] }
  history_record_id?: string | null
}

export interface TaskPollResponse {
  task_id: string
  status: "queued" | "running" | "done" | "error"
  error: string | null
  report: QAReport | null
  rendered: { source: string[]; target: string[] } | null
  history_record_id: string | null
}

export const documentQaService = {
  compare: (
    source: string,
    target: string,
    sourceDisplay = "",
    targetDisplay = "",
    glossaryReference: string | null = null,
    render = true,
    profilePath: string | null = null,
    sourcePassword: string | null = null,
    targetPassword: string | null = null,
  ) =>
    httpClient.json<CompareSubmitResponse>("/api/compare", {
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
        source_password: sourcePassword,
        target_password: targetPassword,
      }),
    }),
  glossaryDefault: () => httpClient.json<Glossary>("/api/glossary/default"),
  glossaryList: () =>
    httpClient.json<{ glossaries: GlossarySummary[] }>("/api/glossary/list").then(
      (r) => r.glossaries,
    ),
  glossaryItem: (filename: string) =>
    httpClient.json<Glossary>(`/api/glossary/item/${encodeURIComponent(filename)}`),
  glossarySave: (glossary: Glossary) =>
    httpClient.json<{ path: string; reference: string }>("/api/glossary/save", {
      method: "POST",
      body: JSON.stringify({ glossary }),
    }),
  glossaryDelete: (filename: string) =>
    httpClient.json<{ deleted: string }>(
      `/api/glossary/item/${encodeURIComponent(filename)}`,
      { method: "DELETE" },
    ),
  task: (taskId: string) =>
    httpClient.json<TaskPollResponse>(`/api/tasks/${encodeURIComponent(taskId)}`),
  exportReport: (recordId: string, format: "xlsx" | "html") =>
    httpClient.blob("/api/report/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ record_id: recordId, format }),
    }),
  verify: (source: string, target: string, stopAfter: string) =>
    httpClient.json<{ stages: StageItem[] }>("/api/verify", {
      method: "POST",
      body: JSON.stringify({ source, target, stop_after: stopAfter }),
    }),
  defaultProfile: () => httpClient.json<RuleProfile>("/api/profile/default"),
  profileSchema: () => httpClient.json<Record<string, unknown>>("/api/profile/schema"),
  profileList: () =>
    httpClient.json<{
      profiles: {
        filename: string
        profile_id: string
        name: string
        version: number
        status: "draft" | "published" | "archived"
        reference: string
      }[]
    }>("/api/profile/list").then((r) => r.profiles),
  profileItem: (filename: string) =>
    httpClient.json<RuleProfile>(`/api/profile/item/${encodeURIComponent(filename)}`),
  profileDelete: (filename: string) =>
    httpClient.json<{ deleted: string }>(
      `/api/profile/item/${encodeURIComponent(filename)}`,
      { method: "DELETE" },
    ),
  profilePublish: (filename: string) =>
    httpClient.json<{ filename: string; reference: string; status: string }>(
      `/api/profile/item/${encodeURIComponent(filename)}/publish`,
      { method: "POST" },
    ),
  saveProfile: (profile: RuleProfile) =>
    httpClient.json<{ path: string; reference: string }>("/api/profile/save", {
      method: "POST",
      body: JSON.stringify({ profile }),
    }),
  sampleFiles: () =>
    httpClient.json<{ samples: string[] }>("/api/files/samples").then((r) => r.samples),
  reviewDecision: (
    taskId: string,
    report: QAReport,
    issueId: string,
    decision: ReviewDecision,
    note = "",
  ) =>
    httpClient.json<ReviewRecord>("/api/review/decision", {
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
  reviewTask: (taskId: string) => httpClient.json<ReviewRecord>(`/api/review/task/${taskId}`),
  reviewInsight: () => httpClient.json<ReviewInsight>("/api/insights/review"),
  tuningSuggestions: () => httpClient.json<TuningAdvice>("/api/insights/review/suggestions"),
  aiRepairReport: () => httpClient.json<AIRepairReport>("/api/insights/review/repair-report"),
  downloadAIRepairReport: (clusterIds: string[]) =>
    httpClient.blob("/api/insights/review/repair-report/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cluster_ids: clusterIds }),
    }),
  historyList: () =>
    httpClient.json<{ records: Omit<HistoryRecord, "report">[] }>("/api/history/list").then(
      (r) => r.records,
    ),
  historyItem: (recordId: string) =>
    httpClient.json<HistoryRecord>(`/api/history/item/${encodeURIComponent(recordId)}`),
  sampleList: (includeArchived = false) =>
    httpClient.json<{ samples: SampleRecord[] }>(
      `/api/samples?include_archived=${includeArchived}`,
    ).then((r) => r.samples),
  sampleCreate: async (
    name: string,
    description: string,
    sourceLanguage: string,
    targetLanguage: string,
    source: File,
    target: File,
  ) => {
    const body = new FormData()
    body.append("name", name)
    body.append("description", description)
    body.append("source_language", sourceLanguage)
    body.append("target_language", targetLanguage)
    body.append("source", source)
    body.append("target", target)
    return httpClient.form<SampleRecord>("/api/samples", body)
  },
  sampleUpdate: (
    sampleId: string,
    name: string,
    description: string,
    sourceLanguage: string,
    targetLanguage: string,
  ) =>
    httpClient.json<SampleRecord>(`/api/samples/${encodeURIComponent(sampleId)}`, {
      method: "PATCH",
      body: JSON.stringify({
        name,
        description,
        source_language: sourceLanguage,
        target_language: targetLanguage,
      }),
    }),
  sampleArchive: (sampleId: string) =>
    httpClient.json<{ archived: string }>(
      `/api/samples/${encodeURIComponent(sampleId)}`,
      { method: "DELETE" },
    ),
  sampleUse: (sampleId: string) =>
    httpClient.json<SampleRecord>(
      `/api/samples/${encodeURIComponent(sampleId)}/use`,
      { method: "POST" },
    ),
  uploadDocument: (file: File) => {
    const body = new FormData()
    body.append("file", file)
    return httpClient.form<{ path: string; name: string }>("/api/files/upload", body)
  },
  samplePath: (name: string) =>
    httpClient.json<{ path: string; name: string }>(
      `/api/files/sample?name=${encodeURIComponent(name)}`,
      { method: "POST" },
    ),
}
