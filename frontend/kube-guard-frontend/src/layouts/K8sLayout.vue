<!-- src/layouts/K8sLayout.vue -->
<template>
  <div class="k8s-dashboard">
    <el-container class="dashboard-container">
      <!-- 顶部 Header -->
      <el-header class="top-header">
        <div class="top-left">
          <div class="top-logo">
            <div class="logo-mark">K8</div>
            <div class="logo-text">
              <div class="logo-title">CloudSphere</div>
              <div class="logo-subtitle">Enterprise K8s</div>
            </div>
          </div>
        </div>

        <div class="top-center"></div>

        <div class="top-right">
          <el-button-group class="header-actions">
            <el-button class="header-icon-btn" text size="small">
              <el-icon><Search /></el-icon>
            </el-button>
            <el-button class="header-icon-btn" text size="small">
              <el-icon><Bell /></el-icon>
            </el-button>
          </el-button-group>

          <el-dropdown trigger="click" @command="handleUserCommand">
            <div class="user-info">
              <el-avatar
                class="user-avatar"
                size="small"
                src="https://avatars.githubusercontent.com/u/9919?s=200&v=4"
              />
              <span class="user-name">{{ userName }}</span>
              <el-icon class="dropdown-icon"><ArrowDown /></el-icon>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="switch">切换用户</el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出用户</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <!-- 下方：Sidebar + 主体 -->
      <el-container class="body-container">
        <!-- Sidebar -->
        <el-aside :width="asideWidth" class="sidebar">
          <!-- 顶部折叠按钮 -->
          <div class="sidebar-top">
            <el-tooltip :content="isCollapse ? '展开导航' : '收起导航'" placement="right">
              <el-button class="collapse-btn" text @click="toggleCollapse">
                <el-icon>
                  <Expand v-if="isCollapse" />
                  <Fold v-else />
                </el-icon>
              </el-button>
            </el-tooltip>
          </div>

          <el-menu
            class="sidebar-menu"
            router
            :default-active="$route.path"
            :collapse="isCollapse"
            :collapse-transition="false"
            background-color="transparent"
            text-color="var(--sidebar-text)"
            active-text-color="var(--brand)"
          >
            <el-menu-item index="/overview">
              <el-tooltip content="概述" placement="right" :disabled="!isCollapse">
                <div class="menu-item-inner">
                  <el-icon class="menu-icon"><DataBoard /></el-icon>
                  <span class="menu-text">概述</span>
                </div>
              </el-tooltip>
            </el-menu-item>

            <el-sub-menu index="nodes">
              <template #title>
                <el-tooltip content="节点" placement="right" :disabled="!isCollapse">
                  <div class="menu-item-inner">
                    <el-icon class="menu-icon"><Cpu /></el-icon>
                    <span class="menu-text">节点</span>
                  </div>
                </el-tooltip>
              </template>
              <el-menu-item index="/nodes">节点列表</el-menu-item>
            </el-sub-menu>

            <el-sub-menu index="workloads">
              <template #title>
                <el-tooltip content="应用负载" placement="right" :disabled="!isCollapse">
                  <div class="menu-item-inner">
                    <el-icon class="menu-icon"><Box /></el-icon>
                    <span class="menu-text">应用负载</span>
                  </div>
                </el-tooltip>
              </template>
              <el-menu-item index="/workloads">工作负载概览</el-menu-item>
            </el-sub-menu>

            <el-sub-menu index="tenants">
              <template #title>
                <el-tooltip content="租户管理" placement="right" :disabled="!isCollapse">
                  <div class="menu-item-inner">
                    <el-icon class="menu-icon"><UserFilled /></el-icon>
                    <span class="menu-text">租户管理</span>
                  </div>
                </el-tooltip>
              </template>
              <el-menu-item index="/tenants">租户与命名空间</el-menu-item>
              <el-menu-item index="/namespaces">命名空间</el-menu-item>
            </el-sub-menu>

            <el-sub-menu index="monitor">
              <template #title>
                <el-tooltip content="监控告警" placement="right" :disabled="!isCollapse">
                  <div class="menu-item-inner">
                    <el-icon class="menu-icon"><Bell /></el-icon>
                    <span class="menu-text">监控告警</span>
                  </div>
                </el-tooltip>
              </template>
              <el-menu-item index="/monitor">监控总览</el-menu-item>
              <el-menu-item index="/metrics">监控指标查询</el-menu-item>
              <el-menu-item index="/monitor-wall">监控大屏</el-menu-item>
            </el-sub-menu>

            <el-sub-menu index="logs">
              <template #title>
                <el-tooltip content="日志管理" placement="right" :disabled="!isCollapse">
                  <div class="menu-item-inner">
                    <el-icon class="menu-icon"><Document /></el-icon>
                    <span class="menu-text">日志管理</span>
                  </div>
                </el-tooltip>
              </template>
              <el-menu-item index="/logs">日志检索</el-menu-item>
            </el-sub-menu>

            <el-sub-menu index="aiops">
              <template #title>
                <el-tooltip content="智能运维" placement="right" :disabled="!isCollapse">
                  <div class="menu-item-inner">
                    <el-icon class="menu-icon"><SetUp /></el-icon>
                    <span class="menu-text">智能运维</span>
                  </div>
                </el-tooltip>
              </template>

              <el-menu-item index="/ai/forecast">资源预测</el-menu-item>
              <el-menu-item index="/ai/suggestions">智能建议</el-menu-item>
              <el-menu-item index="/ai/heal">Pod 自愈</el-menu-item>
            </el-sub-menu>
          </el-menu>

          <!-- ✅ 底部固定区：保留 + 可跳转 + 选中高亮 -->
          <div class="sidebar-bottom">
            <el-tooltip content="设置" placement="right" :disabled="!isCollapse">
              <el-button
                class="bottom-btn"
                :class="{ 'bottom-btn-active': isSettingsActive }"
                text
                @click="goSettings"
              >
                <el-icon><Setting /></el-icon>
                <span v-if="!isCollapse" class="bottom-text">设置</span>
              </el-button>
            </el-tooltip>
          </div>
        </el-aside>

        <!-- 主内容区 -->
        <el-main class="main">
          <div class="page-header">
            <div class="page-title">{{ $route.meta.title || '概述' }}</div>
            <div class="page-subtitle">企业级 Kubernetes 集群管理平台</div>
          </div>

          <div class="main-layout">
            <router-view />
          </div>
        </el-main>
      </el-container>
    </el-container>
    <AiAssistantFloat />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import AiAssistantFloat from '@/components/AiAssistantFloat.vue'
