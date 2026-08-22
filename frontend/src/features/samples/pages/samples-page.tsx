import { useMutation, useQueryClient } from "@tanstack/react-query"
import { SampleManager } from "../../../views/SampleManager"
import { useWorkbench } from "../../workbench"
import { rescanBuiltinSamples } from "../api/samples-api"

/** 样本管理路由页。 */
export const SamplesPage = () => {
  const workbench = useWorkbench()
  const queryClient = useQueryClient()
  const rescanMutation = useMutation({
    mutationKey: ["samples", "rescan"],
    mutationFn: rescanBuiltinSamples,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["samples"] }),
  })

  return (
    <SampleManager
      onUse={workbench.useSample}
      onRescan={() => rescanMutation.mutateAsync()}
      rescanning={rescanMutation.isPending}
    />
  )
}
