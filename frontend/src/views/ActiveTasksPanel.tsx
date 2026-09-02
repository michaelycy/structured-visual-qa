/** 任务动态面板：质检记录页展示进行中/最近失败的比较任务与流水线进度。 */

import { LoadingOutlined } from "@ant-design/icons"
import { Spin, Tag, Tooltip, Typography } from "antd"
import type { TaskProgress, TaskSummary } from "../api"

// 阶段步进顺序；ocr 与 detect 同属"逐页检测"阶段（OCR 是其中最慢的
// 一段，大文档的大部分等待时间都发生在这里），report 表示全部完成。
const PHASES = ["解析", "分组", "对齐", "匹配", "逐页检测", "渲染"] as const

const STAGE_PHASE: Record<TaskProgress["stage"], number> = {
  parse: 0,
  group: 1,
  alignment: 2,
  match: 3,
  ocr: 4,
  detect: 4,
  render: 5,
  report: 6,
}

const SIDE_LABELS = { source: "源文档", target: "目标文档" } as const

/** 把一条进度事件翻译成用户可读的一句话简报。 */
function progressBrief(progress: TaskProgress): string {
  const side = progress.side ? SIDE_LABELS[progress.side] : ""
  switch (progress.stage) {
    case "parse":
      return `${side}解析完成 · ${progress.pages ?? "?"} 页`
    case "group":
      return `${side}分组 · ${progress.regions ?? "?"} 个区域`
    case "alignment":
      return `页面配对 ${progress.pairs ?? "?"} 对`
    case "match":
      return `开始逐页比对 · 共 ${progress.pages ?? "?"} 页`
    case "ocr":
      return `OCR 识别 ${progress.index ?? "?"}/${progress.total ?? "?"} 页`
    case "detect":
      return progress.index
        ? `逐页检测 ${progress.index}/${progress.total ?? "?"} 页`
        : "逐页检测中"
    case "render":
      return `渲染${side}对比页 · ${progress.pages ?? "?"} 页`
    case "report":
      return "汇总评分中"
    default:
      return "处理中"
  }
}

/** 耗时格式化：分钟内精确到秒，超过一小时只到分钟。 */
function formatElapsed(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000))
  if (totalSeconds < 60) return `${totalSeconds} 秒`
  const minutes = Math.floor(totalSeconds / 60)
  if (minutes < 60) return `${minutes} 分 ${totalSeconds % 60} 秒`
  return `${Math.floor(minutes / 60)} 小时 ${minutes % 60} 分`
}

/** 单个任务的阶段步进器：已完成 ✓、进行中高亮、未到置灰。 */
function StageSteps({ progress }: { progress: TaskProgress | null }) {
  const current = progress ? STAGE_PHASE[progress.stage] : 0
  return (
    <span className="task-activity__steps" aria-label="流水线阶段">
      {PHASES.map((phase, index) => (
        <span
          key={phase}
          className={
            index < current
              ? "task-activity__step is-done"
              : index === current
                ? "task-activity__step is-active"
                : "task-activity__step"
          }
        >
          {phase}
        </span>
      ))}
    </span>
  )
}

/** 进行中/最近失败任务的一行动态。 */
function TaskRow({ task, now }: { task: TaskSummary; now: number }) {
  const active = task.status === "queued" || task.status === "running"
  return (
    <div className={`task-activity__row is-${task.status}`}>
      {task.status === "queued" ? (
        <Tag>排队中</Tag>
      ) : task.status === "running" ? (
        <Tag icon={<Spin indicator={<LoadingOutlined spin />} />} color="processing">
          执行中
        </Tag>
      ) : (
        <Tag color="error">失败</Tag>
      )}
      <Tooltip title={`${task.source_display} → ${task.target_display}`}>
        <span className="task-activity__docs">
          {task.source_display} → {task.target_display}
        </span>
      </Tooltip>
      {active ? (
        <>
          <StageSteps progress={task.progress} />
          <Typography.Text type="secondary" className="task-activity__brief">
            {task.progress ? progressBrief(task.progress) : "等待任务启动"}
          </Typography.Text>
          <Typography.Text type="secondary" className="task-activity__elapsed">
            已 {formatElapsed(now - Date.parse(task.created_at))}
          </Typography.Text>
        </>
      ) : (
        <Tooltip title={task.error ?? ""}>
          <Typography.Text type="danger" className="task-activity__brief" ellipsis>
            {task.error ?? "任务失败"}
          </Typography.Text>
        </Tooltip>
      )}
    </div>
  )
}

/** 任务动态面板：只负责展示，数据与轮询由质检记录页持有。 */
export function ActiveTasksPanel({ tasks, now }: { tasks: TaskSummary[]; now: number }) {
  if (tasks.length === 0) return null
  return (
    <div className="task-activity" role="status">
      {tasks.map((task) => (
        <TaskRow key={task.task_id} task={task} now={now} />
      ))}
    </div>
  )
}
