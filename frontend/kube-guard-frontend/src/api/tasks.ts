import { http } from '@/api/http'

export type TaskStatus = 'PENDING' | 'RUNNING' | 'SUCCESS' | 'FAILED' | 'UNKNOWN' | 'RESTRICTED'

export type TaskItem = {
  task_id: string
  type: string
  status: TaskStatus
  progress: number
  error: string
  created_at: number
  updated_at: number
}

export type TaskDetail = TaskItem & {
  input?: any
  input_json?: string
  result?: any
  result_json?: string
  attempts?: number
  started_at?: number
  finished_at?: number
  worker_id?: string
}

export function fetchTasks(params?: { status?: string; type?: string; limit?: number; offset?: number }) {
  return http.get<{ items: TaskItem[] }>('/api/tasks/list', { params })
}

export function fetchTaskDetail(task_id: string) {
  return http.get<{ task: TaskItem & { result?: any } }>(`/api/tasks/${encodeURIComponent(task_id)}`)
}

export function submitTask(type: string, input: any) {
  return http.post<{ ok: boolean; task_id: string; status: TaskStatus }>('/api/tasks/submit', {
    type,
    payload: input ?? {}
  })
}

export function getTask(task_id: string) {
  return http.get<{ task: TaskDetail }>('/api/tasks/get', { params: { task_id } })
}

export function deleteTask(task_id: string) {
  return http.delete<{ ok: boolean; deleted_count: number }>(`/api/tasks/${encodeURIComponent(task_id)}`)
}

export function deleteTasksBatch(task_ids: string[]) {
  return http.post<{ ok: boolean; deleted_count: number }>('/api/tasks/batch-delete', { task_ids })
}

export function deleteAllTasks() {
  return http.delete<{ ok: boolean; deleted_count: number }>('/api/tasks/all')
}