// src/api/namespaces.ts
import { get, post } from '@/api/http'

export type NamespaceItem = {
  name: string
  labels: Record<string, string>
  phase?: string | null
  createdAt?: string | null
  system: boolean
  managed: boolean
  managedByTenantId?: string | null
}

export function fetchNamespaceOptions(): Promise<{ items: string[] }> {
  return get('/api/namespaces/options')
}

export function fetchNamespaces(params?: { keyword?: string }): Promise<{ items: NamespaceItem[] }> {
  return get('/api/namespaces', { params })
}

export function createNamespace(body: {
  name: string
  labels?: Record<string, string>
  managed?: boolean
  managedByTenantId?: string
}): Promise<{ item: NamespaceItem }> {
  return post('/api/namespaces', body)
}

export async function patchNamespaceLabels(
  name: string,
  labels: Record<string, string>
): Promise<{ item: NamespaceItem }> {
  // 你没写 patch wrapper，这里直接用 get/post 思路写一个最简单的：
  const { http } = await import('@/api/http')
  const resp = await http.patch(`/api/namespaces/${encodeURIComponent(name)}/labels`, { labels })
  return resp.data as { item: NamespaceItem }
}

export async function deleteNamespace(name: string, purgeRegistry = true): Promise<{ ok: boolean }> {
  const { http } = await import('@/api/http')
  const resp = await http.delete(`/api/namespaces/${encodeURIComponent(name)}`, {
    params: { purge_registry: purgeRegistry },
  })
  return resp.data as { ok: boolean }
}
