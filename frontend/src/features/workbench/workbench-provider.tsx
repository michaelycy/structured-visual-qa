import { useEffect, useRef, useState } from "react"
import { useNavigate } from "@tanstack/react-router"
import { message } from "antd"
import type { CompareResponse, HistoryRecord, SampleRecord, TaskPollResponse } from "../../api"
import { api } from "../../services/queryClient"
import { WorkbenchContext } from "./workbench-context"
import type { DocumentSelection, WorkbenchContextValue } from "./workbench-context"

interface CompareOverride {
  source: string
  target: string
  sourceDisplay?: string
  targetDisplay?: string
  profile?: string | null
  glossary?: string | null
  sourcePassword?: string
  targetPassword?: string
}

const TASK_STATUS_TEXT: Record<string, string> = {
  queued: "排队中",
  running: "正在分析（解析 → 对齐 → 匹配 → 检测 → 报告）",
}

const SCORE_FORMATTER = new Intl.NumberFormat(undefined, {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
})

/** 工作台业务状态容器：跨一级页面共享载入样本、历史回看和重跑能力。 */
export const WorkbenchProvider = (props: { children: React.ReactNode }) => {
  const { children } = props
  const navigate = useNavigate()
  const [source, setSource] = useState<DocumentSelection>({ path: "", display: "" })
  const [target, setTarget] = useState<DocumentSelection>({ path: "", display: "" })
  const [result, setResult] = useState<CompareResponse | null>(null)
  const [reportKey, setReportKey] = useState(0)
  const [busy, setBusy] = useState(false)
  const [progressText, setProgressText] = useState("")
  const [elapsed, setElapsed] = useState(0)
  const [historyRecordId, setHistoryRecordId] = useState<string | null>(null)
  const [historyRefreshToken, setHistoryRefreshToken] = useState(0)
  const [glossaryReference, setGlossaryReference] = useState<string | null>(null)
  const [profileFilename, setProfileFilename] = useState<string | null>(null)
  const [sourcePassword, setSourcePassword] = useState("")
  const [targetPassword, setTargetPassword] = useState("")
  const [messageApi, contextHolder] = message.useMessage()
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const cancelRef = useRef(false)
  const activeCompareRef = useRef(false)
  const cancelRejectRef = useRef<((reason: Error) => void) | null>(null)
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (busy) {
      setElapsed(0)
      timerRef.current = setInterval(() => setElapsed((value) => value + 1), 1000)
    } else if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [busy])

  const openWorkbench = (recordId?: string | null) =>
    void navigate({
      to: "/",
      search: recordId ? { record: recordId } : {},
    })

  const cancelWaiting = () => {
    cancelRef.current = true
    if (pollTimerRef.current) clearTimeout(pollTimerRef.current)
    // 清除定时器后不会再进入轮询回调，必须主动结束等待 Promise，
    // 否则 finally 无法执行，工作台会永久停留在 busy 状态。
    cancelRejectRef.current?.(new Error("__cancelled__"))
    cancelRejectRef.current = null
  }

  const applyReport = (
    response: { report: CompareResponse["report"]; rendered?: CompareResponse["rendered"] },
    recordId: string | null,
  ) => {
    setResult({
      report: response.report,
      rendered: response.rendered ?? { source: [], target: [] },
    })
    setReportKey((value) => value + 1)
    setHistoryRecordId(recordId)
    openWorkbench(recordId)
  }

  const executeCompare = async (override?: CompareOverride) => {
    // React 状态更新前仍可能发生连续点击；用同步引用阻止重复提交。
    if (activeCompareRef.current) return
    activeCompareRef.current = true
    const src = override?.source ?? source.path
    const tgt = override?.target ?? target.path
    const srcDisplay = override?.sourceDisplay ?? source.display
    const tgtDisplay = override?.targetDisplay ?? target.display
    const profile = override?.profile !== undefined ? override.profile : profileFilename
    const glossary = override?.glossary !== undefined ? override.glossary : glossaryReference
    const srcPassword = override?.sourcePassword !== undefined ? override.sourcePassword : sourcePassword
    const tgtPassword = override?.targetPassword !== undefined ? override.targetPassword : targetPassword
    setBusy(true)
    setProgressText("已提交，等待任务启动")
    cancelRef.current = false
    try {
      const submitted = await api.compare(
        src,
        tgt,
        srcDisplay,
        tgtDisplay,
        glossary,
        true,
        profile,
        srcPassword || null,
        tgtPassword || null,
      )
      if (submitted.report) {
        applyReport(
          { report: submitted.report, rendered: submitted.rendered },
          submitted.history_record_id ?? null,
        )
        setHistoryRefreshToken((value) => value + 1)
        messageApi.success(`质检完成：${SCORE_FORMATTER.format(submitted.report.document_score)} 分`)
        return
      }
      if (!submitted.task_id) throw new Error("服务未返回任务")
      const poll = await new Promise<TaskPollResponse>((resolve, reject) => {
        cancelRejectRef.current = reject
        let ticks = 0
        const pollOnce = () => {
          ticks += 1
          if (ticks > 300) {
            reject(new Error("__timeout__"))
            return
          }
          api.task(submitted.task_id!).then((state) => {
            if (cancelRef.current) {
              reject(new Error("__cancelled__"))
              return
            }
            setProgressText(TASK_STATUS_TEXT[state.status] ?? "处理中")
            if (state.status === "done") {
              resolve(state)
            } else if (state.status === "error") {
              reject(new Error(state.error ?? "质检失败"))
            } else {
              // 上一次查询完成后再计时，避免慢请求与下一次轮询重叠。
              pollTimerRef.current = setTimeout(pollOnce, 1000)
            }
          }).catch((error) => {
            reject(error)
          })
        }
        // 提交成功后立即获取一次状态，让用户无需等待首个轮询周期。
        pollOnce()
      })
      if (!poll.report) throw new Error("任务完成但缺少报告")
      applyReport(
        { report: poll.report, rendered: poll.rendered ?? undefined },
        poll.history_record_id,
      )
      setHistoryRefreshToken((value) => value + 1)
      messageApi.success(`质检完成：${SCORE_FORMATTER.format(poll.report.document_score)} 分`)
    } catch (error) {
      const text = error instanceof Error ? error.message : String(error)
      if (text === "__cancelled__") {
        messageApi.info("已停止等待。任务仍在后台执行，完成后可在「质检记录」中查看。")
      } else if (text === "__timeout__") {
        messageApi.warning("等待超过 5 分钟仍未完成，已停止等待；任务完成后可在「质检记录」中查看。")
      } else {
        messageApi.error(`${text}。请检查服务状态或输入文档后重试。`)
      }
    } finally {
      activeCompareRef.current = false
      setBusy(false)
      setProgressText("")
      pollTimerRef.current = null
      cancelRejectRef.current = null
    }
  }

  const runDemo = async () => {
    try {
      const samples = await api.sampleFiles()
      const en = samples.find((name) => name.includes("en")) ?? samples[0]
      const zh = samples.find((name) => name.includes("zh")) ?? samples[1]
      if (!en || !zh) throw new Error("服务器上没有可用的示例文档")
      const [sourceSample, targetSample] = await Promise.all([api.samplePath(en), api.samplePath(zh)])
      setSource({ path: sourceSample.path, display: sourceSample.name })
      setTarget({ path: targetSample.path, display: targetSample.name })
      void executeCompare({
        source: sourceSample.path,
        target: targetSample.path,
        sourceDisplay: sourceSample.name,
        targetDisplay: targetSample.name,
      })
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : String(error))
    }
  }

  const reopenHistory = (record: HistoryRecord) => {
    if (!record.report) return
    setSource({ path: record.source_path ?? "", display: record.source_display })
    setTarget({ path: record.target_path ?? "", display: record.target_display })
    applyReport(
      { report: record.report, rendered: record.rendered ?? { source: [], target: [] } },
      record.record_id,
    )
    messageApi.info(`已载入 ${record.source_display} 的历史报告`)
  }

  const restoreHistory = (record: HistoryRecord) => {
    if (!record.report) return
    setSource({ path: record.source_path ?? "", display: record.source_display })
    setTarget({ path: record.target_path ?? "", display: record.target_display })
    setResult({
      report: record.report,
      rendered: record.rendered ?? { source: [], target: [] },
    })
    setReportKey((value) => value + 1)
    setHistoryRecordId(record.record_id)
  }

  const rerunHistory: WorkbenchContextValue["rerunHistory"] = (record, profile, passwords) => {
    if (!record.source_path || !record.target_path) {
      messageApi.error("该记录缺少输入文档路径，无法重新质检")
      return
    }
    setSource({ path: record.source_path, display: record.source_display })
    setTarget({ path: record.target_path, display: record.target_display })
    if (profile !== null) setProfileFilename(profile)
    void executeCompare({
      source: record.source_path,
      target: record.target_path,
      sourceDisplay: record.source_display,
      targetDisplay: record.target_display,
      profile: profile !== null ? profile : undefined,
      sourcePassword: passwords.source,
      targetPassword: passwords.target,
    })
  }

  const useSample = (sample: SampleRecord) => {
    setSource({ path: sample.source_path, display: sample.source_name })
    setTarget({ path: sample.target_path, display: sample.target_name })
    openWorkbench(null)
  }

  const value: WorkbenchContextValue = {
    source,
    target,
    result,
    reportKey,
    busy,
    progressText,
    elapsed,
    historyRecordId,
    historyRefreshToken,
    glossaryReference,
    profileFilename,
    sourcePassword,
    targetPassword,
    setSource,
    setTarget,
    setGlossaryReference,
    setProfileFilename,
    setSourcePassword,
    setTargetPassword,
    runCompare: executeCompare,
    runDemo,
    cancelWaiting,
    reopenHistory,
    restoreHistory,
    rerunHistory,
    useSample,
  }

  return (
    <WorkbenchContext.Provider value={value}>
      {contextHolder}
      {children}
    </WorkbenchContext.Provider>
  )
}
