/** 术语库管理页：列表 + 编辑器（新增/删除术语条目）。 */

import { useCallback, useEffect, useState } from "react"
import {
  Button,
  Card,
  Input,
  InputNumber,
  message,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from "antd"
import type { ColumnsType } from "antd/es/table"
import { api, type Glossary, type GlossarySummary } from "../api"

interface EntryRow {
  key: string
  term: string
  translations: string
  note: string
}

function glossaryToRows(glossary: Glossary): EntryRow[] {
  return glossary.entries.map((entry, index) => ({
    key: String(index),
    term: entry.term,
    translations: entry.translations.join(" / "),
    note: entry.note,
  }))
}

function rowsToGlossary(glossary: Glossary, rows: EntryRow[]): Glossary {
  return {
    ...glossary,
    entries: rows
      .filter((row) => row.term.trim() && row.translations.trim())
      .map((row) => ({
        term: row.term.trim(),
        translations: row.translations
          .split("/")
          .map((item) => item.trim())
          .filter(Boolean),
        note: row.note,
        case_sensitive: false,
      })),
  }
}

/** 术语库编辑器：元信息 + 可编辑条目表格。 */
function GlossaryEditor({
  initial,
  onSaved,
}: {
  initial: Glossary
  onSaved: (reference: string) => void
}) {
  const [glossary, setGlossary] = useState<Glossary>(initial)
  const [rows, setRows] = useState<EntryRow[]>(glossaryToRows(initial))
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const [messageApi, contextHolder] = message.useMessage()

  useEffect(() => {
    setGlossary(initial)
    setRows(glossaryToRows(initial))
  }, [initial])

  const save = async () => {
    setBusy(true)
    setError("")
    try {
      const saved = await api.glossarySave(rowsToGlossary(glossary, rows))
      messageApi.success(`已保存 ${saved.reference}`)
      onSaved(saved.reference)
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setBusy(false)
    }
  }

  const updateRow = (key: string, field: keyof EntryRow, value: string) => {
    setRows((prev) =>
      prev.map((row) => (row.key === key ? { ...row, [field]: value } : row)),
    )
  }

  return (
    <Card size="small" title="编辑术语库" style={{ marginTop: 16 }}>
      {contextHolder}
      {error && (
        <Typography.Paragraph type="danger" style={{ fontSize: 13 }}>
          {error}
        </Typography.Paragraph>
      )}
      <Space direction="vertical" size={8} style={{ width: "100%" }}>
        <Space wrap>
          <Input
            placeholder="术语库名称"
            value={glossary.name}
            onChange={(e) => setGlossary({ ...glossary, name: e.target.value })}
            style={{ width: 220 }}
          />
          <Input
            placeholder="glossary_id（小写与连字符）"
            value={glossary.glossary_id}
            onChange={(e) =>
              setGlossary({ ...glossary, glossary_id: e.target.value })
            }
            style={{ width: 220 }}
          />
          <InputNumber
            placeholder="版本"
            value={glossary.version}
            onChange={(v) => setGlossary({ ...glossary, version: v ?? 1 })}
            style={{ width: 100 }}
          />
        </Space>
        <Table
          size="small"
          rowKey="key"
          dataSource={rows}
          pagination={false}
          columns={[
            {
              title: "源术语",
              dataIndex: "term",
              width: "28%",
              render: (_, row) => (
                <Input
                  value={row.term}
                  onChange={(e) => updateRow(row.key, "term", e.target.value)}
                  size="small"
                />
              ),
            },
            {
              title: "允许译法（用 / 分隔多个）",
              dataIndex: "translations",
              render: (_, row) => (
                <Input
                  value={row.translations}
                  onChange={(e) =>
                    updateRow(row.key, "translations", e.target.value)
                  }
                  size="small"
                />
              ),
            },
            {
              title: "备注",
              dataIndex: "note",
              width: "22%",
              render: (_, row) => (
                <Input
                  value={row.note}
                  onChange={(e) => updateRow(row.key, "note", e.target.value)}
                  size="small"
                />
              ),
            },
            {
              title: "",
              width: 60,
              render: (_, row) => (
                <Button
                  type="link"
                  size="small"
                  danger
                  onClick={() =>
                    setRows((prev) => prev.filter((r) => r.key !== row.key))
                  }
                >
                  删除
                </Button>
              ),
            },
          ]}
        />
        <Space>
          <Button
            size="small"
            onClick={() =>
              setRows((prev) => [
                ...prev,
                { key: String(Date.now()), term: "", translations: "", note: "" },
              ])
            }
          >
            添加术语
          </Button>
          <Button type="primary" loading={busy} onClick={() => void save()}>
            校验并保存
          </Button>
          <Button
            onClick={() => api.glossaryDefault().then((g) => {
              setGlossary(g)
              setRows(glossaryToRows(g))
            })}
          >
            重置为示例
          </Button>
        </Space>
      </Space>
    </Card>
  )
}

export function GlossaryManager() {
  const [glossaries, setGlossaries] = useState<GlossarySummary[]>([])
  const [editing, setEditing] = useState<Glossary | null>(null)
  const [loading, setLoading] = useState(true)
  const [messageApi, contextHolder] = message.useMessage()

  const refresh = useCallback(() => {
    setLoading(true)
    api
      .glossaryList()
      .then(setGlossaries)
      .catch(() => undefined)
      .finally(() => setLoading(false))
  }, [])

  useEffect(refresh, [refresh])

  const remove = async (filename: string, reference: string) => {
    try {
      await api.glossaryDelete(filename)
      messageApi.success(`已删除 ${reference}`)
      refresh()
    } catch (exc) {
      messageApi.error(exc instanceof Error ? exc.message : String(exc))
    }
  }

  const columns: ColumnsType<GlossarySummary> = [
    { title: "名称", dataIndex: "name" },
    {
      title: "标识",
      dataIndex: "glossary_id",
      render: (value: string) => (
        <Tag style={{ fontFamily: "monospace", fontSize: 12 }}>{value}</Tag>
      ),
    },
    { title: "版本", dataIndex: "version", width: 70, render: (v: number) => `v${v}` },
    { title: "条目数", dataIndex: "entry_count", width: 80 },
    {
      title: "引用",
      dataIndex: "reference",
      render: (value: string) => (
        <span style={{ fontFamily: "monospace", fontSize: 12 }}>{value}</span>
      ),
    },
    {
      title: "操作",
      width: 200,
      render: (_, record) => (
        <Space size={4}>
          <Button
            type="link"
            size="small"
            onClick={() =>
              api.glossaryItem(record.filename).then(setEditing).catch(() => undefined)
            }
          >
            编辑
          </Button>
          <Popconfirm
            title={`确定删除 ${record.reference}？`}
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
    <>
    {contextHolder}
    <Card
      title="术语库管理"
      extra={
        <Space>
          <Select
            placeholder="从已有术语库复制"
            style={{ minWidth: 180 }}
            value={undefined}
            onChange={(filename) => {
              if (!filename) return
              api
                .glossaryItem(filename)
                .then((g) =>
                  setEditing({
                    ...g,
                    glossary_id: `${g.glossary_id}-copy`,
                    name: `${g.name}（副本）`,
                  }),
                )
                .catch(() => undefined)
            }}
            options={glossaries.map((item) => ({
              value: item.filename,
              label: item.reference,
            }))}
          />
          <Button
            type="primary"
            onClick={() =>
              api.glossaryDefault().then((g) =>
                setEditing({
                  ...g,
                  glossary_id: "my-glossary",
                  name: "我的术语库",
                }),
              )
            }
          >
            新建术语库
          </Button>
        </Space>
      }
    >
      <Table
        size="small"
        rowKey="filename"
        loading={loading}
        columns={columns}
        dataSource={glossaries}
        pagination={false}
        locale={{ emptyText: "尚未保存术语库。" }}
      />
      {editing && (
        <GlossaryEditor
          initial={editing}
          onSaved={() => {
            setEditing(null)
            refresh()
          }}
        />
      )}
    </Card>
    </>
  )
}
