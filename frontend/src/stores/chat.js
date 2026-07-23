// =============================================================================
// 聊天状态管理 (Pinia)
// =============================================================================

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { sendMessage, checkHealth } from '../api/index.js'

export const useChatStore = defineStore('chat', () => {
  // ---- 配置 ----
  const sessionId = ref('web-' + Date.now())
  const customerId = ref('guest')
  const channel = ref('web')
  const language = ref('zh')

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
  const serverStatus = ref(null)   // health check 结果
  const serverOnline = ref(false)

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

  async function send(msg) {
    if (!msg.trim() || loading.value) return

    // 添加用户消息
    messages.value.push({ role: 'user', content: msg, time: new Date() })
    loading.value = true
    error.value = ''

    try {
      const res = await sendMessage({
        session_id: sessionId.value,
        customer_id: customerId.value,
        channel: channel.value,
        message: msg,
        language: language.value
      })

      // 保存响应
      currentDraft.value = res.draft
      currentQuote.value = res.quote
      currentBranch.value = res.branch
      needHuman.value = res.need_human

      // 添加AI回复
      const reply = res.reply || '(暂无回复)'
      messages.value.push({ role: 'assistant', content: reply, time: new Date() })

    } catch (e) {
      error.value = e.message
      messages.value.push({
        role: 'system',
        content: `❌ 请求失败: ${e.message}`,
        time: new Date()
      })
    } finally {
      loading.value = false
    }
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
    sessionId.value = 'web-' + Date.now()
    clearChat()
  }

  return {
    sessionId, customerId, channel, language,
    messages, loading, error,
    currentDraft, currentQuote, currentBranch, needHuman,
    serverStatus, serverOnline, lastReply,
    send, clearChat, newSession, refreshHealth
  }
})
