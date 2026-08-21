import { useEffect, useRef, useState } from "react"
import { Button, Drawer, Empty, Layout, Menu, message, Tag, Typography } from "antd"
import { useLocation, useNavigate } from "@tanstack/react-router"
import {
  BookOutlined,
  ControlOutlined,
  FolderOpenOutlined,
  FileSearchOutlined,
  HistoryOutlined,
  MenuOutlined,
} from "@ant-design/icons"
import type { CompareResponse, HistoryRecord, SampleRecord, TaskPollResponse } from "./api"
import { api } from "./services/queryClient"
import { ReportDetail } from "./views/ReportDetail"
import { ProfileManager } from "./views/ProfileManager"
import { GlossaryManager } from "./views/GlossaryManager"
import { CompareBar } from "./views/CompareBar"
import { HistoryView } from "./views/HistoryView"
import { SampleManager } from "./views/SampleManager"
import { STATUS_META } from "./uiTokens"
import "./workbench.css"

const { Sider, Content } = Layout
const { Title, Text } = Typography

/** 一级导航：工作台（比较任务全流程）与配置管理。 */
type Section = "workbench" | "history" | "samples" | "manager" | "glossary"

const NAV_ITEMS = [
  { key: "workbench", icon: <FileSearchOutlined />, label: "工作台" },
  { key: "history", icon: <HistoryOutlined />, label: "质检记录" },
  { key: "samples", icon: <FolderOpenOutlined />, label: "样本管理" },
  { key: "manager", icon: <ControlOutlined />, label: "规则管理" },
  { key: "glossary", icon: <BookOutlined />, label: "术语库" },
]

const SECTION_LABEL: Record<Section, string> = {
  workbench: "工作台",
  history: "质检记录",
  samples: "样本管理",
  manager: "规则管理",
  glossary: "术语库",
}

const SECTION_PATH: Record<Section, "/" | "/history" | "/samples" | "/rules" | "/glossary"> = {
  workbench: "/",
  history: "/history",
  samples: "/samples",
  manager: "/rules",
  glossary: "/glossary",
}

const PATH_SECTION: Record<string, Section> = Object.fromEntries(
  Object.entries(SECTION_PATH).map(([section, path]) => [path, section]),
) as Record<string, Section>

/** 任务状态 → 进度文案（后端无阶段粒度，只做诚实的状态+耗时展示）。 */
const TASK_STATUS_TEXT: Record<string, string> = {
  queued: "排队中",
  running: "正在分析（解析 → 对齐 → 匹配 → 检测 → 报告）",
}

