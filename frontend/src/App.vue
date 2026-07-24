<template>
  <div class="app">
    <StatusBar />
    <div class="layout">
      <!-- 左侧：对话历史侧边栏 -->
      <HistorySidebar />

      <!-- 中间：聊天 -->
      <div class="main-col">
        <div class="topbar">
          <button class="icon-btn" @click="store.toggleSidebar()" title="切换侧边栏">☰</button>
          <h1>TourAgent</h1>
          <button @click="settingsOpen = true" class="icon-btn" title="设置">⚙️</button>
        </div>
        <ChatPanel />
      </div>

      <!-- 右侧：详情面板 -->
      <div class="side-col" v-if="hasData">
        <DraftCard v-if="store.currentDraft" />
        <QuoteTable v-if="store.currentQuote" />

        <div v-if="store.error" class="error-box">
          ⚠️ {{ store.error }}
        </div>
      </div>
    </div>

    <SettingsPanel :open="settingsOpen" @close="settingsOpen = false" />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useChatStore } from './stores/chat.js'
import StatusBar from './components/StatusBar.vue'
import HistorySidebar from './components/HistorySidebar.vue'
import ChatPanel from './components/ChatPanel.vue'
import DraftCard from './components/DraftCard.vue'
import QuoteTable from './components/QuoteTable.vue'
import SettingsPanel from './components/SettingsPanel.vue'

const store = useChatStore()
const settingsOpen = ref(false)

const hasData = computed(() => store.currentDraft || store.currentQuote || store.error)
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0e0e18; color: #ccc; }
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: #0e0e18; }
::-webkit-scrollbar-thumb { background: #2a2a3e; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #3a3a5e; }
</style>

<style scoped>
.app { display: flex; flex-direction: column; height: 100vh; }
.layout { display: flex; flex: 1; overflow: hidden; }

.main-col {
  flex: 1; display: flex; flex-direction: column; min-width: 0; min-height: 0; overflow: hidden;
}
.topbar {
  display: flex; justify-content: space-between; align-items: center; gap: 10px;
  padding: 12px 20px; background: #1a1a2e; border-bottom: 1px solid #2a2a3e;
}
.topbar h1 {
  font-size: 18px; font-weight: 700;
  background: linear-gradient(135deg, #99aaff, #6677cc);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.icon-btn {
  width: 36px; height: 36px; border-radius: 8px; border: 1px solid #333;
  background: none; color: #888; cursor: pointer; font-size: 16px;
  transition: all .2s; flex-shrink: 0;
}
.icon-btn:hover { border-color: #6677cc; color: #99aaff; }

.side-col {
  width: 420px; border-left: 1px solid #2a2a3e; background: #11111e;
  overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 14px;
}

.error-box {
  padding: 14px 18px; border-radius: 10px; background: #2e1a1a;
  border: 1px solid #4e2a2a; color: #cc6666; font-size: 13px;
}

@media (max-width: 1100px) {
  .side-col { width: 340px; }
}
@media (max-width: 800px) {
  .layout { flex-direction: column; }
  .side-col { width: 100%; max-height: 40vh; }
}
</style>
