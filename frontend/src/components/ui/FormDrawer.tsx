import type { ReactNode } from "react"
import { Drawer } from "antd"
import type { DrawerProps } from "antd"

interface FormDrawerProps extends Omit<DrawerProps, "children" | "title"> {
  title: string
  description?: string
  children: ReactNode
}

/** 表单抽屉统一外壳：固定标题层级、说明位置和内容宽度。 */
export function FormDrawer({
  title,
  description,
  children,
  size = 560,
  ...props
}: FormDrawerProps) {
  return (
    <Drawer
      {...props}
      className="qa-form-drawer"
      size={size}
      title={
        <span className="qa-form-drawer__title">
          <strong>{title}</strong>
          {description ? <small>{description}</small> : null}
        </span>
      }
    >
      {children}
    </Drawer>
  )
}
