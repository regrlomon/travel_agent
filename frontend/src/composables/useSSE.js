import { ref } from 'vue'

export function useSSE() {
  const phase = ref('idle')         // idle | chat | progress | review | done | error
  const messages = ref([])          // [{role:'ai'|'user', text:string}]
  const progressItems = ref([])     // [{node, message, pct}]
  const reviewData = ref(null)      // {message, plans:[...]}
  const finalResult = ref(null)     // compose_output result
  const error = ref(null)
  const confirmData = ref(null)
  const interestsData = ref(null)

  let jobId = null
  let interruptId = null
  let eventSource = null

  async function startChat(userText) {
    messages.value = []
    progressItems.value = []
    reviewData.value = null
    finalResult.value = null
    error.value = null
    confirmData.value = null
    interestsData.value = null
    phase.value = 'chat'

    if (userText) {
      messages.value.push({ role: 'user', text: userText })
    }

    const resp = await fetch('/plans', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: userText }),
    })
    const data = await resp.json()
    jobId = data.job_id
    _openSSE()
  }

  function _openSSE() {
    if (eventSource) eventSource.close()
    eventSource = new EventSource(`/plans/${jobId}/events`)

    eventSource.onmessage = (e) => {
      const msg = JSON.parse(e.data)

      if (msg.type === 'hitl_request') {
        interruptId = msg.interrupt_id
        const d = msg.data
        if (d.type === 'collect_intent') {
          phase.value = 'chat'
          messages.value.push({ role: 'ai', text: d.message })
        } else if (d.type === 'select_interests') {
          phase.value = 'interests'
          interestsData.value = d
        } else if (d.type === 'confirm_intent') {
          phase.value = 'confirm'
          confirmData.value = d.summary
        } else if (d.type === 'review_plan') {
          phase.value = 'review'
          reviewData.value = d
        }
      } else if (msg.type === 'progress') {
        phase.value = 'progress'
        progressItems.value.push(msg)
      } else if (msg.type === 'done') {
        finalResult.value = msg.result
        phase.value = 'done'
        eventSource.close()
      } else if (msg.type === 'error') {
        error.value = msg.message
        phase.value = 'error'
        eventSource.close()
      }
    }

    eventSource.onerror = () => {
      error.value = '连接中断，请刷新页面重试'
      phase.value = 'error'
      eventSource.close()
    }
  }

  async function sendReply(text) {
    if (!jobId || !interruptId) return

    messages.value.push({ role: 'user', text })

    await fetch(`/plans/${jobId}/reply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, interrupt_id: interruptId }),
    })

    if (phase.value === 'review') {
      phase.value = 'progress'
    }
    // For chat phase: wait for next SSE hitl_request
  }

  return {
    phase, messages, progressItems, reviewData, finalResult, error,
    confirmData, interestsData,
    startChat, sendReply,
  }
}
