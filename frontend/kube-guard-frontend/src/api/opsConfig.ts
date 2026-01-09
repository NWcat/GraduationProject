import { http } from '@/api/http'

export type ConfigItem = {
  k: string
  type: 'str' | 'int' | 'bool' | 'float'
  desc: string
  secret: boolean
  source: 'db' | 'env'
  value: any
  default: any
  has_override: boolean
  has_value: boolean
  example: string
  choices: string[]
}

export function fetchOpsConfig() {
  return http.get('/api/ops/config')
}

export function saveOpsConfig(items: Record<string, any>) {
  return http.put('/api/ops/config', { items })
}

export function deleteOpsConfigKey(key: string) {
  return http.delete(`/api/ops/config/${encodeURIComponent(key)}`)
}
