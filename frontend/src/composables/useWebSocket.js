import { ref } from 'vue'

export function useSSE() {
  const step = ref(0)          // 0=idle, 1=confirm, 2=progress, 3=review, 4=results
  const hitlData = ref(null)   // full hitl_request message (includes interrupt_id)
  const progress = ref([])
  const result = ref(null)
  const error = ref(null)
  let es = null
  let jobId = null

  function connect(id) {
    jobId = id
    es = new EventSource(`/plans/${jobId}/events`)

    es.onmessage = (e) => {
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
        es.close()
      }
    }

    es.onerror = () => {
      // EventSource 自动重连，done 之后关掉
      if (step.value === 4) es.close()
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

  async function sendReply(text) {
    if (!hitlData.value) return
    step.value = 2
    await fetch(`/plans/${jobId}/reply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text,
        interrupt_id: hitlData.value.interrupt_id,
      }),
    })
  }

  return { step, hitlData, progress, result, error, startPlan, sendReply }
}
