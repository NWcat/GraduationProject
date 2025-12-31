// src/router/index.ts
import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import K8sLayout from '@/layouts/K8sLayout.vue'
import { useAuthStore } from '@/stores/auth'

const routes: RouteRecordRaw[] = [
  // ✅ 登录页：独立
  {
    path: '/login',
    name: 'LoginView',
    component: () => import('@/views/LoginView.vue'),
    meta: { title: '登录' },
  },

  // ✅ 首登改密：独立（建议）
  {
    path: '/change-password',
    name: 'ChangePassword',
    component: () => import('@/views/ChangePasswordView.vue'),
    meta: { title: '首次登录改密', requiresAuth: true },
  },

  // ✅ 监控大屏（独立）
  {
    path: '/monitor-wall',
    name: 'MonitorWall',
    component: () => import('@/views/MonitorWall.vue'),
    meta: {
      title: '监控大屏',
      requiresAuth: true,
      fullscreen: true, // 语义化标记（可选）
    },
  },

  // ✅ 业务区：走 Layout
  {
    path: '/',
    component: K8sLayout,
    redirect: '/overview',
    children: [
      { path: 'overview', name: 'Overview', component: () => import('@/views/Overview.vue'), meta: { title: '概述', requiresAuth: true } },
      { path: 'tools/kubectl', name: 'KubectlTerminal', component: () => import('@/views/KubectlTerminal.vue'), meta: { title: 'Kubectl 终端', requiresAuth: true } },
      { path: 'system', name: 'SystemStatus', component: () => import('@/views/SystemStatus.vue'), meta: { title: '系统状态监控', requiresAuth: true } },
      { path: 'home', name: 'Home', component: () => import('@/views/Home.vue'), meta: { title: '首页', requiresAuth: true } },
      { path: 'nodes', name: 'NodeList', component: () => import('@/views/NodeList.vue'), meta: { title: '节点', requiresAuth: true } },
      { path: 'workloads', name: 'Workloads', component: () => import('@/views/WorkloadsOverview.vue'), meta: { title: '应用负载', requiresAuth: true } },
      { path: 'monitor', name: 'MonitorOverview', component: () => import('@/views/MonitorOverview.vue'), meta: { title: '监控总览', requiresAuth: true } },
      { path: 'metrics', name: 'MetricsQuery', component: () => import('@/views/MetricsQuery.vue'), meta: { title: '监控指标查询', requiresAuth: true } },

      { path: 'tenants', name: 'TenantsList', component: () => import('@/views/Tenants/NamespaceList.vue'), meta: { title: '租户与命名空间', requiresAuth: true } },
      { path: 'namespaces', name: 'Namespaces', component: () => import('@/views/Tenants/Namespaces.vue'), meta: { title: '命名空间', requiresAuth: true } },
      { path: 'tenants/:id', name: 'TenantDetail', component: () => import('@/views/Tenants/NamespaceDetail.vue'), meta: { title: '租户详情', hideInMenu: true, requiresAuth: true } },

      { path: 'logs', name: 'LogSearch', component: () => import('@/views/Logs/LogSearch.vue'), meta: { title: '日志检索', requiresAuth: true } },
      { path: 'logs/detail', name: 'LogDetail', component: () => import('@/views/Logs/LogDetail.vue'), meta: { title: '日志详情', requiresAuth: true } },
    ],
  },

  // // ✅ 兜底 404
  // { path: '/:pathMatch(.*)*', name: 'NotFound', component: () => import('@/views/NotFound.vue') },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const auth = useAuthStore()

  // 需要登录但没登录 -> 去 login
  if (to.meta.requiresAuth && !auth.isAuthed) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }

  // 已登录访问 login -> 去 redirect 或 overview
  if (to.path === '/login' && auth.isAuthed) {
    const redirect = (to.query.redirect as string) || '/overview'
    return { path: redirect }
  }

  // ✅ mustChange 强制改密：
  // 只要 mustChange=true，除了 /change-password 以外都拦截
  if (auth.isAuthed && auth.mustChange && to.path !== '/change-password') {
    return { path: '/change-password', query: { redirect: to.fullPath } }
  }

  // 改密完成后，如果 mustChange=false，访问改密页就回去
  if (auth.isAuthed && !auth.mustChange && to.path === '/change-password') {
    const redirect = (to.query.redirect as string) || '/overview'
    return { path: redirect }
  }

  return true
})

export default router
export { router }