// src/api/prom.ts
import { http } from '@/api/http'

export type PromResp<T = any> = {
  status: 'success' | 'error'
  data: T
}

export function promQuery(query: string) {
  return http.get('/api/prom/query', { params: { query } })
}

export function promQueryRange(params: {
  query: string
  start: number
  end: number
  step: number
}) {
  return http.get('/api/prom/query_range', { params })
}

export function fetchPromOverview(range: string) {
  return http.get<PromResp>('/api/prom/overview', { params: { range } })
}
