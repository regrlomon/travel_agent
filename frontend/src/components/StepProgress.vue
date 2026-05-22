<template>
  <div class="step-progress">
    <h2>② 规划进行中...</h2>
    <ul class="timeline">
      <li v-for="(p, i) in progress" :key="i" class="timeline-item">
        <span class="node">{{ p.node }}</span>
        <span class="msg">{{ p.message }}</span>
        <span class="pct" v-if="p.pct">{{ p.pct }}%</span>
      </li>
      <li class="timeline-item active">
        <span class="spinner">⟳</span> 处理中...
      </li>
    </ul>
  </div>
</template>

<script setup>
defineProps({ progress: Array })
</script>
