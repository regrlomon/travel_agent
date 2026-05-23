<template>
  <div class="view confirm-view">
    <div class="confirm-card">
      <p class="confirm-label">小Z助手</p>
      <h2 class="confirm-title">帮你确认一下出行信息</h2>
      <p class="confirm-sub">没问题就点确认，或者告诉我哪里要改</p>

      <div class="info-rows">
        <div class="info-row">
          <span class="info-key">目的地</span>
          <span class="info-val">{{ data.destination }}</span>
        </div>
        <div class="info-row">
          <span class="info-key">出发地</span>
          <span class="info-val">{{ data.origin }}</span>
        </div>
        <div class="info-row">
          <span class="info-key">天数</span>
          <span class="info-val">{{ data.duration_days }} 天</span>
        </div>
        <div v-if="data.depart_date" class="info-row">
          <span class="info-key">出发时间</span>
          <span class="info-val">{{ data.depart_date }}</span>
        </div>
        <div v-if="data.interests?.length" class="info-row">
          <span class="info-key">兴趣</span>
          <span class="info-val">{{ data.interests.join('、') }}</span>
        </div>
      </div>

      <!-- 时段偏好：仅在有值时显示 -->
      <div v-if="data.depart_time_pref || data.return_time_pref" class="time-prefs">
        <div v-if="data.depart_time_pref" class="time-pref-row">
          ✓ 去程优先安排 {{ data.depart_time_pref }} 的航班
        </div>
        <div v-if="data.return_time_pref" class="time-pref-row">
          ✓ 返程 {{ data.return_time_pref }}
        </div>
      </div>

      <div class="confirm-input-bar">
        <input
          v-model="draft"
          placeholder="有要改的吗？直接说，或直接点确认"
          @keydown.enter.prevent="confirm"
        />
        <button class="btn-send" @click="confirm">确认，开始规划 →</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({ data: Object })
const emit = defineEmits(['reply'])

const draft = ref('')

function confirm() {
  // Send draft text if user typed a modification; otherwise send "确认"
  emit('reply', draft.value.trim() || '确认')
  draft.value = ''
}
</script>

<style scoped>
.confirm-view {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 16px;
  height: 100%;
}

.confirm-card {
  width: 100%;
  max-width: 480px;
  background: var(--bg-surface);
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 2px 12px rgba(0,0,0,.08);
}

.confirm-label {
  font-size: 12px;
  color: var(--accent);
  font-weight: 600;
  margin-bottom: 6px;
}

.confirm-title {
  font-size: 20px;
  font-weight: 700;
  margin-bottom: 4px;
}

.confirm-sub {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 16px;
}

.info-rows {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 14px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  background: var(--bg-elevated);
  border-radius: 8px;
}

.info-key {
  font-size: 13px;
  color: var(--text-secondary);
}

.info-val {
  font-size: 13px;
  font-weight: 600;
}

.time-prefs {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 20px;
}

.time-pref-row {
  padding: 9px 12px;
  background: #1f6feb18;
  border: 1px solid var(--accent);
  border-radius: 8px;
  font-size: 13px;
  color: var(--accent-hover);
}

.confirm-input-bar {
  display: flex;
  gap: 8px;
}

.confirm-input-bar input {
  flex: 1;
  padding: 10px 12px;
  border: 1.5px solid var(--border);
  border-radius: 8px;
  font-size: 13px;
  background: var(--bg-input);
  color: var(--text-primary);
  outline: none;
  transition: border-color 0.2s;
}

.confirm-input-bar input::placeholder {
  color: var(--text-muted);
}

.confirm-input-bar input:focus {
  border-color: var(--accent);
}
</style>
