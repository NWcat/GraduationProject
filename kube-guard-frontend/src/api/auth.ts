// src/api/auth.ts
import { post } from '@/api/http'
import type { UserInfo } from '@/stores/auth'

export type LoginReq = { username: string; password: string }

export type LoginResp = {
  access_token: string
  token_type?: string
  user: UserInfo
}

// ✅ 你的后端如果是 /api/auth/login，就写这个；
// 如果你后端是 /auth/login，就把这里改一下
export function loginApi(data: LoginReq) {
  return post<LoginResp>('/auth/login', data)
}

export type ChangePwdReq = { oldPassword: string; newPassword: string }

export type ChangePwdResp = {
  ok: boolean
  access_token: string
  token_type?: string
  user: UserInfo
}

export function changePasswordApi(data: ChangePwdReq) {
  return post<ChangePwdResp>('/auth/change-password', data)
}