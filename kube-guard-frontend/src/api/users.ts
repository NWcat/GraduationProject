// src/api/users.ts
import axios from 'axios'

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000',
  timeout: 15000,
})

export async function resetPassword(payload: {
  username: string
}): Promise<{ ok: boolean; oneTimePassword: { username: string; password: string } }> {
  const { data } = await http.post('/api/users/reset-password', payload)
  return data
}

export async function toggleUser(payload: {
  username: string
}): Promise<{ ok: boolean; status: 'active' | 'disabled' }> {
  const { data } = await http.post('/api/users/toggle', payload)
  return data
}