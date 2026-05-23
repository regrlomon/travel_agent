<template>
  <div class="view chat-view">
    <!-- Hero: shown only before first message -->
    <div v-if="messages.length === 0" class="hero">
      <h1 class="hero-title">你想去哪里？</h1>
      <p class="hero-sub">告诉我你的想法，我来帮你搞定机票和行程</p>
    </div>

    <!-- Chat bubbles -->
    <div v-else class="chat-messages">
      <div
        v-for="(msg, i) in messages"
        :key="i"
        class="bubble-row"
        :class="msg.role"
      >
        <div class="bubble-avatar">{{ msg.role === 'ai' ? 'AI' : '我' }}</div>
        <div class="bubble" :class="msg.role">{{ msg.text }}</div>
      </div>

      <!-- Typing indicator while waiting for AI -->
      <div v-if="waiting" class="bubble-row ai">
        <div class="bubble-avatar">AI</div>
        <div class="bubble ai typing">
          <span></span><span></span><span></span>
        </div>
      </div>
    </div>

    <!-- Input bar -->
    <div class="input-bar">
      <input
        v-model="draft"
        :placeholder="messages.length === 0
          ? '随便说，比如「想去西藏看星空，7月，从广州出发」'
          : '继续输入...'"
        @keydown.enter.prevent="send"
        :disabled="waiting"
        ref="inputEl"
      />
      <button class="btn-send" @click="send" :disabled="!draft.trim() || waiting">→</button>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'

const props = defineProps({ messages: Array, waiting: Boolean })
const emit = defineEmits(['send'])

const draft = ref('')
const inputEl = ref(null)

function send() {
  const text = draft.value.trim()
  if (!text) return
  draft.value = ''
  emit('send', text)
  nextTick(() => inputEl.value?.focus())
}
</script>

<style scoped>
.chat-view {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.hero {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 48px 24px 0;
}

.hero-title { font-size: 32px; font-weight: 700; margin-bottom: 10px; }
.hero-sub   { font-size: 15px; color: var(--text-secondary); }

.chat-messages { flex: 1; }

/* typing dots */
.bubble.typing { display: flex; gap: 4px; align-items: center; padding: 12px 14px; }
.bubble.typing span {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--text-muted);
  animation: blink 1.2s infinite;
}
.bubble.typing span:nth-child(2) { animation-delay: 0.2s; }
.bubble.typing span:nth-child(3) { animation-delay: 0.4s; }

@keyframes blink {
  0%, 80%, 100% { opacity: 0.2; }
  40%           { opacity: 1; }
}
</style>
