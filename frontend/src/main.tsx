import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ConfigProvider } from 'antd'
import { QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from '@tanstack/react-router'

import './global.css'
import './components/ui/ui.css'
import { router } from './router.tsx'
import { queryClient } from './services/queryClient.ts'
import { PALETTE } from './uiTokens.ts'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
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
          motionDurationFast: '0.15s',
          motionDurationMid: '0.2s',
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
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </ConfigProvider>
  </StrictMode>,
)
