import { QueryClient } from "@tanstack/react-query"
import { documentQaService } from "../api"
import type { Glossary, QAReport, ReviewDecision, RuleProfile } from "../api"

/** 全局服务端状态客户端：默认立即过期，保留去重、错误和失效能力。 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 0, gcTime: 5 * 60_000, retry: 1 },
    mutations: { retry: 0 },
  },
})

export const queryKeys = {
  files: ["files"] as const,
  glossaries: ["glossaries"] as const,
  glossary: (filename: string) => ["glossaries", filename] as const,
  profiles: ["profiles"] as const,
  profile: (filename: string) => ["profiles", filename] as const,
  history: ["history"] as const,
  historyItem: (recordId: string) => ["history", recordId] as const,
  samples: ["samples"] as const,
  task: (taskId: string) => ["tasks", taskId] as const,
  review: (taskId: string) => ["reviews", taskId] as const,
}

function query<T>(queryKey: readonly unknown[], queryFn: () => Promise<T>): Promise<T> {
  return queryClient.fetchQuery({ queryKey, queryFn })
}

function mutate<T>(
  mutationKey: readonly unknown[],
  mutationFn: () => Promise<T>,
  invalidate: readonly (readonly unknown[])[] = [],
): Promise<T> {
  return queryClient.getMutationCache().build<T, Error, void, unknown>(queryClient, {
    mutationKey,
    mutationFn,
    onSuccess: async () => {
      await Promise.all(invalidate.map((queryKey) => queryClient.invalidateQueries({ queryKey })))
    },
  }).execute(undefined)
}

/** Query API 门面：组件不接触 fetch，并共享缓存键、错误和失效规则。 */
export const api = {
  compare: (...args: Parameters<typeof documentQaService.compare>) =>
    mutate(["compare"], () => documentQaService.compare(...args), [queryKeys.history]),
  glossaryDefault: () => query(["glossaries", "default"], documentQaService.glossaryDefault),
  glossaryList: () => query(queryKeys.glossaries, documentQaService.glossaryList),
  glossaryItem: (filename: string) =>
    query(queryKeys.glossary(filename), () => documentQaService.glossaryItem(filename)),
  glossarySave: (glossary: Glossary) =>
    mutate(["glossaries", "save"], () => documentQaService.glossarySave(glossary), [queryKeys.glossaries]),
  glossaryDelete: (filename: string) =>
    mutate(["glossaries", "delete", filename], () => documentQaService.glossaryDelete(filename), [queryKeys.glossaries]),
  task: (taskId: string) => query(queryKeys.task(taskId), () => documentQaService.task(taskId)),
  exportReport: (recordId: string, format: "xlsx" | "html") =>
    mutate(["reports", "export", recordId, format], () => documentQaService.exportReport(recordId, format)),
  verify: (...args: Parameters<typeof documentQaService.verify>) =>
    mutate(["verify"], () => documentQaService.verify(...args)),
  defaultProfile: () => query(["profiles", "default"], documentQaService.defaultProfile),
  profileSchema: () => query(["profiles", "schema"], documentQaService.profileSchema),
  profileList: () => query(queryKeys.profiles, documentQaService.profileList),
  profileItem: (filename: string) =>
    query(queryKeys.profile(filename), () => documentQaService.profileItem(filename)),
  profileDelete: (filename: string) =>
    mutate(["profiles", "delete", filename], () => documentQaService.profileDelete(filename), [queryKeys.profiles]),
  profilePublish: (filename: string) =>
    mutate(["profiles", "publish", filename], () => documentQaService.profilePublish(filename), [queryKeys.profiles]),
  saveProfile: (profile: RuleProfile) =>
    mutate(["profiles", "save"], () => documentQaService.saveProfile(profile), [queryKeys.profiles]),
  sampleFiles: () => query(queryKeys.files, documentQaService.sampleFiles),
  reviewDecision: (
    taskId: string,
    report: QAReport,
    issueId: string,
    decision: ReviewDecision,
    note = "",
  ) => mutate(
    ["reviews", "decision", taskId, issueId],
    () => documentQaService.reviewDecision(taskId, report, issueId, decision, note),
    [queryKeys.review(taskId)],
  ),
  reviewTask: (taskId: string) =>
    query(queryKeys.review(taskId), () => documentQaService.reviewTask(taskId)),
  reviewInsight: () => query(["insights", "review"], documentQaService.reviewInsight),
  tuningSuggestions: () =>
    query(["insights", "review", "suggestions"], documentQaService.tuningSuggestions),
  aiRepairReport: () =>
    query(["insights", "review", "repair-report"], documentQaService.aiRepairReport),
  downloadAIRepairReport: (clusterIds: string[]) =>
    documentQaService.downloadAIRepairReport(clusterIds),
  historyList: () => query(queryKeys.history, documentQaService.historyList),
  historyItem: (recordId: string) =>
    query(queryKeys.historyItem(recordId), () => documentQaService.historyItem(recordId)),
  sampleList: (includeArchived = false) =>
    query([...queryKeys.samples, includeArchived], () => documentQaService.sampleList(includeArchived)),
  sampleCreate: (...args: Parameters<typeof documentQaService.sampleCreate>) =>
    mutate(["samples", "create"], () => documentQaService.sampleCreate(...args), [queryKeys.samples, queryKeys.files]),
  sampleUpdate: (...args: Parameters<typeof documentQaService.sampleUpdate>) =>
    mutate(["samples", "update", args[0]], () => documentQaService.sampleUpdate(...args), [queryKeys.samples]),
  sampleArchive: (sampleId: string) =>
    mutate(["samples", "archive", sampleId], () => documentQaService.sampleArchive(sampleId), [queryKeys.samples]),
  sampleUse: (sampleId: string) =>
    mutate(["samples", "use", sampleId], () => documentQaService.sampleUse(sampleId)),
  uploadDocument: (file: File) =>
    mutate(["files", "upload", file.name], () => documentQaService.uploadDocument(file)),
  samplePath: (name: string) =>
    query(["files", "sample", name], () => documentQaService.samplePath(name)),
}
