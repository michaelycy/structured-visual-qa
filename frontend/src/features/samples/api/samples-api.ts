import { httpClient } from "../../../services/httpClient"

export interface BuiltinSampleScanSummary {
  discovered: number
  created: number
  existing: number
  conflict_count: number
  conflicts: string[]
}

/** 请求服务端重新扫描内置样本目录。 */
export const rescanBuiltinSamples = () =>
  httpClient.json<BuiltinSampleScanSummary>("/api/samples/rescan", { method: "POST" })
