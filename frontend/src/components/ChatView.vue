<template>
  <div class="view chat-view">
    <div class="aurora">
      <div class="aurora-blob"></div>
      <div class="aurora-blob"></div>
      <div class="aurora-blob"></div>
    </div>

    <div v-if="messages.length === 0" class="hero">
      <div class="hero-eyebrow">
        <span class="hero-pulse"></span>AI 国内旅行规划助手
      </div>
      <h1 class="hero-title">去你一直<br>想去的地方</h1>
      <p class="hero-sub">一句话描述你的旅行想法，AI 自动匹配国内机票与行程方案</p>

      <div class="input-bar hero-input">
        <input
          v-model="draft"
          placeholder="比如「7月去西藏看星空，从广州出发，5天」"
          @keydown.enter.prevent="send"
          ref="inputEl"
        />
        <button class="btn-send" @click="send" :disabled="!draft.trim()">→</button>
      </div>

      <div class="hero-chips">
        <span v-for="s in suggestions" :key="s.label" class="hero-chip" @click="fillSuggestion(s.text)">
          {{ s.label }}
        </span>
      </div>
    </div>

    <div v-else class="chat-messages">
      <div v-for="(msg, i) in messages" :key="i" class="bubble-row" :class="msg.role">
        <div class="bubble-avatar" :class="msg.role === 'ai' ? 'ai-avatar' : 'user-avatar'">
          {{ msg.role === 'ai' ? 'AI' : '我' }}
        </div>
        <div class="bubble" :class="msg.role">{{ msg.text }}</div>
      </div>

      <div v-if="waiting" class="bubble-row ai">
        <div class="bubble-avatar ai-avatar">AI</div>
        <div class="bubble ai typing-bubble">
          <span class="typing-dot"></span>
          <span class="typing-dot"></span>
          <span class="typing-dot"></span>
        </div>
      </div>
    </div>

    <div v-if="messages.length > 0" class="input-bar">
      <input
        v-model="draft"
        placeholder="继续输入…"
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

const draft   = ref('')
const inputEl = ref(null)

const suggestions = [
  { label: '🏔 西藏·星空徒步', text: '想去西藏看星空，7月，从广州出发，5天' },
  { label: '🌊 三亚·亲子海岛', text: '三亚亲子游，8月，从北京出发，4天' },
  { label: '🎭 大理·慢生活',   text: '大理慢生活，5月，从上海出发，7天' },
  { label: '🏞 张家界·奇峰',  text: '张家界，国庆，从广州出发，5天' },
  { label: '🌸 成都·美食',    text: '成都美食之旅，下个月，从北京出发，4天' },
]

function send() {
  const text = draft.value.trim()
  if (!text) return
  draft.value = ''
  emit('send', text)
  nextTick(() => inputEl.value?.focus())
}

function fillSuggestion(text) {
  draft.value = text
  nextTick(() => inputEl.value?.focus())
}
</script>

<style scoped>
.chat-view { display: flex; flex-direction: column; height: 100%; }

.hero {
  flex: 1; position: relative; z-index: 2;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  text-align: center; gap: 24px; padding: 48px 24px 0;
}
.hero-eyebrow {
  display: inline-flex; align-items: center; gap: 8px;
  background: rgba(255,255,255,.07); border: 1px solid rgba(255,255,255,.15);
  border-radius: 20px; padding: 6px 16px; font-size: 12px; color: #9ca3af;
}
.hero-pulse {
  width: 6px; height: 6px; border-radius: 50%; background: #22d3ee;
  animation: pulse 2s ease-in-out infinite;
}
@keyframes pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.5;transform:scale(.8)} }

.hero-title {
  font-size: clamp(40px, 7vw, 68px); font-weight: 800; line-height: 1.1;
  background: linear-gradient(135deg, #fff 0%, #c4b5fd 50%, #67e8f9 100%);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
}
.hero-sub { font-size: 15px; color: #6b7280; max-width: 420px; }

.hero-input { max-width: 580px; width: 100%; margin: 0; padding: 0; }

.hero-chips { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; max-width: 580px; }
.hero-chip {
  background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.12);
  border-radius: 20px; padding: 7px 16px; font-size: 13px; color: #9ca3af;
  cursor: pointer; transition: all .2s;
}
.hero-chip:hover { background: rgba(255,255,255,.12); color: #e5e7eb; border-color: rgba(255,255,255,.25); }

.chat-messages { flex: 1; position: relative; z-index: 2; }

.typing-bubble { display: flex; gap: 5px; align-items: center; padding: 14px 18px; }
.typing-dot {
  width: 7px; height: 7px; border-radius: 50%; background: #a78bfa;
  animation: blink 1.2s infinite;
}
.typing-dot:nth-child(2) { animation-delay: .2s; }
.typing-dot:nth-child(3) { animation-delay: .4s; }
@keyframes blink { 0%,80%,100%{opacity:.2} 40%{opacity:1} }
</style>
