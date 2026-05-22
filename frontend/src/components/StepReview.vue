<template>
  <div class="step-review">
    <h2>③ 确认航班 &amp; 景点</h2>

    <section v-if="flights.length">
      <h3>航班选项</h3>
      <div v-for="f in flights" :key="f.pair_id" class="flight-card">
        <strong>{{ f.outbound }}</strong> / 回程 {{ f.return }}
        <span class="price">合计 ¥{{ f.total_price }}</span>
      </div>
    </section>

    <section v-if="pois.length">
      <h3>推荐景点（TOP {{ pois.length }}）</h3>
      <span v-for="p in pois" :key="p.name" class="poi-tag">{{ p.name }}</span>
    </section>

    <form @submit.prevent="send">
      <input v-model="reply" placeholder="有偏好吗？或直接说「确认，帮我安排」" />
      <button type="submit" :disabled="sent">{{ sent ? '提交中...' : '提交' }}</button>
    </form>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({ hitlData: Object })
const emit = defineEmits(['reply'])
const reply = ref('')
const sent = ref(false)

const flights = computed(() => props.hitlData?.data?.flights_summary || [])
const pois = computed(() => props.hitlData?.data?.poi_summary || [])

function send() {
  sent.value = true
  emit('reply', reply.value || '确认，帮我安排')
}
</script>
