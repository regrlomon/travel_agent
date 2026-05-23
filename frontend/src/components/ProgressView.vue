<template>
  <div class="view progress-view">
    <p class="progress-title">正在规划</p>
    <ul class="timeline">
      <li v-for="(item, i) in items" :key="i" class="timeline-item">
        <div class="timeline-dot">✓</div>
        <div class="timeline-text">
          <div class="timeline-node">{{ item.node }}</div>
          <div class="timeline-msg">{{ item.message }}</div>
        </div>
      </li>
      <li class="timeline-item">
        <div class="timeline-dot pending"></div>
        <div class="timeline-text">
          <div class="timeline-msg" style="color: var(--text-secondary)">处理中...</div>
        </div>
      </li>
    </ul>
  </div>
</template>

<script setup>
defineProps({ items: Array })
</script>
