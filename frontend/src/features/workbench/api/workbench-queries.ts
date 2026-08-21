import { queryOptions } from "@tanstack/react-query"
import { documentQaService } from "../../../api"
import { queryKeys } from "../../../services/queryClient"

/** 按记录 ID 恢复完整报告，供工作台 URL 直达与刷新使用。 */
export const historyReportQuery = (recordId: string | undefined) =>
  queryOptions({
    queryKey: queryKeys.historyItem(recordId ?? "pending"),
    queryFn: () => documentQaService.historyItem(recordId!),
    enabled: Boolean(recordId),
  })
