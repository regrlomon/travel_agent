<template>
  <div class="view review-view">
    <h2 class="review-title">行程方案</h2>
    <p class="review-subtitle">{{ data.message }}</p>

    <div class="plan-cards">
      <div
        v-for="plan in data.plans"
        :key="plan.option_id"
        class="plan-card"
        :class="{ selected: selected === plan.option_id }"
        @click="selected = plan.option_id"
      >
        <div class="plan-option-id">方案 {{ plan.option_id }}</div>
        <div class="plan-summary">{{ plan.summary }}</div>

        <div class="plan-flight-block">
          <div class="plan-flight-label">✈ 去程</div>
          <div class="plan-flight-row">
            <div>
              <div class="plan-flight-city">出发</div>
              <div class="plan-flight-time">{{ plan.depart_time || '--:--' }}</div>
            </div>
            <div class="plan-flight-arrow">→</div>
            <div style="text-align:right">
              <div class="plan-flight-city">到达</div>
              <div class="plan-flight-time">{{ plan.flight || '' }}</div>
            </div>
          </div>
        </div>

        <div v-if="plan.return_time" class="plan-flight-block" style="margin-bottom:12px">
          <div class="plan-flight-label">✈ 返程 {{ plan.return_time }}</div>
        </div>

        <div class="plan-days-new">
          <div v-for="day in plan.days.slice(0, 3)" :key="day.day" class="plan-day-row">
            Day {{ day.day }} · <span>{{ day.pois.join(' · ') }}</span>
          </div>
          <div v-if="plan.days.length > 3" class="plan-day-row" style="color:var(--text-muted)">
            …共 {{ plan.days.length }} 天
          </div>
        </div>

        <div class="plan-price">
          机票 ¥{{ plan.total_price ?? '—' }} <span class="plan-price-label">/ 人</span>
        </div>

        <div v-if="selected === plan.option_id" class="plan-selected-badge">✓ 已选</div>
      </div>
    </div>

    <div class="input-bar">
      <input
        v-model="draft"
        :placeholder="selected
          ? `已选方案 ${selected}，有想调整的吗？或直接按确认`
          : '说说你的想法，或选一个方案'"
        @keydown.enter.prevent="confirm"
      />
      <button class="btn-send" @click="confirm">→</button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({ data: Object })
const emit = defineEmits(['reply'])

const selected = ref('')
const draft = ref('')

function confirm() {
  const text = draft.value.trim() || (selected.value ? `选${selected.value}` : '确认，帮我安排')
  draft.value = ''
  emit('reply', text)
}
</script>

<style scoped>
/* styles moved to style.css */
</style>