import {
  DataBoard,
  Cpu,
  Box,
  UserFilled,
  Bell,
  Document,
  SetUp,
  ArrowDown,
  Search,
  Fold,
  Expand,
  Setting,
} from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

// ✅ 真实用户名：优先从 auth 里拿（你 auth 没有 userName 的话，先显示 username/token 的占位也行）
const userName = computed(() => auth.user?.username || 'admin')

const isCollapse = ref(false)
const asideWidth = computed(() => (isCollapse.value ? '64px' : '220px'))
const toggleCollapse = () => (isCollapse.value = !isCollapse.value)

// ✅ 高亮：当前在 /settings 时，底部按钮也像 menu-item 一样亮
const isSettingsActive = computed(() => route.path === '/settings')

// ✅ 跳转：如果你已经在 settings 就不重复 push（避免重复导航警告）
function goSettings() {
  if (route.path !== '/settings') {
    router.push('/settings')
  }
}

async function doLogout(mode: 'switch' | 'logout') {
  if (mode === 'logout') {
    await ElMessageBox.confirm('确定要退出当前账号吗？', '退出登录', { type: 'warning' })
  }
  auth.clear()
  router.replace({
    path: '/login',
    query: mode === 'switch' ? { mode: 'switch' } : {},
  })
}

const handleUserCommand = (command: 'switch' | 'logout') => {
  if (command === 'switch' || command === 'logout') {
    auth.clear()
    router.replace('/login')
  }
}
</script>

<style scoped>
/* ====== 主题变量 ====== */
.k8s-dashboard {
  --brand: #3b82f6;

  --app-bg: #eef3fb;
  --header-bg: #f6f8fc;
  --header-border: rgba(15, 23, 42, 0.08);

  --sidebar-bg: #f3f6fc;
  --sidebar-border: rgba(15, 23, 42, 0.08);
  --sidebar-text: #475569;

  --main-bg: #eef3fb;

  height: 100vh;
  background: var(--app-bg);
  color: #0f172a;
  font-size: 14px;
}

.dashboard-container {
  height: 100vh;
}

/* ====== Header ====== */
.top-header {
  height: 56px;
  padding: 0 16px;
  background: var(--header-bg);
  border-bottom: 1px solid var(--header-border);
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 12px;
}

