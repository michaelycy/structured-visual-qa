import { useEffect, useRef, useState } from "react"
import { Button, Card, Empty, Layout, Menu, message, Tabs, Typography } from "antd"
import {
  BookOutlined,
  ControlOutlined,
  FileSearchOutlined,
} from "@ant-design/icons"
import type { CompareResponse, HistoryRecord, TaskPollResponse } from "./api"
import { api } from "./api"
import { ReportDetail } from "./views/ReportDetail"
import { ProfileManager } from "./views/ProfileManager"
import { GlossaryManager } from "./views/GlossaryManager"
import { CompareBar } from "./views/CompareBar"
import { HistoryView } from "./views/HistoryView"

const { Sider, Content } = Layout
const { Title, Text } = Typography

/** 一级导航：工作台（比较任务全流程）与配置管理。 */
type Section = "workbench" | "manager" | "glossary"

/** 任务状态 → 进度文案（后端无阶段粒度，只做诚实的状态+耗时展示）。 */
const TASK_STATUS_TEXT: Record<string, string> = {
  queued: "排队中",
  running: "正在分析（解析 → 对齐 → 匹配 → 检测 → 报告）",
}

/** 应用骨架：antd Layout，左侧一级菜单，工作台内部用 Tabs。 */
export function App() {
  // 浏览器安全模型不允许读取本地路径，选择器走上传模式：
  // state 保存服务器端路径，display 只用于界面展示。
  const [source, setSource] = useState({ path: "", display: "" })
  const [target, setTarget] = useState({ path: "", display: "" })
  const [section, setSection] = useState<Section>("workbench")
  const [activeTab, setActiveTab] = useState("detail")
  const [result, setResult] = useState<CompareResponse | null>(null)
  // 报告身份计数：ReportDetail 需按报告重挂载，否则逐页详情的
  // 页码选择与筛选条件会残留在下一份报告上（页数变少时显示空态）。
  const [reportKey, setReportKey] = useState(0)
  const [busy, setBusy] = useState(false)
  // 比较进行中的状态文案与已耗时秒数：让等待可感知。
  const [progressText, setProgressText] = useState("")
  const [elapsed, setElapsed] = useState(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  // 导出锚点：异步比较完成后保存 history_record_id。
  const [historyRecordId, setHistoryRecordId] = useState<string | null>(null)
  // 比较参数：术语库与规则配置（null = 内置默认）。
  const [glossaryReference, setGlossaryReference] = useState<string | null>(null)
  const [profileFilename, setProfileFilename] = useState<string | null>(null)
  const [messageApi, contextHolder] = message.useMessage()
  // 用户主动取消等待的标记与轮询定时器引用：取消时停止轮询。
  const cancelRef = useRef(false)
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  /** 用户主动停止等待：任务仍在服务端执行，完成后照常落入对比记录。 */
  const cancelWaiting = () => {
    cancelRef.current = true
    if (pollTimerRef.current) clearInterval(pollTimerRef.current)
  }

  // 比较期间每秒刷新耗时；结束时清理。
  useEffect(() => {
    if (busy) {
      setElapsed(0)
      timerRef.current = setInterval(() => setElapsed((n) => n + 1), 1000)
    } else if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [busy])

  const applyReport = (
    response: { report: CompareResponse["report"]; rendered?: CompareResponse["rendered"] },
    recordId: string | null,
  ) => {
    setResult({
      report: response.report,
      rendered: response.rendered ?? { source: [], target: [] },
    })
    setReportKey((n) => n + 1)
    setSection("workbench")
    setActiveTab("detail")
    setHistoryRecordId(recordId)
  }

  const runCompare = async (
    override?: {
      source: string
      target: string
      sourceDisplay?: string
      targetDisplay?: string
    },
  ) => {
    // 引导按钮载入示例后立即试跑：路径与展示名以覆盖参数传入，
    // 避免依赖异步 setState 的时序。
    const src = override?.source ?? source.path
    const tgt = override?.target ?? target.path
    const srcDisplay = override?.sourceDisplay ?? source.display
    const tgtDisplay = override?.targetDisplay ?? target.display
    setBusy(true)
    setProgressText("已提交，等待任务启动")
    cancelRef.current = false
    try {
      const submitted = await api.compare(
        src,
        tgt,
        srcDisplay,
        tgtDisplay,
        glossaryReference,
        true,
        profileFilename,
      )
      // 同步模式直接带报告返回；异步模式轮询任务状态。
      if (submitted.report) {
        applyReport(
          { report: submitted.report, rendered: submitted.rendered },
          null,
        )
        messageApi.success(
          `比较完成：${submitted.report.document_score.toFixed(1)} 分`,
        )
        return
      }
      if (!submitted.task_id) throw new Error("服务未返回任务")
      const poll = await new Promise<TaskPollResponse>((resolve, reject) => {
        let ticks = 0
        const timer = setInterval(() => {
          ticks += 1
          // 5 分钟仍未完成：停止轮询并明确告知结果去向，避免无限等待。
          if (ticks > 300) {
            clearInterval(timer)
            reject(new Error("__timeout__"))
            return
          }
          api
            .task(submitted.task_id!)
            .then((state) => {
              if (cancelRef.current) {
                clearInterval(timer)
                reject(new Error("__cancelled__"))
                return
              }
              setProgressText(TASK_STATUS_TEXT[state.status] ?? "处理中")
              if (state.status === "done") {
                clearInterval(timer)
                resolve(state)
              } else if (state.status === "error") {
                clearInterval(timer)
                reject(new Error(state.error ?? "比较失败"))
              }
            })
            .catch((exc) => {
              clearInterval(timer)
              reject(exc)
            })
        }, 1000)
        pollTimerRef.current = timer
      })
      if (!poll.report) throw new Error("任务完成但缺少报告")
      applyReport(
        { report: poll.report, rendered: poll.rendered ?? undefined },
        poll.history_record_id,
      )
      messageApi.success(
        `比较完成：${poll.report.document_score.toFixed(1)} 分`,
      )
    } catch (exc) {
      const text = exc instanceof Error ? exc.message : String(exc)
      if (text === "__cancelled__") {
        messageApi.info("已停止等待。任务仍在后台执行，完成后可在「对比记录」中查看。")
      } else if (text === "__timeout__") {
        messageApi.warning("等待超过 5 分钟仍未完成，已停止等待；任务完成后可在「对比记录」中查看。")
      } else {
        messageApi.error(text)
      }
    } finally {
      setBusy(false)
      setProgressText("")
      pollTimerRef.current = null
    }
  }

  /** 首次使用引导：一键载入内置示例对并立即试跑完整流程。 */
  const runDemo = async () => {
    try {
      const samples = await api.sampleFiles()
      const pick = (keyword: string) =>
        samples.find((name) => name.includes(keyword))
      const en = pick("en") ?? samples[0]
      const zh = pick("zh") ?? samples[1]
      if (!en || !zh) throw new Error("服务器上没有可用的示例文档")
      const load = (name: string) =>
        fetch(`/api/files/sample?name=${encodeURIComponent(name)}`, {
          method: "POST",
        }).then((r) => {
          if (!r.ok) throw new Error(`载入示例 ${name} 失败`)
          return r.json() as Promise<{ path: string; name: string }>
        })
      const [s, t] = await Promise.all([load(en), load(zh)])
      setSource({ path: s.path, display: s.name })
      setTarget({ path: t.path, display: t.name })
      void runCompare({
        source: s.path,
        target: t.path,
        sourceDisplay: s.name,
        targetDisplay: t.name,
      })
    } catch (exc) {
      messageApi.error(exc instanceof Error ? exc.message : String(exc))
    }
  }

  const reopenHistory = (record: HistoryRecord) => {
    if (!record.report) return
    applyReport(
      {
        report: record.report,
        rendered: record.rendered ?? { source: [], target: [] },
      },
      record.record_id,
    )
    messageApi.info(`已载入 ${record.source_display} 的历史报告`)
  }

  return (
    <Layout style={{ minHeight: "100dvh" }}>
      {contextHolder}
      <Sider theme="dark" width={192} breakpoint="lg" collapsedWidth={64}>
        <div style={{ padding: "20px 16px 12px" }}>
          <Title level={5} style={{ color: "#fff", margin: 0 }}>
            Visual QA
          </Title>
          <Text style={{ color: "rgba(255,255,255,0.45)", fontSize: 12 }}>
            翻译文档验收工作台
          </Text>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[section]}
          onClick={({ key }) => setSection(key as Section)}
          items={[
            { key: "workbench", icon: <FileSearchOutlined />, label: "工作台" },
            { key: "manager", icon: <ControlOutlined />, label: "规则管理" },
            { key: "glossary", icon: <BookOutlined />, label: "术语库" },
          ]}
        />
      </Sider>

      <Layout>
        <Content style={{ padding: 24 }}>
          {section === "workbench" ? (
            <>
              <Card size="small" style={{ marginBottom: 16 }}>
                <CompareBar
                  source={source}
                  target={target}
                  busy={busy}
                  glossaryReference={glossaryReference}
                  profileFilename={profileFilename}
                  onGlossary={setGlossaryReference}
                  onProfile={setProfileFilename}
                  onSource={setSource}
                  onTarget={setTarget}
                  onSubmit={() => void runCompare()}
                />
                {busy && (
                  <span style={{ display: "block", marginTop: 8, fontSize: 13 }}>
                    <Typography.Text type="secondary">
                      {progressText} · 已耗时 {elapsed} 秒（大型文档可能需要一两分钟）
                    </Typography.Text>
                    <Button size="small" style={{ marginLeft: 12 }} onClick={cancelWaiting}>
                      停止等待
                    </Button>
                  </span>
                )}
              </Card>
              <Tabs
                activeKey={activeTab}
                onChange={setActiveTab}
                items={[
                  {
                    key: "detail",
                    label: "报告详情",
                    children: result ? (
                      <ReportDetail
                        key={reportKey}
                        report={result.report}
                        rendered={result.rendered}
                        historyRecordId={historyRecordId}
                      />
                    ) : (
                      <Empty
                        image={Empty.PRESENTED_IMAGE_SIMPLE}
                        description={
                          <span>
                            还没有报告。
                            <br />
                            上传原文与译文后点击「开始比较」，或先用内置示例体验完整流程。
                          </span>
                        }
                        style={{ padding: "32px 0" }}
                      >
                        <Button
                          type="primary"
                          loading={busy}
                          onClick={() => void runDemo()}
                        >
                          载入示例并试跑
                        </Button>
                      </Empty>
                    ),
                  },
                  {
                    key: "history",
                    label: "对比记录",
                    children: <HistoryView onReopen={reopenHistory} />,
                  },
                ]}
              />
            </>
          ) : section === "manager" ? (
            <ProfileManager />
          ) : (
            <GlossaryManager />
          )}
        </Content>
      </Layout>
    </Layout>
  )
}
