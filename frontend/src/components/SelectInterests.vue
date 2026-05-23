<template>
  <div class="view interests-view">
    <div class="aurora" style="position:absolute;inset:0;z-index:0;pointer-events:none;overflow:hidden">
      <div class="aurora-blob"></div>
      <div class="aurora-blob"></div>
    </div>
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

    <div class="interests-actions">
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
  display: flex; flex-direction: column;
  height: 100%; padding: 32px 24px 24px;
  position: relative; z-index: 2;
}
.interests-title { font-size: 22px; font-weight: 700; margin-bottom: 6px; }
.interests-sub { font-size: 14px; color: var(--text-secondary); margin-bottom: 24px; }

.tag-grid { display: flex; flex-wrap: wrap; gap: 10px; flex: 1; align-content: flex-start; max-width: 600px; }

.tag-chip {
  padding: 9px 18px; border-radius: 22px;
  border: 1px solid var(--border); background: var(--bg-glass);
  font-size: 14px; color: var(--text-secondary); cursor: pointer; transition: all .2s;
}
.tag-chip:hover { background: rgba(255,255,255,.1); color: var(--text-primary); }
.tag-chip.selected {
  background: linear-gradient(135deg, rgba(108,59,213,.3), rgba(26,111,235,.3));
  border-color: rgba(108,59,213,.6); color: #c4b5fd;
  box-shadow: 0 0 12px rgba(108,59,213,.2);
}

.interests-actions { display: flex; gap: 10px; margin-top: auto; max-width: 600px; }
.btn-skip {
  flex: 1; padding: 13px; border-radius: 12px;
  border: 1px solid var(--border); background: var(--bg-glass);
  color: var(--text-secondary); font-size: 14px; cursor: pointer; transition: all .2s;
}
.btn-skip:hover { background: rgba(255,255,255,.08); }
</style>
