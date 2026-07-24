// =============================================================================
// 聊天状态管理 (Pinia) — 会话持久化 + 记忆功能 + 多会话历史
// =============================================================================

import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { sendMessage, sendMessageStream, checkHealth } from '../api/index.js'

// localStorage 键名
const LS_SESSION_ID = 'tourai_session_id'
const LS_CUSTOMER_ID = 'tourai_customer_id'
const LS_CHANNEL = 'tourai_channel'
const LS_LANGUAGE = 'tourai_language'
const LS_AGENCY_ID = 'tourai_agency_id'
const LS_SESSIONS = 'tourai_sessions'
const LS_SESSION_DATA_PREFIX = 'tourai_session_data_'

function loadPersisted(key, fallback) {
  try { return localStorage.getItem(key) || fallback }
  catch { return fallback }
}

function loadSessions() {
  try {
    const raw = localStorage.getItem(LS_SESSIONS)
    return raw ? JSON.parse(raw) : []
  } catch { return [] }
}

function saveSessions(list) {
  try { localStorage.setItem(LS_SESSIONS, JSON.stringify(list)) } catch {}
}

// 保存单个会话的完整数据（消息 + draft + quote + branch）
function saveSessionData(id, data) {
  try { localStorage.setItem(LS_SESSION_DATA_PREFIX + id, JSON.stringify(data)) } catch {}
}

// 读取单个会话的完整数据
function loadSessionData(id) {
  try {
    const raw = localStorage.getItem(LS_SESSION_DATA_PREFIX + id)
    return raw ? JSON.parse(raw) : null
  } catch { return null }
}

// 删除单个会话的持久化数据
function removeSessionData(id) {
  try { localStorage.removeItem(LS_SESSION_DATA_PREFIX + id) } catch {}
}

