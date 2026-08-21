import { useContext } from "react"
import { WorkbenchContext } from "./workbench-context"

/** 读取工作台公开能力，供工作台、质检记录和样本页协作。 */
export const useWorkbench = () => {
  const context = useContext(WorkbenchContext)
  if (!context) throw new Error("useWorkbench 必须在 WorkbenchProvider 内使用")
  return context
}
