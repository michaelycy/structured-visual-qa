import type { ReactNode } from "react"
import { ConfigProvider } from "antd"
import { QueryClientProvider } from "@tanstack/react-query"
import { PALETTE } from "../../uiTokens"
import { queryClient } from "../../services/queryClient"

/** 应用级基础设施 Provider；业务状态由对应 feature 自己持有。 */
export const AppProviders = (props: { children: ReactNode }) => {
  const { children } = props
  return (
    <ConfigProvider
      theme={{
        token: {
          fontSize: 14,
          fontSizeSM: 12,
          controlHeight: 36,
          controlHeightSM: 32,
          borderRadius: 8,
          borderRadiusLG: 12,
          lineWidth: 1,
          motionDurationFast: "0.15s",
          motionDurationMid: "0.2s",
          colorPrimary: PALETTE.info,
          colorInfo: PALETTE.info,
          colorSuccess: PALETTE.success,
          colorWarning: PALETTE.warning,
          colorError: PALETTE.critical,
          colorText: PALETTE.text,
          colorTextSecondary: PALETTE.textSecondary,
          colorBorder: PALETTE.border,
          colorBorderSecondary: PALETTE.border,
          colorBgLayout: PALETTE.canvas,
          colorBgContainer: PALETTE.surface,
        },
        components: {
          Layout: {
            bodyBg: PALETTE.canvas,
            siderBg: PALETTE.sidebar,
            triggerBg: PALETTE.sidebar,
          },
          Menu: {
            darkItemBg: PALETTE.sidebar,
            darkSubMenuItemBg: PALETTE.sidebar,
            darkItemSelectedBg: PALETTE.info,
          },
        },
      }}
    >
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </ConfigProvider>
  )
}
