<template>
  <div class="confirm-view">
    <div class="aurora-wrap">
      <div class="aurora-blob"></div>
      <div class="aurora-blob"></div>
    </div>
    <div class="confirm-card">
      <p class="confirm-badge">小Z助手</p>
      <h2 class="confirm-title">帮你确认一下出行信息</h2>
      <p class="confirm-hint">没问题就点确认，或者告诉我哪里要改</p>

      <div class="info-list">
        <div class="info-row">
          <span class="info-key">📍 目的地</span>
          <span class="info-val">{{ data.destination }}</span>
        </div>
        <div class="info-row">
          <span class="info-key">🛫 出发地</span>
          <span class="info-val">{{ data.origin }}</span>
        </div>
        <div class="info-row">
          <span class="info-key">🗓 天数</span>
          <span class="info-val">{{ data.duration_days }} 天</span>
        </div>
        <div v-if="data.depart_date" class="info-row">
          <span class="info-key">📅 出发时间</span>
          <span class="info-val">{{ data.depart_date }}</span>
        </div>
        <div v-if="data.interests?.length" class="info-row">
          <span class="info-key">❤ 兴趣</span>
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
        <button class="btn-confirm" @click="confirm">确认，开始规划 →</button>
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
  display: flex; align-items: center; justify-content: center;
  padding: 24px 16px; height: 100%; position: relative;
}
.aurora-wrap { position: absolute; inset: 0; z-index: 0; overflow: hidden; pointer-events: none; }

.confirm-card {
  width: 100%; max-width: 480px;
  background: var(--bg-glass); backdrop-filter: blur(32px);
  border: 1px solid var(--border); border-radius: var(--radius-lg);
  padding: 32px; position: relative; z-index: 2;
  box-shadow: 0 24px 64px rgba(0,0,0,.4);
}
.confirm-badge { font-size: 11px; color: var(--accent-hover); font-weight: 700; letter-spacing: .5px; margin-bottom: 8px; }
.confirm-title { font-size: 20px; font-weight: 700; margin-bottom: 4px; }
.confirm-hint  { font-size: 13px; color: var(--text-secondary); margin-bottom: 20px; }

.info-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 14px; }
.info-row {
  display: flex; justify-content: space-between; align-items: center;
  background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.07);
  border-radius: 10px; padding: 11px 14px;
}
.info-key { font-size: 13px; color: var(--text-secondary); display: flex; align-items: center; gap: 6px; }
.info-val { font-size: 13px; font-weight: 600; }

.time-prefs { display: flex; flex-direction: column; gap: 6px; margin-bottom: 20px; }
.time-pref-row {
  padding: 9px 14px; background: rgba(108,59,213,.12);
  border: 1px solid rgba(108,59,213,.4); border-radius: 10px;
  font-size: 13px; color: var(--accent-hover);
  display: flex; align-items: center; gap: 8px;
}

.confirm-input-bar { display: flex; gap: 8px; }
.confirm-input-bar input {
  flex: 1; padding: 11px 14px;
  border: 1px solid var(--border); border-radius: 10px;
  font-size: 13px; background: var(--bg-input); color: var(--text-primary); outline: none;
  transition: border-color .2s;
}
.confirm-input-bar input::placeholder { color: var(--text-muted); }
.confirm-input-bar input:focus { border-color: rgba(108,59,213,.7); }
.btn-confirm {
  background: linear-gradient(135deg, var(--accent), var(--accent-end));
  border: none; border-radius: 10px; padding: 11px 18px;
  color: #fff; font-size: 13px; font-weight: 600; cursor: pointer;
  white-space: nowrap; transition: opacity .2s;
}
.btn-confirm:hover { opacity: .85; }
</style>
