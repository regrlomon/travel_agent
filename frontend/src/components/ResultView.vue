<template>
  <div class="view result-view">
    <div class="result-header">
      <h2>你的行程</h2>
      <p>{{ result.itineraries?.length }} 个方案 · 点击查看详情</p>
    </div>

    <div v-if="result.warnings?.length" class="warning-box">
      <div v-for="w in result.warnings" :key="w">⚠ {{ w }}</div>
    </div>

    <div v-if="!result.itineraries?.length" style="color: var(--text-secondary); font-size:14px">
      暂无行程方案，请检查警告信息。
    </div>

    <div
      v-for="itin in result.itineraries"
      :key="itin.option_id"
      class="itinerary-card"
    >
      <div class="itin-header">
        <div>
          <div class="itin-title">方案 {{ itin.option_id }}：{{ itin.summary }}</div>
          <div class="itin-flight">
            {{ itin.flights.outbound.depart_airport }} → {{ itin.flights.outbound.arrive_airport }}
            · {{ itin.flights.outbound.depart_time.slice(0, 10) }}
          </div>
        </div>
        <div class="itin-price">¥{{ itin.flights.total_price }}/人</div>
      </div>

      <div class="day-list">
        <div v-for="day in itin.days" :key="day.day" class="day-row">
          <div class="day-num">Day {{ day.day }}</div>
          <div>
            <div class="day-pois">
              <span v-for="poi in day.pois" :key="poi.poi_id" class="poi-chip">
                {{ poi.name }}
              </span>
            </div>
            <div v-if="day.transport_note" class="day-note">{{ day.transport_note }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({ result: Object })
</script>
