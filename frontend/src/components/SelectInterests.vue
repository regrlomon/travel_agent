<template>
  <div class="view interests-view">
    <h2 class="interests-title">{{ data.message }}</h2>
    <p class="interests-sub">点选感兴趣的，也可以直接跳过</p>

    <div class="tag-grid">
      <button
        v-for="tag in data.tags"
        :key="tag"
        class="tag-chip"
        :class="{ selected: selected.has(tag) }"
        @click="toggle(tag)"
      >
        {{ tag }}
      </button>
    </div>

    <div class="input-bar" style="margin-top: auto;">
      <button class="btn-skip" @click="skip">跳过</button>
      <button class="btn-send" @click="confirm" :disabled="selected.size === 0">
        确认 ({{ selected.size }}) →
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({ data: Object })
const emit = defineEmits(['reply'])

const selected = ref(new Set(props.data?.preselected ?? []))

function toggle(tag) {
  if (selected.value.has(tag)) {
    selected.value.delete(tag)
  } else {
    selected.value.add(tag)
  }
  selected.value = new Set(selected.value)
}

function confirm() {
  emit('reply', [...selected.value].join('、'))
}

function skip() {
  emit('reply', '')
}
</script>

<style scoped>
.interests-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 24px 16px 16px;
}

.interests-title {
  font-size: 20px;
  font-weight: 700;
  margin-bottom: 6px;
}

.interests-sub {
  font-size: 14px;
  color: var(--text-secondary);
  margin-bottom: 20px;
}

.tag-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  flex: 1;
  align-content: flex-start;
}

.tag-chip {
  padding: 8px 16px;
  border-radius: 20px;
  border: 1.5px solid var(--border);
  background: transparent;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s;
  color: var(--text-primary);
}

.tag-chip.selected {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}

.btn-skip {
  padding: 11px 16px;
  background: var(--bg-surface);
  color: var(--text-secondary);
  border: none;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
}
</style>
