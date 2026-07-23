<template>
  <div class="draft-card" v-if="store.currentDraft">
    <div class="card-header">
      <h3>📋 行程草案 v{{ store.currentDraft.version }}</h3>
      <span class="cost" v-if="store.currentDraft.estimated_cost">
        💰 ¥{{ store.currentDraft.estimated_cost.toLocaleString() }}/人
      </span>
    </div>

    <div class="card-body" v-html="rendered"></div>

    <div class="card-footer">
      <span v-if="store.currentDraft.weather_summary">🌤️ {{ store.currentDraft.weather_summary }}</span>
      <span v-if="store.currentBranch">📍 {{ store.currentBranch }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useChatStore } from '../stores/chat.js'
import { marked } from 'marked'

marked.setOptions({ breaks: true, gfm: true })

const store = useChatStore()
const rendered = computed(() => {
  const md = store.currentDraft?.itinerary_md || ''
  return marked.parse(md.substring(0, 5000))
})
</script>

<style scoped>
.draft-card {
  background: #1a1a2e; border: 1px solid #2a2a4e; border-radius: 12px;
  overflow: hidden;
}
.card-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 14px 20px; background: #22223e; border-bottom: 1px solid #2a2a4e;
}
.card-header h3 { margin: 0; color: #99aaff; font-size: 15px; }
.cost { color: #ffcc66; font-size: 14px; font-weight: 600; }
.card-body {
  padding: 16px 20px; max-height: 60vh; overflow-y: auto;
  color: #bbc; font-size: 13px; line-height: 1.7;
}
.card-footer {
  display: flex; gap: 16px; padding: 10px 20px;
  border-top: 1px solid #2a2a4e; font-size: 12px; color: #777;
}

/* Markdown 覆盖 */
.card-body :deep(h1) { font-size: 20px; color: #ccd; margin: 12px 0 8px; }
.card-body :deep(h2) { font-size: 16px; color: #99aaff; margin: 10px 0 6px; }
.card-body :deep(h3) { font-size: 14px; color: #aab; margin: 8px 0 4px; }
.card-body :deep(table) {
  width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 12px;
}
.card-body :deep(th), .card-body :deep(td) {
  border: 1px solid #2a2a3e; padding: 5px 8px; text-align: left;
}
.card-body :deep(th) { background: #22223e; color: #999; }
.card-body :deep(strong) { color: #ffcc66; }
.card-body :deep(blockquote) {
  border-left: 3px solid #4455aa; margin: 8px 0; padding: 4px 12px; color: #888;
  background: #1e1e32; border-radius: 0 6px 6px 0;
}
.card-body :deep(code) {
  background: #2a2a3e; padding: 1px 5px; border-radius: 3px; font-size: 11px;
}
</style>
