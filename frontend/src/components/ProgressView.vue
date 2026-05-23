<template>
  <div class="view progress-view">
    <div class="aurora">
      <div class="aurora-blob"></div>
      <div class="aurora-blob"></div>
      <div class="aurora-blob"></div>
    </div>

    <div class="progress-inner">
      <div class="status-bar">
        <span class="status-dot"></span>
        <span class="status-text">AI 正在为你规划行程…</span>
      </div>

      <ul class="timeline">
        <li v-for="(step, idx) in allSteps" :key="step.node" class="tl-item" :class="step.state">
          <div class="tl-track">
            <div class="tl-dot">
              <svg v-if="step.state === 'completed'" viewBox="0 0 16 16" fill="currentColor" width="14" height="14">
                <path d="M13.5 3.5L6 11 2.5 7.5l-1 1L6 13l8.5-8.5z"/>
              </svg>
              <div v-else-if="step.state === 'active'" class="spinner"></div>
            </div>
            <div v-if="idx < allSteps.length - 1" class="tl-line" :class="{ done: step.state === 'completed' }"></div>
          </div>
          <div class="tl-body">
            <div class="tl-label">{{ step.label }}</div>
            <div v-if="step.state === 'active' && step.message" class="tl-msg">{{ step.message }}</div>
          </div>
        </li>
      </ul>

      <div class="stream-area">
        <transition-group name="slide-in" tag="div" v-if="streamingFlights.length" class="flights-section">
          <div class="flights-header" key="flights-header">
            <span class="stream-label">✈ 航班</span>
            <span class="stream-count">共找到 {{ flightsTotalFound }} 个，为你筛选最优 {{ streamingFlights.length }} 个</span>
          </div>
          <div v-for="f in streamingFlights" :key="f.pair_id" class="flight-card">
            <div class="flight-side">
              <div class="flight-city">{{ f.outbound_dep }}</div>
              <div class="flight-time">{{ f.outbound_time }}</div>
            </div>
            <div class="flight-middle">
              <div class="flight-no">{{ f.flight_no }}</div>
              <div class="flight-arrow">→</div>
              <div class="flight-date">{{ f.outbound_date }}</div>
            </div>
            <div class="flight-side right">
              <div class="flight-city">{{ f.outbound_arr }}</div>
              <div class="flight-time">{{ f.return_time }}</div>
            </div>
            <div class="flight-price">¥{{ f.total_price }}</div>
          </div>
        </transition-group>

        <div v-if="streamingPois.length" class="pois-section">
          <div class="pois-header">
            <span class="stream-label">📍 景点</span>
            <span class="stream-count">共收录 {{ poisTotalFound }} 个，评分最高的</span>
          </div>
          <transition-group name="chip-pop" tag="div" class="poi-chips">
            <span v-for="poi in streamingPois" :key="poi" class="poi-chip-stream">{{ poi }}</span>
          </transition-group>
        </div>

        <div v-if="streamText" class="narrative-section">
          <div class="stream-label">💡 行程分析</div>
          <div class="narrative-text">{{ streamText }}<span class="cursor-blink">▌</span></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  items:             { type: Array,  default: () => [] },
  streamingFlights:  { type: Array,  default: () => [] },
  streamingPois:     { type: Array,  default: () => [] },
  streamText:        { type: String, default: '' },
  flightsTotalFound: { type: Number, default: 0 },
  poisTotalFound:    { type: Number, default: 0 },
})

const STEPS = [
  { node: 'parse_input',    label: '解析出行需求' },
  { node: 'discover_pois',  label: '搜索景点 / 查询航班' },
  { node: 'plan_itinerary', label: '规划行程方案' },
  { node: 'compose_output', label: '整理最终行程' },
]
const NODE_TO_SLOT = {
  parse_input: 'parse_input', discover_pois: 'discover_pois',
  scrape_flights: 'discover_pois', plan_itinerary: 'plan_itinerary',
  compose_output: 'compose_output',
}

const allSteps = computed(() => {
  const reached = new Set((props.items || []).map(i => NODE_TO_SLOT[i.node]).filter(Boolean))
  const lastNode = props.items?.length ? NODE_TO_SLOT[props.items[props.items.length - 1].node] : null
  const lastMsg  = props.items?.length ? props.items[props.items.length - 1].message : ''
  return STEPS.map((s, idx) => {
    let state = 'pending'
    if (reached.has(s.node)) state = s.node === lastNode ? 'active' : 'completed'
    return { ...s, state, message: state === 'active' ? lastMsg : '', last: idx === STEPS.length - 1 }
  })
})
</script>

