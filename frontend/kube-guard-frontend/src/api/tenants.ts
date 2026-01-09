// src/api/tenants.ts
import axios from 'axios'

export type TenantStatus = 'active' | 'disabled' | 'warning'
export type MemberRole = 'viewer' | 'editor' | 'admin'
export type MemberStatus = 'active' | 'disabled'

export type TenantRow = {
  id: string
  name: string
  status: TenantStatus
  adminUser: string
  namespaces: string[]
  labels: Record<string, string>
  quota: { cpu: string; memory: string }
  createdAt: string
}

export type TenantListResp = { items: TenantRow[] }

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000',
  timeout: 15000,
})

export async function fetchTenants(params?: {
  keyword?: string
  status?: TenantStatus
}): Promise<TenantListResp> {
  const { data } = await http.get('/api/tenants', { params })
  return data
}

export async function getTenant(id: string): Promise<{ tenant: TenantRow }> {
  const { data } = await http.get(`/api/tenants/${encodeURIComponent(id)}`)
  return data
}

export async function createTenant(payload: {
  name: string
  bindNamespace?: string
  autoCreateNamespace?: boolean // 默认 true（如果传了 bindNamespace）
  createAdminUser: boolean
  adminUsername?: string
  pwdMode?: 'auto' | 'manual'
  tempPassword?: string
  mustChangePassword?: boolean
  quotaCpu?: string
  quotaMem?: string
}): Promise<{
  tenant: TenantRow
  oneTimePassword?: { username: string; password: string }
}> {
  const { data } = await http.post('/api/tenants', payload)
  return data
}

export async function deleteTenant(params: {
  id: string
  deleteNamespaces?: boolean // 是否同时删除绑定的 namespace（危险）
}): Promise<{ ok: boolean }> {
  const { data } = await http.delete(`/api/tenants/${encodeURIComponent(params.id)}`, {
    params: { deleteNamespaces: params.deleteNamespaces ?? false },
  })
  return data
}

export async function toggleTenant(id: string): Promise<{ ok: boolean; status: TenantStatus }> {
  const { data } = await http.post(`/api/tenants/${encodeURIComponent(id)}/toggle`)
  return data
}

export async function bindTenantNamespace(payload: {
  id: string
  namespace: string
  autoCreate?: boolean
}): Promise<{ ok: boolean; namespaces: string[] }> {
  const { data } = await http.post(`/api/tenants/${encodeURIComponent(payload.id)}/namespaces`, {
    namespace: payload.namespace,
    autoCreate: payload.autoCreate ?? true,
  })
  return data
}

export async function unbindTenantNamespace(payload: {
  id: string
  namespace: string
}): Promise<{ ok: boolean; namespaces: string[] }> {
  const { data } = await http.delete(
    `/api/tenants/${encodeURIComponent(payload.id)}/namespaces/${encodeURIComponent(payload.namespace)}`
  )
  return data
}

export async function updateTenantLabels(payload: {
  id: string
  labels: Record<string, string>
}): Promise<{ ok: boolean; labels: Record<string, string> }> {
  const { data } = await http.put(`/api/tenants/${encodeURIComponent(payload.id)}/labels`, payload)
  return data
}

export async function updateTenantQuota(payload: {
  id: string
  cpu: string
  memory: string
}): Promise<{ ok: boolean; quota: { cpu: string; memory: string } }> {
  const { data } = await http.put(`/api/tenants/${encodeURIComponent(payload.id)}/quota`, payload)
  return data
}

// Members
export type TenantMember = {
  username: string
  email?: string
  role: MemberRole
  status: MemberStatus
  createdAt: string
}

export async function listTenantMembers(id: string): Promise<{ items: TenantMember[] }> {
  const { data } = await http.get(`/api/tenants/${encodeURIComponent(id)}/members`)
  return data
}

export async function addTenantMember(payload: {
  id: string
  username: string
  email?: string
  role: MemberRole
  pwdMode: 'auto' | 'manual'
  tempPassword?: string
  mustChange: boolean
}): Promise<{
  ok: boolean
  member: TenantMember
  oneTimePassword?: { username: string; password: string }
}> {
  const { data } = await http.post(`/api/tenants/${encodeURIComponent(payload.id)}/members`, payload)
  return data
}

export async function changeTenantMemberRole(payload: {
  id: string
  username: string
  role: MemberRole
}): Promise<{ ok: boolean }> {
  const { data } = await http.put(
    `/api/tenants/${encodeURIComponent(payload.id)}/members/${encodeURIComponent(payload.username)}/role`,
    payload
  )
  return data
}

export async function removeTenantMember(payload: {
  id: string
  username: string
}): Promise<{ ok: boolean }> {
  const { data } = await http.delete(
    `/api/tenants/${encodeURIComponent(payload.id)}/members/${encodeURIComponent(payload.username)}`
  )
  return data
}
