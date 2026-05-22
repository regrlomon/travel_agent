import { ref } from 'vue'

export function useWebSocket() {
  const step = ref(0)          // 0=idle, 1=confirm, 2=progress, 3=review, 4=results
  const hitlData = ref(null)   // full hitl_request message (includes interrupt_id)
  const progress = ref([])
  const result = ref(null)
  const error = ref(null)
  let ws = null
  let jobId = null

  function connect(id) {
    jobId = id
    ws = new WebSocket(`/ws/${jobId}`)

    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data)
      if (msg.type === 'hitl_request') {
        hitlData.value = msg
        step.value = msg.data.type === 'confirm_params' ? 1 : 3
      } else if (msg.type === 'progress') {
        progress.value.push(msg)
        if (step.value !== 3) step.value = 2
      } else if (msg.type === 'done') {
        result.value = msg.result
        step.value = 4
      }
    }

    ws.onerror = () => { error.value = 'WebSocket error' }
    ws.onclose = () => {
      // auto-reconnect after 2s (server replays from last_id=0 so no messages lost)
      if (step.value < 4) setTimeout(() => connect(jobId), 2000)
    }
  }

  async function startPlan(requestData) {
    progress.value = []
    result.value = null
    error.value = null
    step.value = 1

    const resp = await fetch('/plans', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestData),
    })
    const { job_id } = await resp.json()
    connect(job_id)
    return job_id
  }

  function sendReply(text) {
    if (!ws || !hitlData.value) return
    ws.send(JSON.stringify({
      type: 'hitl_response',
      text,
      interrupt_id: hitlData.value.interrupt_id,   // carry forward interrupt_id for idempotency
    }))
    step.value = 2
  }

  return { step, hitlData, progress, result, error, startPlan, sendReply }
}
