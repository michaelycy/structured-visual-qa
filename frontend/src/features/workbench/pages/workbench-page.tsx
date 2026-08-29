import { useEffect } from "react"
import { getRouteApi, useNavigate } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import { Alert, Button, Empty, Spin, Tag, Typography } from "antd"
import { LoadingOutlined } from "@ant-design/icons"
import { CompareBar } from "../../../views/CompareBar"
import { ReportDetail } from "../../../views/ReportDetail"
import type { PageDetailsViewState } from "../../../views/PageDetails"
import { STATUS_META } from "../../../uiTokens"
import { useWorkbench } from "../use-workbench"
import { historyReportQuery } from "../api/workbench-queries"

const { Title, Text } = Typography
const routeApi = getRouteApi("/")

/** 工作台路由页：组合文档选择、任务进度与完整报告。 */
export const WorkbenchPage = () => {
  const workbench = useWorkbench()
  const search = routeApi.useSearch()
  const navigate = useNavigate({ from: "/" })
  const {
    source,
    target,
    result,
    reportKey,
    busy,
    progressText,
    elapsed,
    historyRecordId,
    glossaryReference,
    profileFilename,
    sourcePassword,
    targetPassword,
  } = workbench
  const recordQuery = useQuery({
    ...historyReportQuery(search.record),
    enabled: Boolean(search.record && historyRecordId !== search.record),
  })

  useEffect(() => {
    if (recordQuery.data?.report && recordQuery.data.record_id !== historyRecordId) {
      workbench.restoreHistory(recordQuery.data)
    }
  }, [historyRecordId, recordQuery.data, workbench])

  const viewState: PageDetailsViewState = {
    page: search.page,
    issue: search.issue,
    issueNumber: search.issueNumber,
    sourceText: search.sourceText,
    severity: search.severity,
    issueType: search.issueType,
    review: search.review,
    issuePage: search.issuePage,
  }

  const updateViewState = (state: PageDetailsViewState) => {
    void navigate({
      replace: true,
      resetScroll: false,
      search: (current) => ({
        ...current,
        page: state.page,
        issue: state.issue,
        issueNumber: state.issueNumber,
        sourceText: state.sourceText,
        severity: state.severity,
        issueType: state.issueType,
        review: state.review,
        issuePage: state.issuePage,
      }),
    })
  }

  const renderReport = () => {
    if (result) {
      return (
        <ReportDetail
          key={reportKey}
          report={result.report}
          rendered={result.rendered}
          historyRecordId={historyRecordId}
          viewState={viewState}
          onViewStateChange={updateViewState}
          sourceDisplay={source.display}
          targetDisplay={target.display}
        />
      )
    }
    if (recordQuery.isPending && search.record) {
      return <Spin className="workbench-loading" description="正在恢复质检报告…" />
    }
    if (recordQuery.isError) {
      return (
        <Alert
          type="error"
          showIcon
          message="无法恢复质检报告"
          description="记录可能已被清理，或服务当前不可用。请检查服务状态后重试。"
          action={<Button onClick={() => void recordQuery.refetch()}>重新加载</Button>}
        />
      )
    }
    return (
      <Empty
        className="workbench-empty"
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={
          <span>
            还没有报告。<br />上传原文与译文后开始质检，或先用内置示例体验完整流程。
          </span>
        }
      >
        <Button type="primary" loading={busy} onClick={() => void workbench.runDemo()}>
          载入示例并试跑
        </Button>
      </Empty>
    )
  }

  return (
    <div className="workbench-page">
      <section className="workbench-taskbar">
        <div className="workbench-taskbar__identity">
          <Text className="workbench-breadcrumb">工作台&nbsp; / &nbsp;报告详情</Text>
          <div className="workbench-title-row">
            <Title level={1} className="workbench-title">
              {source.display && target.display ? "文档质检报告" : "新建文档质检"}
            </Title>
            {result ? (
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
            ) : null}
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
          onGlossary={workbench.setGlossaryReference}
          onProfile={workbench.setProfileFilename}
          onSourcePassword={workbench.setSourcePassword}
          onTargetPassword={workbench.setTargetPassword}
          onSource={workbench.setSource}
          onTarget={workbench.setTarget}
          onSubmit={() => void workbench.runCompare()}
        />
        {busy ? (
          <Alert
            className="workbench-progress"
            type="info"
            showIcon
            icon={<LoadingOutlined spin />}
            message={progressText || "正在提交质检任务"}
            description={`已耗时 ${elapsed} 秒；完成后将自动展示新报告，大型文档可能需要一两分钟。`}
            action={<Button size="small" onClick={workbench.cancelWaiting}>停止等待</Button>}
          />
        ) : null}
      </section>
      <h2 className="workbench-detail-nav"><span>报告详情</span></h2>
      <div className="workbench-detail-content">
        {renderReport()}
      </div>
    </div>
  )
}
