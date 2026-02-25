import { http } from '@/api/http'

export type K8sEventItem = {
  type: string
  reason: string
  message: string
  count: number
  first_timestamp: string
  last_timestamp: string
  namespace: string
  kind: string
  name: string
}

export function fetchEvents(params?: { namespace?: string; limit?: number; continue?: string }) {
  return http.get<{ items: K8sEventItem[]; continue: string }>('/api/events/list', { params })
}

