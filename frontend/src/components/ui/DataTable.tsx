import type { ReactNode } from "react"
import { Table } from "antd"
import type { TableProps } from "antd/es/table"
import { cn } from "../../lib/cn"
import { EmptyState } from "./EmptyState"

interface DataTableProps<RecordType extends object> extends TableProps<RecordType> {
  emptyTitle?: string
  emptyDescription?: string
  emptyAction?: ReactNode
}

/** 管理列表统一表格：集中控制密度、分页和空状态。 */
export function DataTable<RecordType extends object>({
  className,
  emptyTitle = "暂无数据",
  emptyDescription,
  emptyAction,
  locale,
  pagination,
  size = "middle",
  ...props
}: DataTableProps<RecordType>) {
  return (
    <Table<RecordType>
      {...props}
      className={cn("qa-data-table", className)}
      size={size}
      locale={{
        ...locale,
        emptyText: locale?.emptyText ?? (
          <EmptyState
            compact
            title={emptyTitle}
            description={emptyDescription}
            action={emptyAction}
          />
        ),
      }}
      pagination={
        pagination === false
          ? false
          : {
              pageSize: 10,
              showSizeChanger: false,
              showTotal: (total) => `共 ${total} 条`,
              ...pagination,
            }
      }
    />
  )
}
