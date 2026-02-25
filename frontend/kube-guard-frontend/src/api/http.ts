// src/api/http.ts
import axios, { type AxiosInstance, type AxiosRequestConfig, type AxiosResponse } from 'axios'
import { ElMessage } from 'element-plus'
import router from '@/router'
import { useAuthStore } from '@/stores/auth'

/**
 * ✅ baseURL 推荐从 .env 读：
 * VITE_API_BASE_URL=http://127.0.0.1:8000
 * 不配也行（同域反代 / devServer proxy）
 */
const baseURL = import.meta.env.VITE_API_BASE_URL || ''

function genRequestId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

export const http: AxiosInstance = axios.create({
  baseURL,
  timeout: 15000,
  withCredentials: true,
})

http.interceptors.request.use((config) => {
  // ✅ 统一 token key
  const auth = useAuthStore()
  const token = auth.token || localStorage.getItem('cs_token') || ''
  if (token) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Bearer ${token}`
  }
  config.headers = config.headers || {}
  if (!config.headers['X-Request-Id']) {
    config.headers['X-Request-Id'] = genRequestId()
  }
  return config
})

http.interceptors.response.use(
  (resp: AxiosResponse) => resp,
  async (err) => {
    const status = err?.response?.status

    // ✅ 403：权限不足，不清 token，不跳转登录
    if (status === 403) {
      err.__ai_handled = true
      ElMessage.warning('权限不足')
      return Promise.reject(err)
    }

    // ✅ 401：token 失效/未登录，清理并回登录
    if (status === 401) {
      err.__ai_handled = true
      try {
        const auth = useAuthStore()
        auth.clear()
      } catch {
        localStorage.removeItem('cs_token')
        localStorage.removeItem('cs_user')
      }

      if (router.currentRoute.value.path !== '/login') {
        await router.replace({ path: '/login', query: { redirect: router.currentRoute.value.fullPath } })
      }
      return Promise.reject(err)
    }

    const requestId =
      err?.config?.headers?.['X-Request-Id'] || err?.response?.headers?.['x-request-id']
    const detail = err?.response?.data?.detail || err?.message || 'Network Error'
    if (requestId) {
      console.warn(`[request_id=${requestId}] ${detail}`)
    }
    return Promise.reject(err)
  }
)

/** 统一 get/post 的类型封装（可选，但写起来爽） */
export async function get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
  const resp = await http.get(url, config)
  return resp.data as T
}

export async function post<T>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> {
  const resp = await http.post(url, data, config)
  return resp.data as T
}

// src/api/http.ts （在 post<T> 后面追加）
export async function del<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
  const resp = await http.delete(url, config)
  return resp.data as T
}

export async function put<T>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> {
  const resp = await http.put(url, data, config)
  return resp.data as T
}

export async function patch<T>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> {
  const resp = await http.patch(url, data, config)
  return resp.data as T
}
