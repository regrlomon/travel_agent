<template>
  <div class="step-confirm">
    <h2>① 确认出行需求</h2>

    <!-- Initial input form (shown before first hitl_request) -->
    <form v-if="!hitlData" @submit.prevent="submit">
      <input v-model="form.destination" placeholder="目的地（如：川西）" required />
      <input v-model="form.origin" placeholder="出发城市（如：苏州）" required />
      <input v-model.number="form.duration_days" type="number" placeholder="天数" min="1" required />
      <button type="submit" :disabled="loading">{{ loading ? '解析中...' : '开始规划' }}</button>
    </form>

    <!-- HITL confirmation chat -->
    <div v-if="hitlData" class="chat">
      <div class="bot-msg">{{ hitlData.data.message }}</div>
      <form @submit.prevent="confirm">
        <input v-model="reply" placeholder="有需要修改的吗？没有请直接回车确认" />
        <button type="submit" :disabled="sent">{{ sent ? '确认中...' : '确认' }}</button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({ hitlData: Object, loading: Boolean })
const emit = defineEmits(['submit', 'reply'])

const form = ref({ destination: '', origin: '', duration_days: 7 })
const reply = ref('')
const sent = ref(false)

function submit() { emit('submit', form.value) }
function confirm() {
  sent.value = true
  emit('reply', reply.value || '确认')
}
</script>
