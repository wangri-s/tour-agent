<template>
  <div class="quote-card" v-if="store.currentQuote">
    <div class="q-header">
      <h3>📊 报价单</h3>
      <span class="q-total">总计 ¥{{ store.currentQuote.total.toLocaleString() }}/人</span>
    </div>

    <table>
      <thead>
        <tr><th>项目</th><th class="num">人均费用</th><th class="bar-col"></th></tr>
      </thead>
      <tbody>
        <tr v-if="store.currentQuote.flights > 0">
          <td>✈️ 国际机票</td>
          <td class="num">¥{{ store.currentQuote.flights.toLocaleString() }}</td>
          <td><div class="bar" :style="barStyle(store.currentQuote.flights)"></div></td>
        </tr>
        <tr v-if="store.currentQuote.hotels > 0">
          <td>🏨 酒店</td>
          <td class="num">¥{{ store.currentQuote.hotels.toLocaleString() }}</td>
          <td><div class="bar" :style="barStyle(store.currentQuote.hotels)"></div></td>
        </tr>
        <tr v-if="store.currentQuote.transport > 0">
          <td>🚗 市内交通</td>
          <td class="num">¥{{ store.currentQuote.transport.toLocaleString() }}</td>
          <td><div class="bar" :style="barStyle(store.currentQuote.transport)"></div></td>
        </tr>
        <tr v-if="store.currentQuote.tickets > 0">
          <td>🎫 景点门票</td>
          <td class="num">¥{{ store.currentQuote.tickets.toLocaleString() }}</td>
          <td><div class="bar" :style="barStyle(store.currentQuote.tickets)"></div></td>
        </tr>
        <tr v-if="store.currentQuote.meals > 0">
          <td>🍜 餐饮</td>
          <td class="num">¥{{ store.currentQuote.meals.toLocaleString() }}</td>
          <td><div class="bar" :style="barStyle(store.currentQuote.meals)"></div></td>
        </tr>
        <tr v-if="store.currentQuote.guide > 0">
          <td>👨‍💼 导游</td>
          <td class="num">¥{{ store.currentQuote.guide.toLocaleString() }}</td>
          <td><div class="bar" :style="barStyle(store.currentQuote.guide)"></div></td>
        </tr>
      </tbody>
    </table>

    <div class="q-note" v-if="store.currentQuote.notes">{{ store.currentQuote.notes }}</div>
  </div>
</template>

<script setup>
import { useChatStore } from '../stores/chat.js'

const store = useChatStore()

function barStyle(val) {
  const max = store.currentQuote?.total || 1
  const pct = Math.round((val / max) * 100)
  return { width: pct + '%' }
}
</script>

<style scoped>
.quote-card {
  background: #1a1a2e; border: 1px solid #2a2a4e; border-radius: 12px;
  overflow: hidden;
}
.q-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 14px 20px; background: #22223e; border-bottom: 1px solid #2a2a4e;
}
.q-header h3 { margin: 0; color: #99aaff; font-size: 15px; }
.q-total { color: #44cc88; font-size: 16px; font-weight: 700; }
table { width: 100%; border-collapse: collapse; }
th, td {
  padding: 10px 14px; text-align: left; border-bottom: 1px solid #1e1e32;
  font-size: 13px;
}
th { color: #777; font-weight: 600; font-size: 11px; text-transform: uppercase; }
td { color: #bbc; }
.num { text-align: right; font-variant-numeric: tabular-nums; color: #ccc; }
.bar-col { width: 80px; }
.bar {
  height: 6px; border-radius: 3px; background: linear-gradient(90deg, #4455aa, #6677cc);
  min-width: 4px; transition: width .3s;
}
.q-note {
  padding: 10px 14px; font-size: 12px; color: #666; border-top: 1px solid #1e1e32;
}
</style>
