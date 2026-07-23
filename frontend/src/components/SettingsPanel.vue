<template>
  <div class="settings" v-if="open">
    <div class="overlay" @click="$emit('close')"></div>
    <div class="panel">
      <div class="head">
        <h3>⚙️ 设置</h3>
        <button @click="$emit('close')" class="close-btn">✕</button>
      </div>

      <div class="field">
        <label>会话 ID <span class="hint">（刷新不丢失）</span></label>
        <div class="row">
          <input v-model="store.sessionId" />
          <button @click="store.newSession()" class="sm-btn">新建</button>
        </div>
      </div>

      <div class="field">
        <label>客户 ID</label>
        <input v-model="store.customerId" />
      </div>

      <div class="field">
        <label>渠道</label>
        <select v-model="store.channel">
          <option value="web">Web</option>
          <option value="wechat">微信</option>
          <option value="whatsapp">WhatsApp</option>
          <option value="messenger">Messenger</option>
          <option value="tiktok">TikTok</option>
        </select>
      </div>

      <div class="field">
        <label>语言</label>
        <select v-model="store.language">
          <option value="zh">中文</option>
          <option value="en">English</option>
        </select>
      </div>

      <div class="actions">
        <button @click="store.clearChat()" class="danger-btn">清空对话</button>
        <button @click="store.refreshHealth(); $emit('close')" class="sm-btn">🔄 刷新状态</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useChatStore } from '../stores/chat.js'
defineProps({ open: Boolean })
defineEmits(['close'])
const store = useChatStore()
</script>

<style scoped>
.settings { position: fixed; inset: 0; z-index: 100; display: flex; justify-content: center; align-items: center; }
.overlay { position: absolute; inset: 0; background: #0008; }
.panel {
  position: relative; background: #1e1e32; border: 1px solid #333;
  border-radius: 16px; padding: 24px; width: 360px; max-width: 90vw;
  display: flex; flex-direction: column; gap: 16px;
}
.head { display: flex; justify-content: space-between; align-items: center; }
.head h3 { margin: 0; color: #ccc; font-size: 16px; }
.close-btn {
  width: 32px; height: 32px; border-radius: 50%; border: 1px solid #333;
  background: none; color: #888; cursor: pointer; font-size: 14px;
}
.field { display: flex; flex-direction: column; gap: 6px; }
.field label { font-size: 12px; color: #777; }
.field input, .field select {
  padding: 10px 12px; border-radius: 8px; border: 1px solid #333;
  background: #13131f; color: #ccc; font-size: 13px; outline: none;
}
.field input:focus, .field select:focus { border-color: #6677cc; }
.row { display: flex; gap: 8px; }
.row input { flex: 1; }
.sm-btn {
  padding: 8px 14px; border-radius: 8px; border: 1px solid #333;
  background: #2a2a4e; color: #99aaff; cursor: pointer; font-size: 12px;
  white-space: nowrap;
}
.sm-btn:hover { background: #33336e; }
.danger-btn {
  padding: 8px 14px; border-radius: 8px; border: 1px solid #4e2a2a;
  background: #2e1a1a; color: #cc6666; cursor: pointer; font-size: 12px;
}
.danger-btn:hover { background: #3e1e1e; }
.actions { display: flex; gap: 8px; margin-top: 8px; }
.hint { color: #44cc44; font-size: 10px; }
</style>
