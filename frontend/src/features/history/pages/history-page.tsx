import { useNavigate } from "@tanstack/react-router"
import { HistoryView } from "../../../views/HistoryView"
import { useWorkbench } from "../../workbench"

/** 质检记录路由页。 */
export const HistoryPage = () => {
  const navigate = useNavigate()
  const workbench = useWorkbench()
  return (
    <HistoryView
      refreshToken={workbench.historyRefreshToken}
      busy={workbench.busy}
      progressText={workbench.progressText}
      onReopen={workbench.reopenHistory}
      onRerun={workbench.rerunHistory}
      onStart={() => void navigate({ to: "/" })}
    />
  )
}
