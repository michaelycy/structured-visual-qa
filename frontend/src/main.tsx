import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from '@tanstack/react-router'

import './global.css'
import './components/ui/ui.css'
import './workbench.css'
import { AppProviders } from './app/providers/app-providers.tsx'
import { router } from './app/router/router.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>
  </StrictMode>,
)