<style scoped>
.progress-view { display: flex; flex-direction: column; height: 100%; }
.progress-inner {
  position: relative; z-index: 2;
  max-width: 680px; width: 100%; margin: 48px auto;
  padding: 0 24px; display: flex; flex-direction: column; gap: 32px;
}

.status-bar { display: flex; align-items: center; gap: 10px; font-size: 13px; color: var(--text-secondary); }
.status-dot {
  width: 8px; height: 8px; border-radius: 50%; background: var(--accent-hover);
  animation: pulse 1.5s ease-in-out infinite;
}
@keyframes pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.5;transform:scale(.8)} }

.timeline { list-style: none; display: flex; flex-direction: column; }
.tl-item  { display: flex; gap: 14px; }
.tl-track { display: flex; flex-direction: column; align-items: center; width: 36px; flex-shrink: 0; }
.tl-dot {
  width: 36px; height: 36px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
}
.completed .tl-dot { background: linear-gradient(135deg, var(--success), #2da44e); color: #fff; }
.active    .tl-dot { background: linear-gradient(135deg, var(--accent), var(--accent-end)); box-shadow: 0 0 20px rgba(108,59,213,.5); }
.pending   .tl-dot { background: rgba(255,255,255,.05); border: 1px solid var(--border); }
.tl-line { flex: 1; width: 2px; background: var(--border); min-height: 20px; margin: 4px 0; transition: background .3s; }
.tl-line.done { background: linear-gradient(to bottom, var(--success), var(--border)); }
.tl-body { padding-top: 8px; padding-bottom: 20px; flex: 1; }
.tl-label { font-size: 14px; font-weight: 600; }
.active .tl-label   { color: var(--accent-hover); }
.pending .tl-label  { color: var(--text-muted); }
.tl-msg   { font-size: 12px; color: var(--text-secondary); margin-top: 3px; }

.spinner {
  width: 18px; height: 18px; border: 2px solid rgba(255,255,255,.3);
  border-top-color: #fff; border-radius: 50%; animation: spin .8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.stream-area { display: flex; flex-direction: column; gap: 20px; }
.stream-label { font-size: 12px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; }
.stream-count { font-size: 11px; color: var(--text-muted); font-weight: 400; margin-left: 8px; text-transform: none; letter-spacing: 0; }

.flights-section { display: flex; flex-direction: column; gap: 8px; }
.flights-header { margin-bottom: 2px; }
.flight-card {
  background: var(--bg-glass); border: 1px solid var(--border);
  border-radius: 14px; padding: 14px 18px;
  display: flex; align-items: center; gap: 16px;
  transition: border-color .2s;
}
.flight-card:hover { border-color: rgba(108,59,213,.3); }
.flight-side   { min-width: 60px; }
.flight-side.right { text-align: right; }
.flight-city   { font-size: 11px; color: var(--text-muted); }
.flight-time   { font-size: 20px; font-weight: 700; }
.flight-middle { flex: 1; text-align: center; }
.flight-no     { font-size: 11px; color: var(--text-muted); margin-bottom: 2px; }
.flight-arrow  { font-size: 16px; color: var(--text-muted); }
.flight-date   { font-size: 11px; color: var(--text-muted); margin-top: 2px; }
.flight-price  { font-size: 18px; font-weight: 700; color: var(--accent-cyan); margin-left: auto; }

.pois-section { }
.pois-header  { margin-bottom: 10px; }
.poi-chips    { display: flex; flex-wrap: wrap; gap: 8px; }
.poi-chip-stream {
  background: var(--bg-glass); border: 1px solid var(--border);
  border-radius: var(--radius-full); padding: 6px 14px;
  font-size: 13px; color: var(--text-secondary);
}

.narrative-section { }
.narrative-text { font-size: 15px; line-height: 1.8; color: var(--text-secondary); }
.cursor-blink   { animation: blink .8s step-end infinite; color: var(--accent-hover); }
@keyframes blink { 50%{opacity:0} }

.slide-in-enter-active { transition: opacity .4s, transform .4s; }
.slide-in-enter-from   { opacity: 0; transform: translateX(-12px); }
.chip-pop-enter-active { transition: opacity .3s, transform .3s; }
.chip-pop-enter-from   { opacity: 0; transform: scale(.88); }
</style>
