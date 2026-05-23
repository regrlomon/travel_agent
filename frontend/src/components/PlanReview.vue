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
        <div class="plan-flight">
          <span>✈ 去程 <strong>{{ plan.depart_time || '--:--' }}</strong></span>
          <span class="flight-route">{{ plan.flight }}</span>
        </div>
        <div v-if="plan.return_time" class="plan-flight plan-flight-return">
          ✈ 返程 <strong>{{ plan.return_time }}</strong>
        </div>
        <div class="plan-days">
          <div v-for="day in plan.days.slice(0, 3)" :key="day.day" class="plan-day">
            Day {{ day.day }}：{{ day.pois.join(' · ') }}
          </div>
          <div v-if="plan.days.length > 3" class="plan-day">...共 {{ plan.days.length }} 天</div>
        </div>
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
.plan-flight { font-size: 13px; color: var(--text-secondary); margin-bottom: 4px; }
.plan-flight strong { font-size: 15px; color: var(--text-primary); font-weight: 700; }
.plan-flight-return { margin-bottom: 10px; }
.flight-route { margin-left: 8px; }
</style>
