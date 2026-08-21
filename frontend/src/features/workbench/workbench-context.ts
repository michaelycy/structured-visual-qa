import { createContext } from "react"
import type { CompareResponse, HistoryRecord, SampleRecord } from "../../api"

export interface DocumentSelection {
  path: string
  display: string
}

export interface WorkbenchContextValue {
  source: DocumentSelection
  target: DocumentSelection
  result: CompareResponse | null
  reportKey: number
  busy: boolean
  progressText: string
  elapsed: number
  historyRecordId: string | null
  historyRefreshToken: number
  glossaryReference: string | null
  profileFilename: string | null
  sourcePassword: string
  targetPassword: string
  setSource: (value: DocumentSelection) => void
  setTarget: (value: DocumentSelection) => void
  setGlossaryReference: (value: string | null) => void
  setProfileFilename: (value: string | null) => void
  setSourcePassword: (value: string) => void
  setTargetPassword: (value: string) => void
  runCompare: () => Promise<void>
  runDemo: () => Promise<void>
  cancelWaiting: () => void
  reopenHistory: (record: HistoryRecord) => void
  restoreHistory: (record: HistoryRecord) => void
  rerunHistory: (
    record: HistoryRecord,
    profile: string | null,
    passwords: { source: string; target: string },
  ) => void
  useSample: (sample: SampleRecord) => void
}

export const WorkbenchContext = createContext<WorkbenchContextValue | null>(null)
