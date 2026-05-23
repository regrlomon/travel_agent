<template>
  <div class="view result-view-wrap">
    <div class="aurora">
      <div class="aurora-blob"></div>
      <div class="aurora-blob"></div>
    </div>

    <div class="result-view">
      <div class="result-header">
        <h2 class="result-title">你的行程 🎉</h2>
        <p class="result-sub">{{ result.itineraries?.length }} 套方案 · 点击展开详情</p>
      </div>

      <div v-if="result.warnings?.length" class="warning-box">
        <div v-for="w in result.warnings" :key="w">⚠ {{ w }}</div>
      </div>

      <div v-if="!result.itineraries?.length" style="color:var(--text-secondary);font-size:14px">
        暂无行程方案，请检查警告信息。
      </div>

      <div v-for="itin in result.itineraries" :key="itin.option_id" class="itinerary-card">
        <div class="itin-top">
          <div>
            <div class="itin-option">方案 {{ itin.option_id }}</div>
            <div class="itin-name">{{ itin.summary }}</div>
          </div>
          <div style="text-align:right">
            <div class="itin-price">¥{{ itin.flights?.total_price ?? '—' }}</div>
            <div class="itin-price-label">机票 / 人<br>住宿·餐饮另计</div>
          </div>
        </div>

        <div v-if="itin.flights" class="itin-flight-strip">
          <span>✈</span>
          <span>去程：{{ itin.flights.outbound.depart_airport }} {{ itin.flights.outbound.depart_time?.slice(11,16) }} → {{ itin.flights.outbound.arrive_airport }}</span>
          <span style="margin-left:auto">返程：{{ itin.flights.return_flight?.depart_airport }} {{ itin.flights.return_flight?.depart_time?.slice(11,16) }} → {{ itin.flights.return_flight?.arrive_airport }}</span>
        </div>

        <div class="itin-days">
          <div v-for="day in itin.days" :key="day.day" class="day-row">
            <div class="day-badge">Day {{ day.day }}</div>
            <div>
              <div class="day-pois">
                <span v-for="poi in day.pois" :key="poi.poi_id" class="poi-chip">{{ poi.name }}</span>
              </div>
              <div v-if="day.transport_note" class="day-note">{{ day.transport_note }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({ result: Object })
</script>

<style scoped>
.result-view-wrap { display: flex; flex-direction: column; }
</style>
