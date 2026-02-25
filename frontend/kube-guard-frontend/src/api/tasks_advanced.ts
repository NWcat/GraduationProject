// 前端高级任务管理 API
// 文件位置：src/api/tasks_advanced.ts

import { http } from '@/api/http'

export interface TaskActionResp {
  code: number
  message: string
  data: {
    task_id: string
    status: string
    [key: string]: any
  }
}

export interface TaskStatsResp {
  code: number
  data: {
    total: number
    success: number
    failed: number
    cancelled: number
    paused: number
    success_rate: number
    avg_duration: number
    by_type: Record<string, { total: number; success: number; failed: number }>
    by_day: Array<{ day: string; total: number; success: number; failed: number }>
  }
}

export interface TaskHistoryResp {
  code: number
  data: {
    timeline: Array<{
      timestamp: number
      event: 'task_created' | 'task_started' | 'task_completed'
      task_id: string
      status: string
    }>
  }
}

/**
 * 取消任务
 */
export function cancelTask(task_id: string) {
  return http.post<TaskActionResp>(`/tasks/${encodeURIComponent(task_id)}/cancel`)
}

/**
 * 暂停任务
 */
export function pauseTask(task_id: string) {
  return http.post<TaskActionResp>(`/tasks/${encodeURIComponent(task_id)}/pause`)
}

/**
 * 恢复暂停的任务
 */
export function resumeTask(task_id: string) {
  return http.post<TaskActionResp>(`/tasks/${encodeURIComponent(task_id)}/resume`)
}

/**
 * 删除任务记录
 */
export function deleteTask(task_id: string, force: boolean = false) {
  return http.delete<TaskActionResp>(`/tasks/${encodeURIComponent(task_id)}`, {
    params: { force }
  })
}

/**
 * 批量删除任务
 */
export function deleteTasksBatch(task_ids: string[]) {
  return http.post<{ code: number; message: string; data: { deleted_count: number } }>(
    '/tasks/batch-delete',
    { task_ids }
  )
}

/**
 * 删除所有任务
 */
export function deleteAllTasks() {
  return http.delete<{ code: number; message: string; data: { deleted_count: number } }>('/tasks/all')
}


/**
 * 获取任务统计数据
 */
export function getTaskStats(task_type?: string, days: number = 7) {
  return http.get<TaskStatsResp>('/tasks/stats', {
    params: {
      task_type,
      days
    }
  })
}

/**
 * 获取任务执行历史时间线
 */
export function getTaskHistory(days: number = 7, task_type?: string, limit: number = 100) {
  return http.get<TaskHistoryResp>('/tasks/history', {
    params: {
      days,
      task_type,
      limit
    }
  })
}

/**
 * 在列表中提交任务时指定优先级
 */
export interface SubmitTaskWithPriorityParams {
  type: string
  payload: Record<string, any>
  priority?: number // 0-10，默认 0
  max_retries?: number // 默认 3
}

export function submitTaskWithPriority(params: SubmitTaskWithPriorityParams) {
  return http.post('/tasks/submit', params)
}