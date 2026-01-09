// src/stores/auth.ts
import { defineStore } from 'pinia'
import { loginApi, changePasswordApi, type LoginReq } from '@/api/auth'

export type UserInfo = {
  username: string
  status?: string
  mustChange?: boolean

  // 你之前预留的字段也保留，后面做租户登录可用
  roles?: string[]
  tenantId?: string
  tenantName?: string
}

const LS_TOKEN = 'cs_token'
const LS_USER = 'cs_user'

function readJSON<T>(key: string): T | null {
  const raw = localStorage.getItem(key)
  if (!raw) return null
  try {
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem(LS_TOKEN) || '',
    user: readJSON<UserInfo>(LS_USER),
  }),

  getters: {
    isAuthed: (s) => !!s.token,
    username: (s) => s.user?.username || '',
    mustChange: (s) => !!s.user?.mustChange,
  },

  actions: {
    setLogin(token: string, user: UserInfo) {
      this.token = token
      this.user = user
      localStorage.setItem(LS_TOKEN, token)
      localStorage.setItem(LS_USER, JSON.stringify(user))
    },

    clear() {
      this.token = ''
      this.user = null
      localStorage.removeItem(LS_TOKEN)
      localStorage.removeItem(LS_USER)
    },

    // ✅ 登录：写入 token + user.mustChange
    async login(payload: LoginReq) {
      const resp = await loginApi(payload)
      this.setLogin(resp.access_token, resp.user)
      return resp
    },

    // ✅ 首登改密：成功后后端返回新 token + mustChange=false
    async changePassword(oldPassword: string, newPassword: string) {
      const resp = await changePasswordApi({ oldPassword, newPassword })
      this.setLogin(resp.access_token, resp.user)
      return resp
    },
  },
})
