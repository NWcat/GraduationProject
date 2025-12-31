// src/api/logs.ts
import {http} from '@/api/http' // ⚠️按你项目实际 axios 实例路径改
// 如果你是直接用 axios：import axios from 'axios'

export type LogLevel = 'info' | 'warn' | 'error'

export type LokiLabels = {
  namespace?: string
  pod?: string
  container?: string
  level?: LogLevel
  stream?: string
  [k: string]: string | undefined
}

export type LogRow = {
  id: string
  ts: string
  stream: string
  line: string
  labels: LokiLabels
}

type LogsResp = {
  status: 'success' | 'error'
  data?: { items: LogRow[] }
  error?: string
}

export function logsRange(params: { query: string; minutes: number; limit?: number; direction?: 'backward' | 'forward' }) {
  return http.get<LogsResp>('/api/logs/range', { params })
}

export function logsInstant(params: { query: string; limit?: number; time?: string; direction?: 'backward' | 'forward' }) {
  return http.get<LogsResp>('/api/logs/instant', { params })
}
