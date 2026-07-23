<template>
  <div class="chat-panel">
    <!-- 消息列表 -->
    <div class="messages" ref="msgList">
      <div v-if="store.messages.length === 0" class="welcome">
        <div class="welcome-icon">✈️</div>
        <h2>TourAgent 智能旅游定制</h2>
        <p>告诉我你想去哪里，我来帮你规划完美行程</p>
        <div class="quick-actions">
          <button @click="quickSend('北京5天2人预算8000喜欢历史文化')">🏯 北京经典游</button>
          <button @click="quickSend('成都3天1人预算3000看熊猫吃火锅')">🐼 成都美食游</button>
          <button @click="quickSend('西安4天2人预算6000兵马俑华山')">⚔️ 西安古都游</button>
          <button @click="quickSend('桂林4天2人预算5000漓江阳朔')">🏞️ 桂林山水游</button>
        </div>
      </div>

      <div v-for="(m, i) in store.messages" :key="i"
           :class="['msg', m.role, { streaming: m.streaming }]">
        <div class="avatar">{{ m.role === 'user' ? '👤' : m.role === 'system' ? '⚠️' : '🤖' }}</div>
        <div class="bubble" v-html="renderContent(m.content) + (m.streaming ? '▊' : '')"></div>
      </div>

      <!-- 初始加载：还没有 streaming 消息时的占位动画 -->
      <div v-if="store.loading && !store.messages.find(m => m.streaming)" class="msg assistant">
        <div class="avatar">🤖</div>
        <div class="bubble typing">
          <span></span><span></span><span></span>
        </div>
      </div>
    </div>

    <!-- 输入区 -->
    <div class="input-area">
      <input
        ref="inputEl"
        v-model="input"
        @keydown.enter="sendMsg"
        placeholder="输入你的旅游需求..."
        :disabled="store.loading"
      />
      <button @click="sendMsg" :disabled="store.loading || !input.trim()" class="send-btn">
        <span v-if="!store.loading">▶</span>
        <span v-else class="spinner"></span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, watch } from 'vue'
import { useChatStore } from '../stores/chat.js'
import { marked } from 'marked'

marked.setOptions({ breaks: true, gfm: true })

const store = useChatStore()
const input = ref('')
const inputEl = ref(null)
const msgList = ref(null)

function renderContent(text) {
  if (!text) return ''
  // 检测是否包含 Markdown
  if (text.includes('|') || text.includes('##') || text.includes('**')) {
    return marked.parse(text)
  }
  return text.replace(/\n/g, '<br>')
}

function sendMsg() {
  const msg = input.value.trim()
  if (!msg || store.loading) return
  input.value = ''
  store.send(msg)
}

function quickSend(msg) {
  store.send(msg)
}

watch(() => store.messages.length, async () => {
  await nextTick()
  if (msgList.value) {
    msgList.value.scrollTop = msgList.value.scrollHeight
  }
})
</script>

<style scoped>
.chat-panel {
  display: flex; flex-direction: column; height: 100%; background: #13131f;
}
.messages {
  flex: 1; overflow-y: auto; padding: 20px;
  display: flex; flex-direction: column; gap: 16px;
}
.welcome {
  text-align: center; margin-top: 60px; color: #888;
}
.welcome-icon { font-size: 64px; margin-bottom: 16px; }
.welcome h2 { color: #ccc; font-size: 24px; margin: 0 0 8px; }
.welcome p { margin: 0 0 24px; font-size: 14px; }
.quick-actions {
  display: flex; flex-wrap: wrap; gap: 8px; justify-content: center;
}
.quick-actions button {
  padding: 10px 18px; border: 1px solid #333; border-radius: 20px;
  background: #1a1a2e; color: #aaa; cursor: pointer; font-size: 13px;
  transition: all .2s;
}
.quick-actions button:hover { border-color: #6677cc; color: #99aaff; background: #1e1e3e; }

/* 消息气泡 */
.msg { display: flex; gap: 10px; max-width: 85%; }
.msg.user { align-self: flex-end; flex-direction: row-reverse; }
.msg.assistant { align-self: flex-start; }
.msg.system { align-self: center; max-width: 90%; }
.avatar {
  width: 36px; height: 36px; border-radius: 50%; display: flex;
  align-items: center; justify-content: center; font-size: 18px;
  background: #1e1e3e; flex-shrink: 0;
}
.bubble {
  padding: 12px 16px; border-radius: 16px; font-size: 14px; line-height: 1.6;
  overflow-x: auto;
}
.msg.user .bubble { background: #2a3a6e; color: #dde; border-bottom-right-radius: 4px; }
.msg.assistant .bubble { background: #1e1e3e; color: #ccd; border-bottom-left-radius: 4px; }
.msg.system .bubble { background: #3e1e1e; color: #f88; font-size: 13px; border-radius: 8px; }

/* Markdown 渲染 */
.bubble :deep(table) {
  border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 13px;
}
.bubble :deep(th), .bubble :deep(td) {
  border: 1px solid #333; padding: 6px 10px; text-align: left;
}
.bubble :deep(th) { background: #2a2a4e; color: #aaa; }
.bubble :deep(h1),.bubble :deep(h2),.bubble :deep(h3) { color: #99aaff; margin: 8px 0 4px; }
.bubble :deep(h2) { font-size: 16px; }
.bubble :deep(strong) { color: #ffcc66; }
.bubble :deep(code) {
  background: #2a2a3e; padding: 2px 6px; border-radius: 4px; font-size: 12px;
}
.bubble :deep(blockquote) {
  border-left: 3px solid #6677cc; margin: 8px 0; padding: 4px 12px; color: #999;
}

/* 输入区 */
.input-area {
  display: flex; gap: 10px; padding: 16px 20px;
  border-top: 1px solid #2a2a3e; background: #1a1a2e;
}
.input-area input {
  flex: 1; padding: 12px 18px; border-radius: 24px; border: 1px solid #333;
  background: #13131f; color: #ccc; font-size: 14px; outline: none;
  transition: border-color .2s;
}
.input-area input:focus { border-color: #6677cc; }
.send-btn {
  width: 48px; height: 48px; border-radius: 50%; border: none;
  background: linear-gradient(135deg, #6677cc, #4455aa);
  color: #fff; font-size: 18px; cursor: pointer; transition: all .2s;
  display: flex; align-items: center; justify-content: center;
}
.send-btn:hover:not(:disabled) { transform: scale(1.05); }
.send-btn:disabled { opacity: .4; cursor: not-allowed; }

/* 打字动画 */
.typing { display: flex; gap: 4px; align-items: center; padding: 16px 20px; }
.typing span {
  width: 8px; height: 8px; border-radius: 50%; background: #6677cc;
  animation: bounce 1.4s infinite ease-in-out both;
}
.typing span:nth-child(1) { animation-delay: -0.32s; }
.typing span:nth-child(2) { animation-delay: -0.16s; }
@keyframes bounce { 0%,80%,100%{transform:scale(0)} 40%{transform:scale(1)} }

.spinner {
  width: 20px; height: 20px; border: 2px solid #fff3; border-top-color: #fff;
  border-radius: 50%; animation: spin .6s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* 流式输出光标闪烁 */
.msg.streaming .bubble {
  border-left: 2px solid #6677cc;
}
@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
</style>
