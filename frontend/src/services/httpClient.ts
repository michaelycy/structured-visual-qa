/** 统一 HTTP 客户端：只处理协议、响应类型和后端错误格式。 */

async function ensureOk(response: Response): Promise<Response> {
  if (response.ok) return response

  let detail = `HTTP ${response.status}`
  try {
    const body = await response.json()
    if (body?.detail) detail = String(body.detail)
  } catch {
    // 非 JSON 错误保留 HTTP 状态，避免吞掉可诊断信息。
  }
  throw new Error(detail)
}

export const httpClient = {
  /** JSON 请求统一补充 Content-Type，并解析为调用方声明的 DTO。 */
  async json<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await ensureOk(await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...init,
    }))
    return response.json() as Promise<T>
  },

  /** FormData 上传不能手动声明 Content-Type，边界由浏览器生成。 */
  async form<T>(path: string, body: FormData): Promise<T> {
    const response = await ensureOk(await fetch(path, { method: "POST", body }))
    return response.json() as Promise<T>
  },

  /** 报告导出保留二进制响应，不进入 JSON 解析链路。 */
  async blob(path: string, init?: RequestInit): Promise<Blob> {
    const response = await ensureOk(await fetch(path, init))
    return response.blob()
  },
}
