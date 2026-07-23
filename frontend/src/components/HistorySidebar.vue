<template>
  <aside class="sidebar" :class="{ collapsed: !store.sidebarOpen }">
    <!-- 头部 -->
    <div class="sb-header">
      <button class="new-btn" @click="store.newSession()">
        <span>+</span> 新对话
      </button>
      <button class="toggle-btn" @click="store.toggleSidebar()" :title="store.sidebarOpen ? '收起' : '展开'">
        {{ store.sidebarOpen ? '◀' : '▶' }}
      </button>
    </div>

    <!-- 对话列表 -->
    <div class="sb-list" v-if="store.sidebarOpen">
      <div class="sb-section">
        <span class="sb-label">历史对话 ({{ store.sessions.length }})</span>
      </div>

      <div v-if="store.sessions.length === 0" class="sb-empty">
        暂无历史对话<br>发送消息后将自动保存
      </div>

      <div
        v-for="s in store.sessions"
        :key="s.id"
        class="sb-item"
        :class="{ active: s.id === store.sessionId }"
        @click="store.switchSession(s.id)"
      >
        <div class="sb-item-main">
          <div class="sb-title">{{ s.title }}</div>
          <div class="sb-meta">
            <span>{{ s.date }}</span>
            <span>· {{ s.msgCount }} 条</span>
            <span v-if="s.draft" class="sb-cost">· ¥{{ s.draft }}</span>
          </div>
          <div class="sb-branch" v-if="s.branch">
            <span class="branch-tag">{{ branchLabel(s.branch) }}</span>
          </div>
        </div>
        <button class="del-btn" @click.stop="store.deleteSession(s.id)" title="删除">✕</button>
      </div>
    </div>

    <!-- 当前会话信息（折叠时显示） -->
    <div class="sb-current" v-if="!store.sidebarOpen && store.sessions.length > 0">
      <div class="sb-current-count">{{ store.sessions.length }}</div>
    </div>
  </aside>
</template>

<script setup>
import { useChatStore } from '../stores/chat.js'
const store = useChatStore()

function branchLabel(b) {
  const map = { planner: '🏖️ 行程', service: '💬 客服', sales: '💰 销售', operations: '📋 运营' }
  return map[b] || b
}
</script>

<style scoped>
.sidebar {
  width: 280px;
  min-width: 280px;
  height: 100%;
  background: #11111e;
  border-right: 1px solid #2a2a3e;
  display: flex;
  flex-direction: column;
  transition: all .25s;
  overflow: hidden;
}
.sidebar.collapsed {
  width: 44px;
  min-width: 44px;
}

.sb-header {
  display: flex;
  gap: 8px;
  padding: 14px 12px;
  border-bottom: 1px solid #1e1e32;
}
.new-btn {
  flex: 1;
  padding: 9px 0;
  border-radius: 8px;
  border: 1px solid #333;
  background: #1a1a3e;
  color: #99aaff;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
  transition: all .15s;
}
.new-btn span { font-size: 16px; }
.new-btn:hover { background: #2a2a5e; border-color: #6677cc; }
.collapsed .new-btn { display: none; }

.toggle-btn {
  width: 32px; height: 32px;
  border-radius: 6px;
  border: 1px solid #333;
  background: none;
  color: #888;
  cursor: pointer;
  font-size: 12px;
  transition: all .15s;
  flex-shrink: 0;
}
.toggle-btn:hover { border-color: #6677cc; color: #99aaff; }

.sb-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}
.sb-section {
  padding: 8px 4px 6px;
}
.sb-label {
  font-size: 11px;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 1px;
}
.sb-empty {
  padding: 24px 12px;
  text-align: center;
  color: #555;
  font-size: 12px;
  line-height: 1.6;
}

.sb-item {
  display: flex;
  align-items: flex-start;
  padding: 10px 8px;
  margin: 2px 0;
  border-radius: 8px;
  cursor: pointer;
  transition: all .15s;
  gap: 6px;
}
.sb-item:hover { background: #1a1a2e; }
.sb-item.active { background: #1e1e3e; border: 1px solid #333; }

.sb-item-main { flex: 1; min-width: 0; }
.sb-title {
  font-size: 13px;
  color: #ccc;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 3px;
}
.active .sb-title { color: #99aaff; }
.sb-meta {
  font-size: 10px;
  color: #666;
  display: flex;
  gap: 2px;
  flex-wrap: wrap;
}
.sb-cost { color: #44aa66; }
.sb-branch { margin-top: 2px; }
.branch-tag {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  background: #1a1a3e;
  color: #8888cc;
}

.del-btn {
  width: 20px; height: 20px;
  border-radius: 4px;
  border: none;
  background: none;
  color: #555;
  cursor: pointer;
  font-size: 11px;
  flex-shrink: 0;
  margin-top: 2px;
  transition: all .15s;
}
.del-btn:hover { background: #3e1a1a; color: #cc4444; }

.sb-current {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 0;
}
.sb-current-count {
  width: 28px; height: 28px;
  border-radius: 50%;
  background: #1a1a3e;
  color: #99aaff;
  font-size: 12px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}

.collapsed .sb-list,
.collapsed .sb-section,
.collapsed .sb-empty,
.collapsed .sb-item,
.collapsed .sb-label { display: none; }
</style>