/** 应用骨架：antd Layout，左侧一级菜单承载工作台与各管理页面。 */
export function App() {
  // 浏览器安全模型不允许读取本地路径，选择器走上传模式：
  // state 保存服务器端路径，display 只用于界面展示。
  const [source, setSource] = useState({ path: "", display: "" })
  const [target, setTarget] = useState({ path: "", display: "" })
  const pathname = useLocation({ select: (location) => location.pathname })
  const navigate = useNavigate()
  const section = PATH_SECTION[pathname] ?? "workbench"
  const [viewportWidth, setViewportWidth] = useState(() => window.innerWidth)
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
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
  // 历史列表刷新令牌：比较落盘后触发重新拉取，避免列表停留在首次快照。
  const [historyRefreshToken, setHistoryRefreshToken] = useState(0)
  // 比较参数：术语库与规则配置（null = 内置默认）。
  const [glossaryReference, setGlossaryReference] = useState<string | null>(null)
  const [profileFilename, setProfileFilename] = useState<string | null>(null)
  // 打开密码（仅受保护 PDF）：只在本次请求内使用，不落历史记录。
  const [sourcePassword, setSourcePassword] = useState("")
  const [targetPassword, setTargetPassword] = useState("")
  const [messageApi, contextHolder] = message.useMessage()
  // 用户主动取消等待的标记与轮询定时器引用：取消时停止轮询。
  const cancelRef = useRef(false)
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    const updateViewport = () => setViewportWidth(window.innerWidth)
    window.addEventListener("resize", updateViewport)
    return () => window.removeEventListener("resize", updateViewport)
  }, [])

  const isMobile = viewportWidth < 768
  const isCompactSidebar = viewportWidth < 1280

  /** 一级导航在移动端选中后立即收起抽屉，避免遮挡目标页面。 */
  const selectSection = (next: Section) => {
    void navigate({ to: SECTION_PATH[next] })
    setMobileNavOpen(false)
  }

  /** 用户主动停止等待：任务仍在服务端执行，完成后照常落入质检记录。 */
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
    selectSection("workbench")
    setHistoryRecordId(recordId)
  }

  const runCompare = async (
    override?: {
      source: string
      target: string
      sourceDisplay?: string
      targetDisplay?: string
      /** 覆盖规则配置；undefined 沿用当前 state，null 强制用内置默认。 */
      profile?: string | null
      /** 覆盖术语库引用；undefined 沿用当前 state，null 强制不启用。 */
      glossary?: string | null
      /** 覆盖源/目标打开密码；undefined 沿用工作台输入，"" 视为无密码。 */
      sourcePassword?: string
      targetPassword?: string
    },
  ) => {
    // 引导按钮载入示例后立即试跑：路径与展示名以覆盖参数传入，
    // 避免依赖异步 setState 的时序。
    const src = override?.source ?? source.path
    const tgt = override?.target ?? target.path
    const srcDisplay = override?.sourceDisplay ?? source.display
    const tgtDisplay = override?.targetDisplay ?? target.display
    const profile = override?.profile !== undefined ? override.profile : profileFilename
    const glossary = override?.glossary !== undefined ? override.glossary : glossaryReference
    // 密码覆盖语义：undefined 沿用工作台输入，"" 视为无密码。
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
      // 同步模式直接带报告返回；异步模式轮询任务状态。
      if (submitted.report) {
        applyReport(
          { report: submitted.report, rendered: submitted.rendered },
          submitted.history_record_id ?? null,
        )
        setHistoryRefreshToken((n) => n + 1)
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
      setHistoryRefreshToken((n) => n + 1)
      messageApi.success(
        `比较完成：${poll.report.document_score.toFixed(1)} 分`,
      )
    } catch (exc) {
      const text = exc instanceof Error ? exc.message : String(exc)
      if (text === "__cancelled__") {
        messageApi.info("已停止等待。任务仍在后台执行，完成后可在「质检记录」中查看。")
      } else if (text === "__timeout__") {
        messageApi.warning("等待超过 5 分钟仍未完成，已停止等待；任务完成后可在「质检记录」中查看。")
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
      const [s, t] = await Promise.all([api.samplePath(en), api.samplePath(zh)])
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
    // 历史回看也要恢复报告上下文；即使旧记录缺少可重跑路径，仍展示真实文件名。
    setSource({ path: record.source_path ?? "", display: record.source_display })
    setTarget({ path: record.target_path ?? "", display: record.target_display })
    applyReport(
      {
        report: record.report,
        rendered: record.rendered ?? { source: [], target: [] },
      },
      record.record_id,
    )
    messageApi.info(`已载入 ${record.source_display} 的历史报告`)
  }

  /** 从质检记录重新执行比较：填回源/目标文档并立即运行。
   *
   * profile 为 null 时沿用工作台当前配置（用户可在弹窗选择不覆盖）；
   * 选了具体配置则同步更新工作台的下拉状态，保持界面与实际执行一致。
   * 密码不落历史：重比加密文档时由用户在弹窗重新输入，经覆盖参数传入。
   */
  const rerunHistory = (
    record: HistoryRecord,
    profile: string | null,
    passwords: { source: string; target: string },
  ) => {
    if (!record.source_path || !record.target_path) {
      messageApi.error("该记录缺少输入文档路径，无法重新比较")
      return
    }
    setSource({ path: record.source_path, display: record.source_display })
    setTarget({ path: record.target_path, display: record.target_display })
    if (profile !== null) setProfileFilename(profile)
    void runCompare({
      source: record.source_path,
      target: record.target_path,
      sourceDisplay: record.source_display,
      targetDisplay: record.target_display,
      profile: profile !== null ? profile : undefined,
      sourcePassword: passwords.source,
      targetPassword: passwords.target,
    })
  }

  /** 从样本库一次载入源、目标文档对，并返回工作台等待用户执行。 */
  const useSample = (sample: SampleRecord) => {
    setSource({ path: sample.source_path, display: sample.source_name })
    setTarget({ path: sample.target_path, display: sample.target_name })
    selectSection("workbench")
  }

  return (
    <Layout className="app-shell tw:min-h-dvh tw:bg-qa-canvas">
      {contextHolder}
      {!isMobile ? (
        <Sider
          className="app-shell__sider"
          theme="dark"
          width={260}
          collapsed={isCompactSidebar}
          collapsedWidth={72}
          trigger={null}
        >
          <div className="app-shell__brand">
            <Title level={5}>Visual QA</Title>
            {!isCompactSidebar ? <Text>翻译文档验收工作台</Text> : null}
          </div>
          <Menu
            theme="dark"
            mode="inline"
            selectedKeys={[section]}
            onClick={({ key }) => selectSection(key as Section)}
            items={NAV_ITEMS}
          />
        </Sider>
      ) : null}

      <Layout>
        {isMobile ? (
          <header className="app-mobile-header">
            <Button
              type="text"
              icon={<MenuOutlined />}
              aria-label="打开主导航"
              onClick={() => setMobileNavOpen(true)}
            />
            <strong>Visual QA</strong>
            <span>{SECTION_LABEL[section]}</span>
          </header>
        ) : null}
        <Drawer
          className="app-mobile-nav"
          placement="left"
          width={288}
          open={isMobile && mobileNavOpen}
          title="Visual QA"
          onClose={() => setMobileNavOpen(false)}
        >
          <Menu
            theme="dark"
            mode="inline"
            selectedKeys={[section]}
            onClick={({ key }) => selectSection(key as Section)}
            items={NAV_ITEMS}
          />
        </Drawer>
        <Content
          className={
            section === "workbench"
              ? "workbench-content"
              : section === "history"
                ? "app-content app-content--history"
                : "app-content"
          }
        >
          {section === "workbench" ? (
            <div className="workbench-page">
              <section className="workbench-taskbar">
                <div className="workbench-taskbar__identity">
                  <Text className="workbench-breadcrumb">工作台&nbsp; / &nbsp;报告详情</Text>
                  <div className="workbench-title-row">
                    <Title level={4} className="workbench-title">
                      {source.display && target.display ? "文档视觉对比报告" : "新建文档对比"}
                    </Title>
                    {result && (
                      <Tag
                        variant="filled"
                        className="workbench-status"
                        style={{
                          color: STATUS_META[result.report.status]?.color,
                          background: STATUS_META[result.report.status]?.background,
                        }}
                      >
                        {STATUS_META[result.report.status]?.label ?? result.report.status}
                      </Tag>
                    )}
                  </div>
                </div>
                <CompareBar
                  source={source}
                  target={target}
                  busy={busy}
                  glossaryReference={glossaryReference}
                  profileFilename={profileFilename}
                  sourcePassword={sourcePassword}
                  targetPassword={targetPassword}
                  onGlossary={setGlossaryReference}
                  onProfile={setProfileFilename}
                  onSourcePassword={setSourcePassword}
                  onTargetPassword={setTargetPassword}
                  onSource={setSource}
                  onTarget={setTarget}
                  onSubmit={() => void runCompare()}
                />
                {busy && (
                  <span className="workbench-progress">
                    <Typography.Text type="secondary">
                      {progressText} · 已耗时 {elapsed} 秒（大型文档可能需要一两分钟）
                    </Typography.Text>
                    <Button size="small" style={{ marginLeft: 12 }} onClick={cancelWaiting}>
                      停止等待
                    </Button>
                  </span>
                )}
              </section>
              <div className="workbench-detail-nav">
                <span>报告详情</span>
              </div>
              <div className="workbench-detail-content">
                {result ? (
                  <ReportDetail
                    key={reportKey}
                    report={result.report}
                    rendered={result.rendered}
                    historyRecordId={historyRecordId}
                  />
                ) : (
                  <Empty
                    className="workbench-empty"
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
                )}
              </div>
            </div>
          ) : section === "history" ? (
            <HistoryView
              refreshToken={historyRefreshToken}
              onReopen={reopenHistory}
              onRerun={rerunHistory}
              onStart={() => selectSection("workbench")}
            />
          ) : section === "samples" ? (
            <SampleManager onUse={useSample} />
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
