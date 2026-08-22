import { useEffect, useState } from "react"
import {
  BookOutlined,
  ControlOutlined,
  FileSearchOutlined,
  FolderOpenOutlined,
  HistoryOutlined,
  LeftOutlined,
  MenuOutlined,
  RightOutlined,
} from "@ant-design/icons"
import { Link, Outlet, useLocation } from "@tanstack/react-router"
import { Button, Drawer, Layout, Menu } from "antd"
import brandLogoUrl from "../../assets/logo.svg"

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
  // 手动收起状态（null = 未手动干预，跟随视口宽度自动收起/展开）。
  const [manualCollapsed, setManualCollapsed] = useState<boolean | null>(null)
  const isMobile = viewportWidth < 768
  const isCompact = viewportWidth < 1280
  // 用户手动收起/展开优先于响应式断点。
  const siderCollapsed = manualCollapsed ?? isCompact

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
          collapsed={siderCollapsed}
          collapsedWidth={72}
          trigger={null}
        >
          <div className="app-shell__brand">
            {siderCollapsed ? (
              /* 收起态只保留一个干净、居中的品牌标记，避免完整彩色 logo 在
               * 72px 窄栏里被裁切成一团失真的色块。 */
              <span className="app-shell__brand-tile" title="TransLint">
                <svg
                  className="app-shell__brand-tile__icon"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  role="img"
                  aria-label="TransLint"
                >
                  <circle cx="10" cy="10" r="6.2" />
                  <path d="M14.6 14.6L19.5 19.5" />
                  <path d="M7.4 10.2l1.8 1.8 3.6-3.7" />
                </svg>
              </span>
            ) : (
              <>
                <img
                  className="app-shell__brand-logo app-shell__brand-logo--expanded"
                  src={brandLogoUrl}
                  alt=""
                  width={300}
                  height={300}
                />
                <span className="app-brand-wordmark" aria-label="TransLint">
                  <span className="app-brand-wordmark__trans" aria-hidden="true">Trans</span>
                  <span className="app-brand-wordmark__lint" aria-hidden="true">Lint</span>
                </span>
              </>
            )}
          </div>
          {navigation}
          {/* 手动收起/展开：原生 button 自控布局，图标绝对居中、
              整行命中（antd Button 的图标包裹层会干扰宽度传导）。 */}
          <button
            type="button"
            className="app-shell__collapse-trigger"
            aria-label={siderCollapsed ? "展开侧边栏" : "收起侧边栏"}
            title={siderCollapsed ? "展开侧边栏" : "收起侧边栏"}
            onClick={() => setManualCollapsed(!siderCollapsed)}
          >
            {siderCollapsed ? (
              <RightOutlined aria-hidden="true" />
            ) : (
              <LeftOutlined aria-hidden="true" />
            )}
          </button>
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
            <img
              className="app-mobile-header__logo"
              src={brandLogoUrl}
              alt="TransLint"
              width={300}
              height={300}
            />
            <span>{PAGE_LABELS[pathname] ?? "文档质检"}</span>
          </header>
        ) : null}
        <Drawer
          className="app-mobile-nav"
          placement="left"
          size={288}
          open={isMobile && mobileNavOpen}
          title={
            <span className="app-mobile-nav__brand">
              <img
                className="app-mobile-nav__logo"
                src={brandLogoUrl}
                alt=""
                width={300}
                height={300}
              />
              <span className="app-brand-wordmark" aria-label="TransLint">
                <span className="app-brand-wordmark__trans" aria-hidden="true">Trans</span>
                <span className="app-brand-wordmark__lint" aria-hidden="true">Lint</span>
              </span>
            </span>
          }
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
