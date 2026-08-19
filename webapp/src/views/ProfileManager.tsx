/** 规则管理页：antd Table + 编辑抽屉内嵌表单。 */

import { useCallback, useEffect, useState } from "react"
import { Button, Card, message, Popconfirm, Space, Table, Tag } from "antd"
import type { ColumnsType } from "antd/es/table"
import { api, type RuleProfile } from "../api"
import { ProfileEditor } from "./ProfileEditor"

interface ProfileListItem {
  filename: string
  profile_id: string
  name: string
  version: number
  status: string
  reference: string
}

const STATUS_COLOR: Record<string, string> = {
  published: "green",
  draft: "orange",
  archived: "default",
}

/** 新建/编辑共用的加载器封装。 */
function useProfileLoader() {
  const [editing, setEditing] = useState<RuleProfile | null>(null)
  const startNew = () =>
    api
      .defaultProfile()
      .then((profile) =>
        setEditing({
          ...profile,
          profile_id: "custom-rules",
          name: "自定义规则",
          version: 1,
        }),
      )
      .catch(() => message.error("无法加载默认配置"))
  const startEdit = (filename: string) =>
    api.profileItem(filename).then(setEditing).catch(() => message.error("读取失败"))
  const startFork = (filename: string) =>
    api
      .profileItem(filename)
      .then((profile) =>
        setEditing({
          ...profile,
          profile_id: `${profile.profile_id}-copy`,
          name: `${profile.name}（副本）`,
        }),
      )
      .catch(() => message.error("读取失败"))
  return { editing, setEditing, startNew, startEdit, startFork }
}

export function ProfileManager() {
  const [profiles, setProfiles] = useState<ProfileListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [messageApi, contextHolder] = message.useMessage()
  const { editing, setEditing, startNew, startEdit, startFork } =
    useProfileLoader()

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

  const remove = async (filename: string, reference: string) => {
    try {
      await api.profileDelete(filename)
      messageApi.success(`已删除 ${reference}`)
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
        <Tag style={{ fontFamily: "monospace", fontSize: 12 }}>{value}</Tag>
      ),
    },
    { title: "版本", dataIndex: "version", width: 70, render: (v: number) => `v${v}` },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (value: string) => (
        <Tag color={STATUS_COLOR[value] ?? "default"}>{value}</Tag>
      ),
    },
    {
      title: "引用",
      dataIndex: "reference",
      render: (value: string) => (
        <span style={{ fontFamily: "monospace", fontSize: 12 }}>{value}</span>
      ),
    },
    {
      title: "操作",
      width: 220,
      render: (_, record) => (
        <Space size={4}>
          <Button type="link" size="small" onClick={() => void startEdit(record.filename)}>
            编辑
          </Button>
          <Button type="link" size="small" onClick={() => void startFork(record.filename)}>
            复制派生
          </Button>
          <Popconfirm
            title={`确定删除 ${record.reference}？`}
            description="此操作不可恢复。"
            okText="删除"
            okButtonProps={{ danger: true }}
            onConfirm={() => void remove(record.filename, record.reference)}
          >
            <Button type="link" size="small" danger>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Card
      title="规则配置管理"
      extra={
        <Button type="primary" onClick={startNew}>
          新建配置
        </Button>
      }
    >
      {contextHolder}
      <Table
        size="small"
        rowKey="filename"
        loading={loading}
        columns={columns}
        dataSource={profiles}
        pagination={false}
        locale={{
          emptyText: "尚未保存任何规则配置。点击「新建配置」从内置平衡配置起步。",
        }}
      />
      {editing && (
        <Card
          size="small"
          title={`编辑：${editing.name ?? editing.profile_id}`}
          style={{ marginTop: 16 }}
          extra={
            <Button size="small" onClick={() => setEditing(null)}>
              关闭
            </Button>
          }
        >
          <ProfileEditor
            initial={editing}
            onSaved={(reference) => {
              messageApi.success(`已保存 ${reference}`)
              setEditing(null)
              refresh()
            }}
          />
        </Card>
      )}
    </Card>
  )
}
