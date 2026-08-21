/** 样本管理：维护可复用的源文档与目标文档对。 */

import { useEffect, useState } from "react"
import {
  Button,
  Card,
  Form,
  Input,
  message,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  Upload,
} from "antd"
import { PlusOutlined } from "@ant-design/icons"
import type { ColumnsType } from "antd/es/table"
import type { UploadFile } from "antd/es/upload/interface"
import { api, type SampleRecord } from "../api"

const ACCEPT = ".pdf,.docx,.doc,.pptx,.ppt,.xlsx,.xls,.odt,.odp"
const LANGUAGE_OPTIONS = [
  { value: "und", label: "未指定" },
  { value: "zh-CN", label: "中文（简体）" },
  { value: "zh-TW", label: "中文（繁体）" },
  { value: "en", label: "英语" },
  { value: "ja", label: "日语" },
  { value: "ko", label: "韩语" },
  { value: "fr", label: "法语" },
  { value: "de", label: "德语" },
  { value: "es", label: "西班牙语" },
  { value: "pt", label: "葡萄牙语" },
  { value: "ru", label: "俄语" },
  { value: "ar", label: "阿拉伯语" },
]

export function SampleManager({
  onUse,
}: {
  onUse: (sample: SampleRecord) => void
}) {
  const [records, setRecords] = useState<SampleRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [createOpen, setCreateOpen] = useState(false)
  const [editing, setEditing] = useState<SampleRecord | null>(null)
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [sourceLanguage, setSourceLanguage] = useState("und")
  const [targetLanguage, setTargetLanguage] = useState("und")
  const [sourceFiles, setSourceFiles] = useState<UploadFile[]>([])
  const [targetFiles, setTargetFiles] = useState<UploadFile[]>([])
  const [saving, setSaving] = useState(false)
  const [messageApi, contextHolder] = message.useMessage()

  const reload = () => {
    setLoading(true)
    api
      .sampleList()
      .then(setRecords)
      .catch((exc) =>
        messageApi.error(exc instanceof Error ? exc.message : String(exc)),
      )
      .finally(() => setLoading(false))
  }

  useEffect(reload, [messageApi])

  const openCreate = () => {
    setName("")
    setDescription("")
    setSourceLanguage("und")
    setTargetLanguage("und")
    setSourceFiles([])
    setTargetFiles([])
    setCreateOpen(true)
  }

  const create = async () => {
    const source = sourceFiles[0]?.originFileObj
    const target = targetFiles[0]?.originFileObj
    if (!name.trim() || !source || !target) {
      messageApi.warning("请填写样本名称，并选择源文档和目标文档")
      return
    }
    setSaving(true)
    try {
      await api.sampleCreate(
        name,
        description,
        sourceLanguage,
        targetLanguage,
        source,
        target,
      )
      messageApi.success("样本已创建")
      setCreateOpen(false)
      reload()
    } catch (exc) {
      messageApi.error(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setSaving(false)
    }
  }

  const saveEdit = async () => {
    if (!editing || !name.trim()) return
    setSaving(true)
    try {
      await api.sampleUpdate(
        editing.sample_id,
        name,
        description,
        sourceLanguage,
        targetLanguage,
      )
      messageApi.success("样本信息已更新")
      setEditing(null)
      reload()
    } catch (exc) {
      messageApi.error(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setSaving(false)
    }
  }

  const useSample = async (record: SampleRecord) => {
    try {
      const full = await api.sampleUse(record.sample_id)
      onUse(full)
      messageApi.success(`已载入样本「${full.name}」`)
    } catch (exc) {
      messageApi.error(exc instanceof Error ? exc.message : String(exc))
    }
  }

  const columns: ColumnsType<SampleRecord> = [
    {
      title: "样本",
      dataIndex: "name",
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{record.name}</Typography.Text>
          {record.description && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {record.description}
            </Typography.Text>
          )}
        </Space>
      ),
    },
    {
      title: "源文档",
      dataIndex: "source_name",
      ellipsis: true,
      render: (value: string, record) => (
        <span><Tag>{record.source_format.slice(1).toUpperCase()}</Tag>{value}</span>
      ),
    },
    {
      title: "目标文档",
      dataIndex: "target_name",
      ellipsis: true,
      render: (value: string, record) => (
        <span><Tag>{record.target_format.slice(1).toUpperCase()}</Tag>{value}</span>
      ),
    },
    {
      title: "语言对",
      width: 145,
      render: (_, record) => (
        <Typography.Text code>
          {record.source_language} → {record.target_language}
        </Typography.Text>
      ),
    },
    {
      title: "来源",
      dataIndex: "origin",
      width: 90,
      render: (value: SampleRecord["origin"]) =>
        value === "builtin" ? <Tag color="blue">内置</Tag> : <Tag>用户</Tag>,
    },
    {
      title: "更新时间",
      dataIndex: "updated_at",
      width: 175,
      render: (value: string) =>
        new Date(value).toLocaleString("zh-CN", { hour12: false }),
    },
    {
      title: "操作",
      width: 190,
      render: (_, record) => (
        <Space>
          <a onClick={() => void useSample(record)}>载入工作台</a>
          {record.origin === "user" && (
            <>
              <a
                onClick={() => {
                  setEditing(record)
                  setName(record.name)
                  setDescription(record.description)
                  setSourceLanguage(record.source_language)
                  setTargetLanguage(record.target_language)
                }}
              >
                编辑
              </a>
              <Popconfirm
                title="归档该样本？"
                description="不会删除文档文件和已有对比记录。"
                onConfirm={() =>
                  api
                    .sampleArchive(record.sample_id)
                    .then(() => {
                      messageApi.success("样本已归档")
                      reload()
                    })
                    .catch((exc) =>
                      messageApi.error(
                        exc instanceof Error ? exc.message : String(exc),
                      ),
                    )
                }
              >
                <a>归档</a>
              </Popconfirm>
            </>
          )}
        </Space>
      ),
    },
  ]

  return (
    <>
      {contextHolder}
      <Card
        title="样本管理"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新建样本
          </Button>
        }
      >
        <Typography.Paragraph type="secondary">
          一个样本同时包含源文档和目标文档；内置样本只读，用户样本可编辑和归档。
        </Typography.Paragraph>
        <Table
          rowKey="sample_id"
          loading={loading}
          columns={columns}
          dataSource={records}
          pagination={{ pageSize: 10, showSizeChanger: false }}
        />
      </Card>

      <Modal
        title="新建样本"
        open={createOpen}
        confirmLoading={saving}
        onOk={() => void create()}
        onCancel={() => setCreateOpen(false)}
        okText="创建"
      >
        <Form layout="vertical">
          <Form.Item label="样本名称" required>
            <Input value={name} maxLength={200} onChange={(e) => setName(e.target.value)} />
          </Form.Item>
          <Form.Item label="说明">
            <Input.TextArea
              value={description}
              maxLength={2000}
              rows={3}
              onChange={(e) => setDescription(e.target.value)}
            />
          </Form.Item>
          <Form.Item label="语言对">
            <Space.Compact style={{ width: "100%" }}>
              <Select
                showSearch
                style={{ width: "50%" }}
                value={sourceLanguage}
                options={LANGUAGE_OPTIONS}
                onChange={setSourceLanguage}
              />
              <Select
                showSearch
                style={{ width: "50%" }}
                value={targetLanguage}
                options={LANGUAGE_OPTIONS}
                onChange={setTargetLanguage}
              />
            </Space.Compact>
          </Form.Item>
          <Form.Item label="源文档" required>
            <Upload
              accept={ACCEPT}
              beforeUpload={() => false}
              maxCount={1}
              fileList={sourceFiles}
              onChange={({ fileList }) => setSourceFiles(fileList.slice(-1))}
            >
              <Button>选择源文档</Button>
            </Upload>
          </Form.Item>
          <Form.Item label="目标文档" required>
            <Upload
              accept={ACCEPT}
              beforeUpload={() => false}
              maxCount={1}
              fileList={targetFiles}
              onChange={({ fileList }) => setTargetFiles(fileList.slice(-1))}
            >
              <Button>选择目标文档</Button>
            </Upload>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="编辑样本"
        open={editing !== null}
        confirmLoading={saving}
        onOk={() => void saveEdit()}
        onCancel={() => setEditing(null)}
        okText="保存"
      >
        <Form layout="vertical">
          <Form.Item label="样本名称" required>
            <Input value={name} maxLength={200} onChange={(e) => setName(e.target.value)} />
          </Form.Item>
          <Form.Item label="说明">
            <Input.TextArea
              value={description}
              maxLength={2000}
              rows={3}
              onChange={(e) => setDescription(e.target.value)}
            />
          </Form.Item>
          <Form.Item label="语言对">
            <Space.Compact style={{ width: "100%" }}>
              <Select
                showSearch
                style={{ width: "50%" }}
                value={sourceLanguage}
                options={LANGUAGE_OPTIONS}
                onChange={setSourceLanguage}
              />
              <Select
                showSearch
                style={{ width: "50%" }}
                value={targetLanguage}
                options={LANGUAGE_OPTIONS}
                onChange={setTargetLanguage}
              />
            </Space.Compact>
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}