export const useChatStore = defineStore('chat', () => {
  // ---- 配置（持久化到 localStorage，刷新不丢失）----
  const sessionId = ref(loadPersisted(LS_SESSION_ID, 'web-' + Date.now()))
  const customerId = ref(loadPersisted(LS_CUSTOMER_ID, 'guest'))
  const channel = ref(loadPersisted(LS_CHANNEL, 'web'))
  const language = ref(loadPersisted(LS_LANGUAGE, 'zh'))
  const agencyId = ref(loadPersisted(LS_AGENCY_ID, ''))

  // 持久化：值变化时自动写入 localStorage
  watch(sessionId, v => { try { localStorage.setItem(LS_SESSION_ID, v) } catch {} })
  watch(customerId, v => { try { localStorage.setItem(LS_CUSTOMER_ID, v) } catch {} })
  watch(channel, v => { try { localStorage.setItem(LS_CHANNEL, v) } catch {} })
  watch(language, v => { try { localStorage.setItem(LS_LANGUAGE, v) } catch {} })
  watch(agencyId, v => { try { localStorage.setItem(LS_AGENCY_ID, v) } catch {} })

  // ---- 消息 ----
  const messages = ref([])
  const loading = ref(false)
  const error = ref('')

  // ---- 当前响应数据 ----
  const currentDraft = ref(null)
  const currentQuote = ref(null)
  const currentBranch = ref('')
  const needHuman = ref(false)

  // ---- 服务状态 ----
  const serverStatus = ref(null)
  const serverOnline = ref(false)

  // ---- 多会话历史 ----
  const sessions = ref(loadSessions())
  const sidebarOpen = ref(true)

  // ---- 启动时恢复当前会话的消息 ----
  {
    const saved = loadSessionData(sessionId.value)
    if (saved) {
      if (saved.messages && Array.isArray(saved.messages)) {
        messages.value = saved.messages.map(m => ({
          role: m.role,
          content: m.content,
          time: m.time ? new Date(m.time) : new Date(),
        }))
      }
      if (saved.draft) currentDraft.value = saved.draft
      if (saved.quote) currentQuote.value = saved.quote
      if (saved.branch) currentBranch.value = saved.branch
    }
  }

  // 保存/更新当前会话到历史列表（元数据 + 完整数据）
  function saveCurrentSession() {
    const msgs = messages.value
    if (msgs.length === 0) return
    const title = msgs.find(m => m.role === 'user')?.content?.slice(0, 30) || '(空对话)'
    const existing = sessions.value.find(s => s.id === sessionId.value)
    const entry = {
      id: sessionId.value,
      title,
      date: new Date().toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }),
      msgCount: msgs.length,
      draft: currentDraft.value ? currentDraft.value.estimated_cost || 0 : 0,
      branch: currentBranch.value,
    }
    if (existing) {
      Object.assign(existing, entry)
    } else {
      sessions.value.unshift(entry)
    }
    // 最多保留 50 条
    if (sessions.value.length > 50) {
      // 清理被淘汰会话的持久化数据
      const removed = sessions.value.slice(50)
      sessions.value = sessions.value.slice(0, 50)
      removed.forEach(s => removeSessionData(s.id))
    }
    saveSessions(sessions.value)

    // 保存完整消息数据到独立 key
    saveSessionData(sessionId.value, {
      messages: msgs.map(m => ({ role: m.role, content: m.content, time: m.time })),
      draft: currentDraft.value,
      quote: currentQuote.value,
      branch: currentBranch.value,
    })
  }

  // 切换到某个历史会话
  function switchSession(id) {
    if (id === sessionId.value) return

    // 1. 保存当前会话（消息 + 元数据）
    saveCurrentSession()

    // 2. 切换 sessionId
    sessionId.value = id
    clearChat()

    // 3. 从 localStorage 恢复目标会话的完整数据
    const data = loadSessionData(id)
    if (data) {
      if (data.messages && Array.isArray(data.messages)) {
        messages.value = data.messages.map(m => ({
          role: m.role,
          content: m.content,
          time: m.time ? new Date(m.time) : new Date(),
        }))
      }
      if (data.draft) currentDraft.value = data.draft
      if (data.quote) currentQuote.value = data.quote
      if (data.branch) currentBranch.value = data.branch
    }
  }

  // 删除会话
  function deleteSession(id) {
    sessions.value = sessions.value.filter(s => s.id !== id)
    saveSessions(sessions.value)
    removeSessionData(id)  // 清理持久化的消息数据
    if (id === sessionId.value) {
      newSession()
    }
  }

  // ---- 计算 ----
  const lastReply = computed(() => {
    const msgs = messages.value.filter(m => m.role === 'assistant')
    return msgs.length ? msgs[msgs.length - 1] : null
  })

  // ---- 行动 ----
  async function refreshHealth() {
    try {
      const data = await checkHealth()
      serverStatus.value = data
      serverOnline.value = data.status === 'ok'
    } catch {
      serverOnline.value = false
      serverStatus.value = null
    }
  }

  // 取消前一个流式请求
  let _streamAbort = null

  async function send(msg) {
    if (!msg.trim() || loading.value) return

    // 取消正在进行的流式请求
    if (_streamAbort) { _streamAbort(); _streamAbort = null }

    messages.value.push({ role: 'user', content: msg, time: new Date() })
    loading.value = true
    error.value = ''

    // 流式 token 累积
    currentDraft.value = null
    currentQuote.value = null
    currentBranch.value = ''
    needHuman.value = false

    // 插入空的 assistant 占位消息
    const assistantIdx = messages.value.length
    messages.value.push({ role: 'assistant', content: '', time: new Date(), streaming: true })

    let streamedText = ''
    let hasStreamedTokens = false

    _streamAbort = sendMessageStream(
      {
        session_id: sessionId.value,
        customer_id: customerId.value,
        agency_id: agencyId.value,
        channel: channel.value,
        message: msg,
        language: language.value,
      },
      {
        onToken(text) {
          hasStreamedTokens = true
          streamedText += text
          // 直接更新数组中的消息对象（Vue 响应式）
          const m = messages.value[assistantIdx]
          if (m) m.content = streamedText
        },

        onBranch(branch) {
          currentBranch.value = branch
        },

        onDraft(draft) {
          currentDraft.value = draft
          if (!currentBranch.value) currentBranch.value = 'planner'
        },

        onQuote(quote) {
          currentQuote.value = quote
        },

        onReply(text) {
          // 非流式回复兜底：如果没有 stream token，用 reply 事件的内容
          if (!hasStreamedTokens) {
            const m = messages.value[assistantIdx]
            if (m) m.content = text
          }
        },

        onDone() {
          _streamAbort = null
          loading.value = false
          const m = messages.value[assistantIdx]
          if (m) {
            m.streaming = false
            if (!m.content) m.content = '(暂无回复)'
          }
          saveCurrentSession()
        },

        onError(err) {
          _streamAbort = null
          loading.value = false
          error.value = err.message
          const m = messages.value[assistantIdx]
          if (m) {
            m.role = 'system'
            m.content = `❌ 请求失败: ${err.message}`
            m.streaming = false
          }
          saveCurrentSession()
        },
      }
    )
  }

  function clearChat() {
    messages.value = []
    currentDraft.value = null
    currentQuote.value = null
    currentBranch.value = ''
    needHuman.value = false
    error.value = ''
  }

  function newSession() {
    saveCurrentSession()
    sessionId.value = 'web-' + Date.now()
    clearChat()
  }

  function toggleSidebar() {
    sidebarOpen.value = !sidebarOpen.value
  }

  return {
    sessionId, customerId, channel, language, agencyId,
    messages, loading, error,
    currentDraft, currentQuote, currentBranch, needHuman,
    serverStatus, serverOnline, lastReply,
    sessions, sidebarOpen,
    send, clearChat, newSession, refreshHealth,
    switchSession, deleteSession, saveCurrentSession, toggleSidebar
  }
})
