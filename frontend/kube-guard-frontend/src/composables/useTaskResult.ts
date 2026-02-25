import { computed, onBeforeUnmount, ref } from 'vue'
import { getTask, type TaskDetail, type TaskStatus } from '@/api/tasks'

type UseTaskResultOptions = {
  intervalMs?: number
  timeoutMs?: number
}

function normalizeStatus(raw?: string): TaskStatus {
  if (!raw) return 'UNKNOWN'
  if (raw === 'DONE') return 'SUCCESS'
  if (raw === 'PENDING' || raw === 'RUNNING' || raw === 'SUCCESS' || raw === 'FAILED' || raw === 'UNKNOWN' || raw === 'RESTRICTED') {
    return raw
  }
  return 'UNKNOWN'
}

function extractErrorMessage(task: TaskDetail | null | undefined, fallback: string): string {
  const err = (task as any)?.error
  if (typeof err === 'string' && err) return err
  if (err && typeof err === 'object') {
    const detail = (err as any).detail || (err as any).message
    if (typeof detail === 'string' && detail) return detail
    try {
      return JSON.stringify(err)
    } catch {
      return fallback
    }
  }
  return fallback
}

function parseResult<T>(task: TaskDetail | null | undefined): T | null {
  const raw = (task as any)?.result_json ?? (task as any)?.result
  if (raw == null) return null
  if (typeof raw === 'string') {
    if (!raw) return null
    try {
      return JSON.parse(raw) as T
    } catch {
      return raw as unknown as T
    }
  }
  return raw as T
}

function extractRequestError(err: any): string {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string' && detail) return detail
  const message = err?.message
  return typeof message === 'string' && message ? message : '任务轮询失败'
}

export function useTaskResult<T = unknown>(baseOptions?: UseTaskResultOptions) {
  const taskId = ref('')
  const status = ref<TaskStatus>('PENDING')
  const task = ref<TaskDetail | null>(null)
  const result = ref<T | null>(null)
  const error = ref('')

  let timer: ReturnType<typeof setTimeout> | null = null
  let token = 0
  let startAt = 0
  let intervalMs = Math.max(200, Number(baseOptions?.intervalMs ?? 800))
  let timeoutMs = Math.max(1000, Number(baseOptions?.timeoutMs ?? 60000))

  const loading = computed(() => {
    const s = status.value
    return !!taskId.value && (s === 'PENDING' || s === 'RUNNING')
  })

  function stop() {
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
  }

  function reset() {
    status.value = 'PENDING'
    task.value = null
    result.value = null
    error.value = ''
  }

  async function pollOnce(currentToken: number) {
    try {
      const { data } = await getTask(taskId.value)
      if (currentToken !== token) return
      const nextTask = data?.task ?? null
      task.value = nextTask
      const nextStatus = normalizeStatus(nextTask?.status)
      status.value = nextStatus

      if (nextStatus === 'SUCCESS') {
        result.value = parseResult<T>(nextTask)
        return
      }
      if (nextStatus === 'FAILED' || nextStatus === 'UNKNOWN' || nextStatus === 'RESTRICTED') {
        error.value = extractErrorMessage(nextTask, nextStatus === 'RESTRICTED' ? '操作被禁止' : '任务执行失败')
        return
      }
      if (Date.now() - startAt > timeoutMs) {
        status.value = 'FAILED'
        error.value = '任务超时'
        return
      }
      timer = setTimeout(() => pollOnce(currentToken), intervalMs)
    } catch (err) {
      if (currentToken !== token) return
      status.value = 'FAILED'
      error.value = extractRequestError(err)
    }
  }

  function start(nextTaskId: string, options?: UseTaskResultOptions) {
    if (!nextTaskId) return
    stop()
    token += 1
    taskId.value = nextTaskId
    reset()
    startAt = Date.now()
    intervalMs = Math.max(200, Number(options?.intervalMs ?? baseOptions?.intervalMs ?? 800))
    timeoutMs = Math.max(1000, Number(options?.timeoutMs ?? baseOptions?.timeoutMs ?? 60000))
    pollOnce(token)
  }

  onBeforeUnmount(() => {
    stop()
  })

  return {
    taskId,
    status,
    task,
    result,
    error,
    loading,
    start,
    stop,
    reset
  }
}
