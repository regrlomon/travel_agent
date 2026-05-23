<template>
  <div class="view progress-view">
    <p class="progress-title">正在为你规划行程</p>
    <ul class="timeline">
      <li
        v-for="step in allSteps"
        :key="step.node"
        class="timeline-item"
        :class="step.state"
      >
        <div class="tl-dot">
          <svg v-if="step.state === 'completed'" viewBox="0 0 16 16" fill="currentColor">
            <path d="M13.5 3.5L6 11 2.5 7.5l-1 1L6 13l8.5-8.5z"/>
          </svg>
          <div v-else-if="step.state === 'active'" class="spinner"></div>
        </div>
        <div class="tl-connector" v-if="!step.last"></div>
        <div class="tl-body">
          <div class="tl-label">{{ step.label }}</div>
          <div v-if="step.state === 'active'" class="tl-msg">{{ step.message }}</div>
        </div>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ items: Array })

const STEPS = [
  { node: 'parse_input',   label: '解析出行需求' },
  { node: 'discover_pois', label: '搜索景点 / 查询航班' },
  { node: 'plan_itinerary', label: '规划行程方案' },
  { node: 'compose_output', label: '整理最终行程' },
]

// scrape_flights maps to the same slot as discover_pois
const NODE_TO_SLOT = {
  parse_input:    'parse_input',
  discover_pois:  'discover_pois',
  scrape_flights: 'discover_pois',
  plan_itinerary: 'plan_itinerary',
  compose_output: 'compose_output',
}

const allSteps = computed(() => {
  const reached = new Set((props.items || []).map(i => NODE_TO_SLOT[i.node]).filter(Boolean))
  const lastNode = props.items?.length
    ? NODE_TO_SLOT[props.items[props.items.length - 1].node]
    : null
  const lastMsg = props.items?.length
    ? props.items[props.items.length - 1].message
    : ''

  return STEPS.map((s, idx) => {
    let state = 'pending'
    if (reached.has(s.node)) {
      state = s.node === lastNode ? 'active' : 'completed'
    }
    return { ...s, state, message: state === 'active' ? lastMsg : '', last: idx === STEPS.length - 1 }
  })
})
</script>

<style scoped>
.progress-view { padding: 40px 24px; }
.progress-title { font-size: 18px; font-weight: 700; margin-bottom: 24px; }

.timeline { list-style: none; padding: 0; margin: 0; }
.timeline-item {
  display: flex;
  gap: 12px;
  position: relative;
  padding-bottom: 20px;
}
.timeline-item.pending { opacity: 0.35; }

.tl-dot {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1;
}
.completed .tl-dot { background: var(--accent); color: #fff; }
.completed .tl-dot svg { width: 14px; height: 14px; }
.active .tl-dot { border: 2px solid var(--accent); }
.pending .tl-dot { border: 2px solid var(--border); }

.tl-connector {
  position: absolute;
  left: 11px;
  top: 24px;
  bottom: 0;
  width: 2px;
  background: var(--border);
}

.tl-body { padding-top: 2px; }
.tl-label { font-size: 14px; font-weight: 600; }
.active .tl-label { color: var(--accent); }
.tl-msg  { font-size: 12px; color: var(--text-secondary); margin-top: 2px; }

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--accent);
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin: 1px;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
