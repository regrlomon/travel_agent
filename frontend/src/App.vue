<template>
  <div id="app">
    <header class="topbar">
      <span class="topbar-brand">✈ TRAVEL AI</span>
      <div class="stepper">
        <div class="step-item">
          <div class="step-dot" :class="stepClass(1)">
            <span v-if="stepClass(1) === 'done'">✓</span>
            <span v-else>1</span>
          </div>
          <span class="step-label" :class="stepClass(1)">告诉我</span>
        </div>
        <div class="step-line" :class="{ done: stepClass(1) === 'done' }"></div>
        <div class="step-item">
          <div class="step-dot" :class="stepClass(2)">
            <span v-if="stepClass(2) === 'done'">✓</span>
            <span v-else>2</span>
          </div>
          <span class="step-label" :class="stepClass(2)">规划中</span>
        </div>
        <div class="step-line" :class="{ done: stepClass(2) === 'done' }"></div>
        <div class="step-item">
          <div class="step-dot" :class="stepClass(3)">
            <span v-if="stepClass(3) === 'done'">✓</span>
            <span v-else>3</span>
          </div>
          <span class="step-label" :class="stepClass(3)">选方案</span>
        </div>
        <div class="step-line" :class="{ done: stepClass(3) === 'done' }"></div>
        <div class="step-item">
          <div class="step-dot" :class="stepClass(4)">
            <span v-if="stepClass(4) === 'done'">✓</span>
            <span v-else>4</span>
          </div>
          <span class="step-label" :class="stepClass(4)">出发</span>
        </div>
      </div>
    </header>

    <ChatView
      v-if="phase === 'idle' || phase === 'chat'"
      :messages="messages"
      :waiting="waiting"
      @send="onSend"
    />
    <ProgressView
      v-else-if="phase === 'progress'"
      :items="progressItems"
    />
    <SelectInterests
      v-else-if="phase === 'interests'"
      :data="interestsData"
      @reply="onReply"
    />
    <ConfirmIntent
      v-else-if="phase === 'confirm'"
      :data="confirmData"
      @reply="onReply"
    />
    <PlanReview
      v-else-if="phase === 'review'"
      :data="reviewData"
      @reply="onReply"
    />
    <ResultView
      v-else-if="phase === 'done'"
      :result="finalResult"
    />

    <div v-if="phase === 'error'" style="padding:24px;color:var(--error)">
      {{ error }}
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useSSE } from './composables/useSSE.js'
import ChatView     from './components/ChatView.vue'
import ProgressView from './components/ProgressView.vue'
import SelectInterests from './components/SelectInterests.vue'
import ConfirmIntent   from './components/ConfirmIntent.vue'
import PlanReview   from './components/PlanReview.vue'
import ResultView   from './components/ResultView.vue'

const {
  phase, messages, progressItems, reviewData, finalResult, error,
  confirmData, interestsData,
  startChat, sendReply,
} = useSSE()

const waiting = computed(() =>
  phase.value === 'chat' &&
  messages.value.length > 0 &&
  messages.value[messages.value.length - 1]?.role === 'user'
)

function onSend(text) {
  if (phase.value === 'idle') {
    startChat(text)
  } else {
    sendReply(text)
  }
}

function onReply(text) {
  sendReply(text)
}

function stepClass(n) {
  const map = { idle: 0, chat: 1, interests: 1, confirm: 1, progress: 2, review: 3, done: 4, error: 0 }
  const current = map[phase.value] ?? 0
  if (n < current) return 'done'
  if (n === current) return 'active'
  return 'pending'
}
</script>