.top-logo {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo-mark {
  width: 34px;
  height: 34px;
  border-radius: 12px;
  background: linear-gradient(135deg, #3b82f6, #22c55e);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  font-size: 14px;
  color: #f8fafc;
  box-shadow: 0 6px 16px rgba(59, 130, 246, 0.18);
}

.logo-text {
  display: flex;
  flex-direction: column;
  line-height: 1.05;
}

.logo-title {
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
}

.logo-subtitle {
  font-size: 11px;
  color: #64748b;
}

.top-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-icon-btn {
  color: #64748b;
}
.header-icon-btn:hover {
  color: #0f172a;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.04);
  border: 1px solid rgba(15, 23, 42, 0.06);
  cursor: pointer;
}
.user-info:hover {
  background: rgba(15, 23, 42, 0.06);
}
.user-name {
  color: #0f172a;
  font-weight: 600;
}
.dropdown-icon {
  font-size: 14px;
  color: #64748b;
}

/* ====== Body ====== */
.body-container {
  height: calc(100vh - 56px);
}

/* ====== Sidebar ====== */
.sidebar {
  background: var(--sidebar-bg);
  border-right: 1px solid var(--sidebar-border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: width 0.18s ease;
}

.sidebar-top {
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-bottom: 1px solid rgba(15, 23, 42, 0.06);
}

.collapse-btn {
  color: #475569;
}
.collapse-btn:hover {
  color: #0f172a;
  background: rgba(59, 130, 246, 0.08);
  border-radius: 10px;
}

.sidebar-menu {
  border-right: none;
  flex: 1;
  padding-top: 8px;
}

/* 菜单项内部 */
.menu-item-inner {
  display: flex;
  align-items: center;
}
.menu-icon {
  margin-right: 10px;
  color: #64748b;
}

/* ====== ✅ Active Indicator：选中态左侧指示条 ====== */
:deep(.el-menu-item),
:deep(.el-sub-menu__title) {
  position: relative;
  margin: 2px 8px;
  border-radius: 10px;
}

/* hover：淡底 */
:deep(.el-menu-item:hover),
:deep(.el-sub-menu__title:hover) {
  background: rgba(59, 130, 246, 0.08) !important;
}

/* el-menu-item active：淡底 + 品牌色文字 */
:deep(.el-menu-item.is-active) {
  background: rgba(59, 130, 246, 0.12) !important;
  color: var(--brand) !important;
}
:deep(.el-menu-item.is-active) .menu-icon {
  color: var(--brand) !important;
}

:deep(.el-menu-item.is-active)::before {
  content: '';
  position: absolute;
  left: 0;
  top: 10px;
  bottom: 10px;
  width: 3px;
  border-radius: 999px;
  background: var(--brand);
  box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.06);
}

:deep(.el-sub-menu.is-active > .el-sub-menu__title)::before,
:deep(.el-sub-menu.is-opened > .el-sub-menu__title)::before {
  content: '';
  position: absolute;
  left: 0;
  top: 10px;
  bottom: 10px;
  width: 3px;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.6);
}

/* ====== collapse：只显示 icon ====== */
:deep(.el-menu--collapse) .menu-text {
  display: none !important;
}
:deep(.el-menu--collapse) .el-menu-item,
:deep(.el-menu--collapse) .el-sub-menu__title {
  justify-content: center !important;
}
:deep(.el-menu--collapse) .menu-icon {
  margin-right: 0 !important;
}

/* ====== Sidebar Bottom ====== */
.sidebar-bottom {
  padding: 8px;
  border-top: 1px solid rgba(15, 23, 42, 0.06);
  display: flex;
  justify-content: center;
}

/* ✅ 保持底部固定区按钮可点 & 全宽 */
.bottom-btn {
  width: 100%;
  display: flex;
  justify-content: center;
  gap: 8px;
  color: #475569;
  border-radius: 10px;
}
.bottom-btn:hover {
  background: rgba(59, 130, 246, 0.08);
  color: #0f172a;
}
.bottom-text {
  font-size: 13px;
}

/* ✅ 底部“设置”选中态（模拟 el-menu-item.is-active 的视觉） */
.bottom-btn-active {
  background: rgba(59, 130, 246, 0.12) !important;
  color: var(--brand) !important;
  position: relative;
}
.bottom-btn-active :deep(.el-icon) {
  color: var(--brand) !important;
}
.bottom-btn-active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 10px;
  bottom: 10px;
  width: 3px;
  border-radius: 999px;
  background: var(--brand);
  box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.06);
}

/* ====== Main ====== */
.main {
  background: var(--main-bg);
  padding: 14px 18px 18px;
  overflow: auto;
}

.page-header {
  margin-bottom: 12px;
}
.page-title {
  font-size: 18px;
  font-weight: 700;
  color: #0f172a;
}
.page-subtitle {
  font-size: 12px;
  color: #64748b;
  margin-top: 4px;
}

.main-layout {
  max-width: 1600px;
}

@media (max-width: 1024px) {
  .main {
    padding: 12px;
  }
  .main-layout {
    max-width: 100%;
  }
}
</style>
