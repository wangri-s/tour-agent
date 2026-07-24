// =============================================================================
// API 层 — 对接后端 /chat /chat/stream 和 /health
// =============================================================================

const BASE = ''   // Vite proxy 已转发

export async function checkHealth() {
  const res = await fetch(`${BASE}/health`)
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`)
  return res.json()
}

/** 获取可用旅行社列表 */
export async function fetchAgencies() {
  const res = await fetch(`${BASE}/admin/prompts`)
  if (!res.ok) throw new Error(`Failed to fetch agencies: ${res.status}`)
  return res.json()
}

export async function sendMessage({ session_id, customer_id, agency_id, channel, message, language }) {
  const res = await fetch(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id, customer_id, agency_id, channel, message, language })
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Request failed: ${res.status}`)
  }
  return res.json()
}

// =============================================================================
// 流式请求 — 使用 SSE (Server-Sent Events) 逐 token 接收
// =============================================================================

/**
 * 流式发送消息，返回一个 abort 函数和 onToken/onDone/onError 回调接口
 *
 * @param {Object} params
 * @param {Object} callbacks - { onToken, onBranch, onDraft, onQuote, onReply, onDone, onError }
 * @returns {Function} abort — 调用以取消请求
 */
export function sendMessageStream(params, callbacks) {
  const controller = new AbortController()

  fetch(`${BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
    signal: controller.signal,
  }).then(async (response) => {
    if (!response.ok) {
      const err = await response.json().catch(() => ({}))
      callbacks.onError?.(new Error(err.detail || `Stream failed: ${response.status}`))
      return
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      // 解析 SSE 事件
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''  // 最后一行可能不完整

      let eventType = ''
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          eventType = line.slice(7).trim()
        } else if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6))
            switch (eventType) {
              case 'token':
                callbacks.onToken?.(data.text)
                break
              case 'branch':
                callbacks.onBranch?.(data.branch)
                break
              case 'draft':
                callbacks.onDraft?.(data)
                break
              case 'quote':
                callbacks.onQuote?.(data)
                break
              case 'reply':
                callbacks.onReply?.(data.text)
                break
              case 'done':
                callbacks.onDone?.()
                break
              case 'error':
                callbacks.onError?.(new Error(data.error))
                break
            }
          } catch {
            // 忽略解析失败的行
          }
        }
      }
    }
  }).catch((err) => {
    if (err.name !== 'AbortError') {
      callbacks.onError?.(err)
    }
  })

  return () => controller.abort()
}
