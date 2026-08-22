/** 规则管理页：antd Table + 编辑抽屉内嵌表单。 */

import { useCallback, useEffect, useState } from "react"
import { Button, message, Popconfirm, Space, Tag } from "antd"
import type { ColumnsType } from "antd/es/table"
import type { RuleProfile } from "../api"
import { api } from "../services/queryClient"
import { ProfileEditor } from "./ProfileEditor"
import { PALETTE } from "../uiTokens"
import { DataTable, FormDrawer, PageHeader, PageSection } from "../components/ui"

interface ProfileListItem {
  filename: string
  profile_id: string
  name: string
  version: number
  status: "draft" | "published" | "archived"
  reference: string
}

interface EditingProfile {
  profile: RuleProfile
  title: string
  description: string
}

const STATUS_COLOR: Record<string, { color: string; background: string; label: string }> = {
  published: { color: PALETTE.success, background: PALETTE.successSoft, label: "已发布" },
  draft: { color: PALETTE.warning, background: PALETTE.warningSoft, label: "草稿" },
  archived: { color: PALETTE.textSecondary, background: PALETTE.canvas, label: "已归档" },
}

/** 生成未被现有规则家族占用的稳定标识。 */
function uniqueProfileId(profiles: ProfileListItem[], preferred: string) {
  const used = new Set(profiles.map((item) => item.profile_id))
  if (!used.has(preferred)) return preferred
  let suffix = 2
  while (used.has(`${preferred}-${suffix}`)) suffix += 1
  return `${preferred}-${suffix}`
}

/** 新建、派生和版本升级共用的加载器封装。 */
function useProfileLoader(profiles: ProfileListItem[]) {
  const [editing, setEditing] = useState<EditingProfile | null>(null)
  const startNew = () =>
    api
      .defaultProfile()
      .then((profile) =>
        setEditing({
          title: "新建规则",
          description: "从内置平衡配置开始创建草稿。",
          profile: {
            ...profile,
            profile_id: uniqueProfileId(profiles, "custom-rules"),
            name: "自定义规则",
            version: 1,
            status: "draft",
            description: "",
          },
        }),
      )
      .catch(() => message.error("无法加载默认配置"))
  const startEdit = (record: ProfileListItem) =>
    api
      .profileItem(record.filename)
      .then((profile) => {
        if (record.status === "draft") {
          setEditing({
            profile,
            title: "编辑规则",
            description: `正在编辑草稿 ${record.reference}。`,
          })
          return
        }
        const nextVersion = Math.max(
          ...profiles
            .filter((item) => item.profile_id === record.profile_id)
            .map((item) => item.version),
        ) + 1
        setEditing({
          title: "新建规则版本",
          description: `基于 ${record.reference} 创建不可冲突的新版本。`,
          profile: { ...profile, version: nextVersion, status: "draft" },
        })
      })
      .catch(() => message.error("读取失败"))
  const startFork = (filename: string) =>
    api
      .profileItem(filename)
      .then((profile) =>
        setEditing({
          title: "复制规则",
          description: `基于 ${profile.profile_id}@${profile.version} 创建独立规则。`,
          profile: {
            ...profile,
            profile_id: uniqueProfileId(profiles, `${profile.profile_id}-copy`),
            name: `${profile.name}（副本）`,
            version: 1,
            status: "draft",
          },
        }),
      )
      .catch(() => message.error("读取失败"))
  return { editing, setEditing, startNew, startEdit, startFork }
}

export function ProfileManager() {
  const [profiles, setProfiles] = useState<ProfileListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [messageApi, contextHolder] = message.useMessage()
  const { editing, setEditing, startNew, startEdit, startFork } = useProfileLoader(profiles)

  const refresh = useCallback(() => {
    setLoading(true)
    api
      .profileList()
      .then(setProfiles)
      .catch((exc) =>
        messageApi.error(exc instanceof Error ? exc.message : String(exc)),
      )
      .finally(() => setLoading(false))
  }, [messageApi])

  useEffect(refresh, [refresh])

  const archive = async (filename: string, reference: string) => {
    try {
      await api.profileDelete(filename)
      messageApi.success(`已归档 ${reference}`)
      refresh()
    } catch (exc) {
      messageApi.error(exc instanceof Error ? exc.message : String(exc))
    }
  }

  const publish = async (filename: string, reference: string) => {
    try {
      await api.profilePublish(filename)
      messageApi.success(`已发布 ${reference}`)
      refresh()
    } catch (exc) {
      messageApi.error(exc instanceof Error ? exc.message : String(exc))
    }
  }

  const columns: ColumnsType<ProfileListItem> = [
    { title: "名称", dataIndex: "name" },
    {
      title: "标识",
      dataIndex: "profile_id",
      render: (value: string) => (
        <Tag className="qa-code-value">{value}</Tag>
      ),
    },
    { title: "版本", dataIndex: "version", width: 70, render: (v: number) => `v${v}` },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (value: string) => {
        const meta = STATUS_COLOR[value]
        return (
          <Tag
            style={{
              color: meta?.color ?? PALETTE.textSecondary,
              background: meta?.background ?? PALETTE.canvas,
              borderColor: meta?.background ?? PALETTE.border,
            }}
          >
            {meta?.label ?? value}
          </Tag>
        )
      },
    },
    {
      title: "引用",
      dataIndex: "reference",
      render: (value: string) => (
        <span className="qa-code-value">{value}</span>
      ),
    },
    {
      title: "操作",
      width: 240,
      render: (_, record) => (
        <Space size={4}>
          <Button type="link" size="small" onClick={() => void startEdit(record)}>
            {record.status === "draft" ? "编辑" : "新建版本"}
          </Button>
          {record.status === "draft" ? (
            <Button type="link" size="small" onClick={() => void publish(record.filename, record.reference)}>
              发布
            </Button>
          ) : (
            <Button type="link" size="small" onClick={() => void startFork(record.filename)}>
              复制派生
            </Button>
          )}
          <Popconfirm
            title={`确定归档 ${record.reference}？`}
            description="归档后不再用于新质检，历史记录仍可复现。"
            okText="归档"
            okButtonProps={{ danger: true }}
            onConfirm={() => void archive(record.filename, record.reference)}
          >
            <Button type="link" size="small" danger>
              归档
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="qa-page management-page">
      {contextHolder}
      <PageHeader
        title="规则管理"
        meta={`· ${profiles.length} 个配置`}
        description="配置检测规则与阈值；草稿发布后不可覆盖，调整时创建新版本。"
        extra={
          <Button type="primary" onClick={startNew}>
            新建配置
          </Button>
        }
      />
      <PageSection className="management-page__section">
        <DataTable
          rowKey="filename"
          loading={loading}
          columns={columns}
          dataSource={profiles}
          pagination={false}
          emptyTitle="尚未保存规则配置"
          emptyDescription="新建配置可从内置平衡配置起步。"
        />
      </PageSection>
      <FormDrawer
        open={Boolean(editing)}
        title={editing?.title ?? "规则配置"}
        description={editing?.description}
        size={720}
        destroyOnHidden
        onClose={() => setEditing(null)}
      >
        {editing ? (
          <ProfileEditor
            initial={editing.profile}
            onSaved={(reference) => {
              messageApi.success(`已保存 ${reference}`)
              setEditing(null)
              refresh()
            }}
          />
        ) : null}
      </FormDrawer>
    </div>
  )
}
