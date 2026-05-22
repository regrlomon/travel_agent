<template>
  <div id="app">
    <header>
      <h1>✈ 智能出行助手</h1>
      <nav class="stepper">
        <span :class="{ active: step === 1 }">① 确认需求</span>
        <span :class="{ active: step === 2 }">② 规划中</span>
        <span :class="{ active: step === 3 }">③ 确认选择</span>
        <span :class="{ active: step === 4 }">④ 查看行程</span>
      </nav>
    </header>

    <main>
      <StepConfirm
        v-if="step <= 1"
        :hitlData="step === 1 ? hitlData : null"
        :loading="step === 1 && !hitlData"
        @submit="onSubmit"
        @reply="onReply"
      />
      <StepProgress v-if="step === 2" :progress="progress" />
      <StepReview   v-if="step === 3" :hitlData="hitlData" @reply="onReply" />
      <StepResults  v-if="step === 4" :result="result" />

      <p v-if="error" class="error">{{ error }}</p>
    </main>
  </div>
</template>

<script setup>
import { useWebSocket } from './composables/useWebSocket.js'
import StepConfirm  from './components/StepConfirm.vue'
import StepProgress from './components/StepProgress.vue'
import StepReview   from './components/StepReview.vue'
import StepResults  from './components/StepResults.vue'

const { step, hitlData, progress, result, error, startPlan, sendReply } = useWebSocket()

function onSubmit(formData) { startPlan(formData) }
function onReply(text)      { sendReply(text) }
</script>
