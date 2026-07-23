<template>
  <div class="status-bar" :class="{ online: store.serverOnline }">
    <div class="status-left">
      <span class="dot"></span>
      <span class="text">{{ store.serverOnline ? '服务在线' : '服务离线' }}</span>
      <span v-if="store.serverStatus" class="version">v{{ store.serverStatus.version }}</span>
    </div>
    <div class="status-right" v-if="store.serverStatus">
      <span class="tag" v-if="store.serverStatus?.features?.rag">RAG</span>
      <span class="tag" v-if="store.serverStatus?.features?.cot_prompts">COT</span>
      <span class="tag mem" :class="{ ok: store.serverStatus?.memory?.short_term?.connected }">Redis</span>
      <span class="tag mem" :class="{ ok: store.serverStatus?.memory?.long_term?.connected }">MySQL</span>
    </div>
  </div>
</template>

<script setup>
import { useChatStore } from '../stores/chat.js'
import { onMounted } from 'vue'

const store = useChatStore()
onMounted(() => store.refreshHealth())
</script>

<style scoped>
.status-bar {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 20px; background: #1e1e2e; color: #a0a0b0; font-size: 12px;
  border-bottom: 1px solid #2a2a3e;
}
.status-bar.online { background: #1a1a2e; }
.status-left, .status-right { display: flex; align-items: center; gap: 10px; }
.dot {
  width: 8px; height: 8px; border-radius: 50%; background: #ff4444;
  animation: pulse 2s infinite;
}
.online .dot { background: #44ff88; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
.text { color: #ccc; }
.version { color: #888; font-size: 11px; }
.tag {
  padding: 2px 8px; border-radius: 4px; font-size: 10px;
  background: #2a2a4e; color: #8888cc;
}
.tag.mem { background: #2e1a1a; color: #cc4444; }
.tag.mem.ok { background: #1a2e1a; color: #44cc44; }
</style>
