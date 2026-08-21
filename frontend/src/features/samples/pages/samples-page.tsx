import { SampleManager } from "../../../views/SampleManager"
import { useWorkbench } from "../../workbench"

/** 样本管理路由页。 */
export const SamplesPage = () => {
  const workbench = useWorkbench()
  return <SampleManager onUse={workbench.useSample} />
}
