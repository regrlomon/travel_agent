<template>
  <div class="step-results">
    <h2>④ 行程方案</h2>

    <div v-if="result.warnings?.length" class="warnings">
      <p v-for="w in result.warnings" :key="w">⚠ {{ w }}</p>
    </div>

    <div v-for="itin in result.itineraries" :key="itin.option_id" class="itinerary-card">
      <h3>方案 {{ itin.option_id }}：{{ itin.summary }}</h3>
      <p class="flight-info">
        {{ itin.flights.outbound.depart_airport }} → {{ itin.flights.outbound.arrive_airport }}
        ¥{{ itin.flights.total_price }}/人
      </p>
      <div v-for="day in itin.days" :key="day.day" class="day-plan">
        <strong>Day {{ day.day }}</strong>
        <span v-for="poi in day.pois" :key="poi.poi_id" class="poi-name">{{ poi.name }}</span>
        <span class="transport">{{ day.transport_note }}</span>
      </div>
    </div>

    <p v-if="!result.itineraries?.length" class="empty">暂无行程方案，请检查警告信息。</p>
  </div>
</template>

<script setup>
defineProps({ result: Object })
</script>
