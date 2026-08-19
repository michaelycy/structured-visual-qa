import { useState } from "react"
import { Card, Layout, Menu, message, Tabs, Typography } from "antd"
import {
  BookOutlined,
  ControlOutlined,
  FileSearchOutlined,
} from "@ant-design/icons"
import type { CompareResponse, HistoryRecord, QAReport, ReviewDecision, TaskPollResponse } from "./api"
import { api } from "./api"
import { ReportOverview } from "./views/ReportOverview"
import { PageDetails } from "./views/PageDetails"
import { StageView } from "./views/StageView"
import { ProfileEditor } from "./views/ProfileEditor"
import { ProfileManager } from "./views/ProfileManager"
import { GlossaryManager } from "./views/GlossaryManager"
import { CompareBar } from "./views/CompareBar"
import { HistoryView } from "./views/HistoryView"

const { Sider, Content } = Layout
const { Title, Text } = Typography

/** 一级导航：工作台（比较任务全流程）与规则管理。 */
type Section = "workbench" | "manager" | "glossary"

/** 应用骨架：antd Layout，左侧一级菜单，工作台内部用 Tabs。 */
export function App() {
  // 浏览器安全模型不允许读取本地路径，选择器走上传模式：
  // state 保存服务器端路径，display 只用于界面展示。
  const [source, setSource] = useState({ path: "", display: "" })
  const [target, setTarget] = useState({ path: "", display: "" })
  const [section, setSection] = useState<Section>("workbench")
  const [result, setResult] = useState<CompareResponse | null>(null)
  const [busy, setBusy] = useState(false)
  // 复核闭环：比较完成后生成任务 ID，判定按 Issue 粒度持久化。
  const [taskId, setTaskId] = useState<string | null>(null)
  const [decisions, setDecisions] = useState<Record<string, ReviewDecision>>({})
  // 导出锚点：异步比较完成后保存 history_record_id。
  const [historyRecordId, setHistoryRecordId] = useState<string | null>(null)
  // 比较时可引用的术语库（id@version）；null 表示不启用术语检测。
  const [glossaryReference, setGlossaryReference] = useState<string | null>(null)
  const [messageApi, contextHolder] = message.useMessage()

  const applyReport = (
    response: { report: QAReport; rendered?: { source: string[]; target: string[] } },
    recordId: string | null,
  ) => {
    setResult({
      report: response.report,
      rendered: response.rendered ?? { source: [], target: [] },
    })
    setSection("workbench")
    setHistoryRecordId(recordId)
    // 复核任务 ID 由双方文档摘要组成，同一对文档的判定自然延续。
    const id = `${response.report.source_document_id.slice(0, 12)}-${response.report.target_document_id.slice(0, 12)}`
    setTaskId(id)
    setDecisions({})
    api
      .reviewTask(id)
      .then((record) =>
        setDecisions(
          Object.fromEntries(
            Object.entries(record.decisions).map(([k, v]) => [k, v.decision]),
          ),
        ),
      )
      .catch(() => undefined)
  }

  const runCompare = async () => {
    setBusy(true)
    try {
      const submitted = await api.compare(
        source.path,
        target.path,
        source.display,
        target.display,
        glossaryReference,
      )
      // 同步模式直接带报告返回；异步模式轮询任务状态。
      if (submitted.report) {
        applyReport(
          { report: submitted.report, rendered: submitted.rendered },
          null,
        )
        messageApi.success(
          `比较完成：${submitted.report.status} · ${submitted.report.document_score.toFixed(1)} 分`,
        )
        return
      }
      if (!submitted.task_id) throw new Error("服务未返回任务")
      const poll = await new Promise<TaskPollResponse>((resolve, reject) => {
        const timer = setInterval(() => {
          api
            .task(submitted.task_id!)
            .then((state) => {
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
      })
      if (!poll.report) throw new Error("任务完成但缺少报告")
      applyReport(
        { report: poll.report, rendered: poll.rendered ?? undefined },
        poll.history_record_id,
      )
      messageApi.success(
        `比较完成：${poll.report.status} · ${poll.report.document_score.toFixed(1)} 分`,
      )
    } catch (exc) {
      messageApi.error(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setBusy(false)
    }
  }

  const decide = (issueId: string, decision: ReviewDecision) => {
    if (!taskId || !result) return
    setDecisions((prev) => ({ ...prev, [issueId]: decision }))
    api
      .reviewDecision(taskId, result.report, issueId, decision)
      .catch((exc) => messageApi.error(exc instanceof Error ? exc.message : String(exc)))
  }

  const reopenHistory = (record: HistoryRecord) => {
    if (!record.report) return
    applyReport(
      { report: record.report, rendered: { source: [], target: [] } },
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
                  onGlossary={setGlossaryReference}
                  onSource={setSource}
                  onTarget={setTarget}
                  onSubmit={() => void runCompare()}
                />
              </Card>
              <Tabs
                defaultActiveKey="overview"
                items={[
                  {
                    key: "overview",
                    label: "报告总览",
                    children: result ? (
                      <ReportOverview
                        report={result.report}
                        historyRecordId={historyRecordId}
                      />
                    ) : (
                      <Text type="secondary">
                        选择源文档与目标文档后点击「开始比较」。
                      </Text>
                    ),
                  },
                  {
                    key: "pages",
                    label: "逐页详情",
                    children: result ? (
                      <PageDetails
                        report={result.report}
                        rendered={result.rendered}
                        taskId={taskId}
                        decisions={decisions}
                        onDecide={decide}
                      />
                    ) : (
                      <Text type="secondary">先执行一次比较，再查看逐页详情。</Text>
                    ),
                  },
                  {
                    key: "stages",
                    label: "分阶段验证",
                    children: (
                      <StageView source={source.path} target={target.path} />
                    ),
                  },
                  {
                    key: "history",
                    label: "对比记录",
                    children: <HistoryView onReopen={reopenHistory} />,
                  },
                  {
                    key: "profile",
                    label: "快速配置",
                    children: <ProfileEditor />,
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
