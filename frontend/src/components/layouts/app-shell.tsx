import { useEffect, useState } from "react"
import {
  BookOutlined,
  ControlOutlined,
  FileSearchOutlined,
  FolderOpenOutlined,
  HistoryOutlined,
  MenuOutlined,
} from "@ant-design/icons"
import { Link, Outlet, useLocation } from "@tanstack/react-router"
import { Button, Drawer, Layout, Menu } from "antd"

const { Sider, Content } = Layout

const NAV_ITEMS = [
  { key: "/", icon: <FileSearchOutlined aria-hidden="true" />, label: <Link to="/">工作台</Link> },
  { key: "/history", icon: <HistoryOutlined aria-hidden="true" />, label: <Link to="/history">质检记录</Link> },
  { key: "/samples", icon: <FolderOpenOutlined aria-hidden="true" />, label: <Link to="/samples">样本管理</Link> },
  { key: "/rules", icon: <ControlOutlined aria-hidden="true" />, label: <Link to="/rules">规则管理</Link> },
  { key: "/glossary", icon: <BookOutlined aria-hidden="true" />, label: <Link to="/glossary">术语库</Link> },
]

const PAGE_LABELS: Record<string, string> = {
  "/": "工作台",
  "/history": "质检记录",
  "/samples": "样本管理",
  "/rules": "规则管理",
  "/glossary": "术语库",
}

/** 全站统一壳层，只负责一级导航、响应式侧栏和页面出口。 */
export const AppShell = () => {
  const pathname = useLocation({ select: (location) => location.pathname })
  const [viewportWidth, setViewportWidth] = useState(() => window.innerWidth)
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const isMobile = viewportWidth < 768
  const isCompact = viewportWidth < 1280

  useEffect(() => {
    const updateViewport = () => setViewportWidth(window.innerWidth)
    window.addEventListener("resize", updateViewport)
    return () => window.removeEventListener("resize", updateViewport)
  }, [])

  const navigation = (
    <Menu
      className="app-shell__menu"
      theme="dark"
      mode="inline"
      selectedKeys={[pathname]}
      items={NAV_ITEMS}
      onClick={() => setMobileNavOpen(false)}
    />
  )

  return (
    <Layout className="app-shell">
      <a className="app-skip-link" href="#main-content">跳到主要内容</a>
      {!isMobile ? (
        <Sider
          className="app-shell__sider"
          theme="dark"
          width={260}
          collapsed={isCompact}
          collapsedWidth={72}
          trigger={null}
        >
          <div className="app-shell__brand" aria-label="Structured Visual QA">
            <span className="app-shell__brand-mark">VQ</span>
            {!isCompact ? (
              <span className="app-shell__brand-copy">
                <strong>Visual QA</strong>
                <small>翻译文档质检</small>
              </span>
            ) : null}
          </div>
          {navigation}
        </Sider>
      ) : null}

      <Layout className="app-shell__main">
        {isMobile ? (
          <header className="app-mobile-header">
            <Button
              type="text"
              icon={<MenuOutlined aria-hidden="true" />}
              aria-label="打开主导航"
              onClick={() => setMobileNavOpen(true)}
            />
            <strong>Visual QA</strong>
            <span>{PAGE_LABELS[pathname] ?? "文档质检"}</span>
          </header>
        ) : null}
        <Drawer
          className="app-mobile-nav"
          placement="left"
          size={288}
          open={isMobile && mobileNavOpen}
          title="Visual QA"
          onClose={() => setMobileNavOpen(false)}
        >
          {navigation}
        </Drawer>
        <Content id="main-content" className="app-shell__content" tabIndex={-1}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
