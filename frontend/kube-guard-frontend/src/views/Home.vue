<template>
  <div class="k8s-dashboard">
    <el-container class="dashboard-container">
      <!-- 侧边导航 -->
      <el-aside width="220px" class="sidebar">
        <div class="sidebar-logo">
          <div class="logo-mark">K8</div>
          <div class="logo-text">
            <div class="logo-title">CloudSphere</div>
            <div class="logo-subtitle">Enterprise K8s</div>
          </div>
        </div>

        <el-menu
          class="sidebar-menu"
          :default-active="activeMenu"
          background-color="transparent"
          text-color="#9ca3af"
          active-text-color="var(--brand-color)"
          router="false"
        >
          <el-menu-item index="overview">
            <el-icon class="menu-icon"><DataBoard /></el-icon>
            <span>概述</span>
          </el-menu-item>

          <el-sub-menu index="nodes">
            <template #title>
              <el-icon class="menu-icon"><Cpu /></el-icon>
              <span>节点</span>
            </template>
            <el-menu-item index="nodes-list">节点列表</el-menu-item>
            <el-menu-item index="nodes-monitor">节点监控</el-menu-item>
          </el-sub-menu>

          <el-sub-menu index="workloads">
            <template #title>
              <el-icon class="menu-icon"><Box /></el-icon>
              <span>应用负载</span>
            </template>
            <el-menu-item index="deployments">Deployment</el-menu-item>
            <el-menu-item index="statefulsets">StatefulSet</el-menu-item>
            <el-menu-item index="daemonsets">DaemonSet</el-menu-item>
            <el-menu-item index="services">Service</el-menu-item>
          </el-sub-menu>

          <el-sub-menu index="tenant">
            <template #title>
              <el-icon class="menu-icon"><UserFilled /></el-icon>
              <span>租户管理</span>
            </template>
            <el-menu-item index="namespaces">命名空间</el-menu-item>
            <el-menu-item index="tenant-users">用户与角色</el-menu-item>
            <el-menu-item index="quota">资源配额</el-menu-item>
          </el-sub-menu>

          <el-sub-menu index="monitor">
            <template #title>
              <el-icon class="menu-icon"><Bell /></el-icon>
              <span>监控告警</span>
            </template>
            <el-menu-item index="monitor-dashboard">监控大盘</el-menu-item>
            <el-menu-item index="alert-rules">告警规则</el-menu-item>
          </el-sub-menu>

          <el-sub-menu index="logs">
            <template #title>
              <el-icon class="menu-icon"><Document /></el-icon>
              <span>日志管理</span>
            </template>
            <el-menu-item index="cluster-logs">集群日志</el-menu-item>
            <el-menu-item index="audit-logs">审计日志</el-menu-item>
          </el-sub-menu>

          <el-sub-menu index="scheduling">
            <template #title>
              <el-icon class="menu-icon"><SetUp /></el-icon>
              <span>智能调度</span>
            </template>
            <el-menu-item index="autoscaling">自动扩缩容</el-menu-item>
            <el-menu-item index="scheduling-strategy">调度策略</el-menu-item>
          </el-sub-menu>
        </el-menu>
      </el-aside>

      <!-- 右侧整体（顶部 + 主内容） -->
      <el-container>
        <!-- 顶部栏 -->
        <el-header class="header">
          <div class="header-left">
            <div class="header-title">概述</div>
            <div class="header-subtitle">企业级 Kubernetes 集群总览</div>
          </div>

          <div class="header-right">
            <!-- 顶部工具入口，可以放全局搜索 / 通知等 -->
            <el-button-group class="header-actions">
              <el-button text size="small">
                <el-icon><Search /></el-icon>
              </el-button>
              <el-button text size="small">
                <el-icon><Bell /></el-icon>
              </el-button>
            </el-button-group>

            <!-- 用户信息下拉 -->
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

        <!-- 主体区域：中间概览 + 右侧信息面板 -->
        <el-main class="main">
          <div class="main-layout">
            <!-- 中间主内容 -->
            <section class="overview-section">
              <!-- 概览卡片区域 -->
              <el-card shadow="never" class="section-card overview-card">
                <div class="section-header">
                  <div class="section-title">集群概览</div>
                  <div class="section-subtitle">当前集群运行状态一览</div>
                </div>

                <div class="overview-grid">
                  <div
                    v-for="item in overviewStats"
                    :key="item.key"
                    class="stat-card"
                  >
                    <div class="stat-icon-wrapper">
                      <el-icon class="stat-icon">
                        <component :is="item.icon" />
                      </el-icon>
                    </div>
                    <div class="stat-content">
                      <div class="stat-value">{{ item.value }}</div>
                      <div class="stat-label">{{ item.label }}</div>
                      <div class="stat-desc">{{ item.desc }}</div>
                    </div>
                  </div>
                </div>
              </el-card>

              <!-- 工具入口区域 -->
              <el-card shadow="never" class="section-card tools-card">
                <div class="section-header">
                  <div class="section-title">工具</div>
                  <div class="section-subtitle">运维高频操作入口</div>
                </div>

                <div class="tools-grid">
                  <el-card
                    v-for="tool in toolEntries"
                    :key="tool.key"
                    shadow="hover"
                    class="tool-card"
                    body-class="tool-card-body"
                  >
                    <div class="tool-main">
                      <el-icon class="tool-icon">
                        <component :is="tool.icon" />
                      </el-icon>
                      <div class="tool-content">
                        <div class="tool-title">{{ tool.title }}</div>
                        <div class="tool-desc">{{ tool.desc }}</div>
                      </div>
                    </div>
                    <el-button type="primary" text size="small">
                      进入
                    </el-button>
                  </el-card>
                </div>
              </el-card>
            </section>

            <!-- 右侧信息面板 -->
            <aside class="right-panel">
              <el-card shadow="never" class="cluster-card">
                <div class="cluster-header">
                  <div class="cluster-name">
                    <span class="cluster-badge">主集群</span>
                    <span class="cluster-title">host</span>
                  </div>
                  <div class="cluster-status">
                    <span class="status-dot online"></span> 运行中
                  </div>
                </div>

                <div class="cluster-desc">
                  该集群由平台自动创建并接入，当前为企业级生产环境。
                </div>

                <div class="cluster-section-title">基本信息</div>
                <el-descriptions
                  :column="1"
                  size="small"
                  class="cluster-desc-table"
                  border
                >
                  <el-descriptions-item label="集群类型">
                    KubeSphere 管理集群
                  </el-descriptions-item>
                  <el-descriptions-item label="Kubernetes 版本">
                    v1.29.3
                  </el-descriptions-item>
                  <el-descriptions-item label="平台版本">
                    v1.0.0-rc.1
                  </el-descriptions-item>
                  <el-descriptions-item label="所在机房">
                    广州 · A 区 · 生产环境
                  </el-descriptions-item>
                </el-descriptions>

                <div class="cluster-section-title mt-16">资源概况</div>
                <div class="cluster-metrics">
                  <div class="metric-item">
                    <div class="metric-label">节点</div>
                    <div class="metric-value">7</div>
                  </div>
                  <div class="metric-item">
                    <div class="metric-label">命名空间</div>
                    <div class="metric-value">20</div>
                  </div>
                  <div class="metric-item">
                    <div class="metric-label">Pod</div>
                    <div class="metric-value">126</div>
                  </div>
                  <div class="metric-item">
                    <div class="metric-label">告警规则</div>
                    <div class="metric-value">32</div>
                  </div>
                </div>
              </el-card>

              <el-card shadow="never" class="cluster-card mt-16">
                <div class="cluster-section-title mb-8">
                  集群健康摘要
                </div>
                <ul class="health-list">
                  <li class="health-item">
                    <span class="indicator ok"></span>
                    控制面组件运行正常
                  </li>
                  <li class="health-item">
                    <span class="indicator ok"></span>
                    节点心跳全部在线
                  </li>
                  <li class="health-item">
                    <span class="indicator warn"></span>
                    最近 24h 出现 3 条告警
                  </li>
                  <li class="health-item">
                    <span class="indicator ok"></span>
                    集群容量使用率 63%
                  </li>
                </ul>
              </el-card>
            </aside>
          </div>
        </el-main>
      </el-container>
    </el-container>
  </div>
</template>

<script setup lang="ts">
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
  Histogram,
  Collection,
  Tickets,
  Connection,
  Monitor,
  User,
} from '@element-plus/icons-vue'

const activeMenu = 'overview'
const userName = 'admin'

// 概览统计数据
const overviewStats = [
  {
    key: 'projects',
    label: '项目',
    value: 7,
    desc: '已创建的业务项目',
    icon: Collection,
  },
  {
    key: 'namespaces',
    label: '命名空间',
    value: 20,
    desc: '隔离的租户空间',
    icon: Tickets,
  },
  {
    key: 'nodes',
    label: '节点',
    value: 7,
    desc: '在线工作节点',
    icon: Cpu,
  },
  {
    key: 'workloads',
    label: '工作负载',
    value: 68,
    desc: 'Deployment / StatefulSet',
    icon: Box,
  },
  {
    key: 'pods',
    label: 'Pod 数量',
    value: 126,
    desc: '当前运行中的 Pod',
    icon: Histogram,
  },
  {
    key: 'services',
    label: '服务',
    value: 22,
    desc: 'ClusterIP / NodePort 等',
    icon: Connection,
  },
  {
    key: 'users',
    label: '用户',
    value: 18,
    desc: '有权限访问该集群的用户',
    icon: User,
  },
  {
    key: 'roles',
    label: '角色',
    value: 9,
    desc: 'RBAC 角色定义',
    icon: SetUp,
  },
]

// 工具入口
const toolEntries = [
  {
    key: 'kubectl',
    title: 'kubectl 终端',
    desc: '通过命令行快速执行集群操作',
    icon: Monitor,
  },
  {
    key: 'kubeconfig',
    title: 'kubeconfig 下载',
    desc: '获取当前集群的访问凭证文件',
    icon: Document,
  },
  {
    key: 'diagnostic',
    title: '集群诊断',
    desc: '一键体检，排查潜在风险',
    icon: Bell,
  },
]

const handleUserCommand = (command: 'switch' | 'logout') => {
  if (command === 'switch') {
    console.log('切换用户逻辑')
  } else if (command === 'logout') {
    console.log('退出用户逻辑')
  }
}
</script>

<style scoped>
.k8s-dashboard {
  --brand-color: #3b82f6;
  --bg-light: #f3f4f6;
  --card-bg: #ffffff;

  min-height: 100vh;
  background: #eef1f7;
  color: #111827;
  font-size: 14px;
}

.dashboard-container {
  height: 100vh;
}

/* ========== 侧边栏 ========== */
.sidebar {
  background: #0f172a;
  color: #e5e7eb;
  border-right: 1px solid rgba(15, 23, 42, 0.9);
  display: flex;
  flex-direction: column;
  padding: 12px 0;
}

.sidebar-logo {
  display: flex;
  align-items: center;
  padding: 0 16px 12px;
  margin-bottom: 8px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.3);
}

.logo-mark {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: linear-gradient(135deg, #3b82f6, #22c55e);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 14px;
  color: #f9fafb;
  margin-right: 10px;
}

.logo-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.logo-title {
  font-size: 14px;
  font-weight: 600;
  color: #e5e7eb;
}

.logo-subtitle {
  font-size: 11px;
  color: #9ca3af;
}

.sidebar-menu {
  border-right: none;
  flex: 1;
  padding-top: 4px;
}

.menu-icon {
  margin-right: 6px;
  font-size: 16px;
}

/* ========== 顶部栏 ========== */
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  padding: 0 20px;
  background: #ffffff;
  border-bottom: 1px solid #e5e7eb;
}

.header-left {
  display: flex;
  flex-direction: column;
}

.header-title {
  font-size: 18px;
  font-weight: 600;
  color: #111827;
}

.header-subtitle {
  font-size: 12px;
  color: #6b7280;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-actions {
  margin-right: 8px;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  background: #f3f4f6;
  cursor: pointer;
  transition: background 0.15s ease;
}

.user-info:hover {
  background: #e5e7eb;
}

.user-avatar {
  border: 1px solid #d1d5db;
}

.user-name {
  font-size: 13px;
  color: #111827;
}

.dropdown-icon {
  font-size: 14px;
  color: #9ca3af;
}

/* ========== 主体区域 ========== */
.main {
  padding: 16px 20px 20px;
  background: #f3f4f6;
}

.main-layout {
  display: grid;
  grid-template-columns: minmax(0, 3fr) minmax(260px, 1fr);
  gap: 16px;
}

/* 中间概览 */
.section-card {
  background: var(--card-bg);
  border-radius: 10px;
  border: 1px solid #e5e7eb;
  margin-bottom: 16px;
}

.section-header {
  display: flex;
  flex-direction: column;
  margin-bottom: 10px;
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #111827;
}

.section-subtitle {
  font-size: 12px;
  color: #9ca3af;
}

/* 概览卡片网格 */
.overview-card {
  margin-bottom: 16px;
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
  margin-top: 8px;
}

.stat-card {
  display: flex;
  padding: 10px 12px;
  background: #f9fafb;
  border-radius: 10px;
  border: 1px solid #e5e7eb;
  transition: box-shadow 0.15s ease, transform 0.1s ease, border-color 0.15s ease;
  cursor: default;
}

.stat-card:hover {
  box-shadow: 0 6px 18px rgba(15, 23, 42, 0.06);
  transform: translateY(-1px);
  border-color: rgba(59, 130, 246, 0.3);
}

.stat-icon-wrapper {
  width: 32px;
  height: 32px;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.08);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 10px;
}

.stat-icon {
  font-size: 18px;
  color: var(--brand-color);
}

.stat-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stat-value {
  font-size: 18px;
  font-weight: 600;
  color: #111827;
}

.stat-label {
  font-size: 12px;
  color: #6b7280;
}

.stat-desc {
  font-size: 11px;
  color: #9ca3af;
}

/* 工具入口 */
.tools-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 10px;
  margin-top: 8px;
}

.tool-card {
  border-radius: 10px;
  border-color: #e5e7eb;
}

.tool-card-body {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-height: 88px;
  padding: 10px 12px;
}

.tool-main {
  display: flex;
  align-items: center;
  gap: 10px;
}

.tool-icon {
  font-size: 22px;
  color: var(--brand-color);
}

.tool-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.tool-title {
  font-size: 14px;
  font-weight: 600;
  color: #111827;
}

.tool-desc {
  font-size: 12px;
  color: #6b7280;
}

/* 右侧信息面板 */
.right-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.cluster-card {
  background: var(--card-bg);
  border-radius: 10px;
  border: 1px solid #e5e7eb;
}

.cluster-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.cluster-name {
  display: flex;
  align-items: center;
  gap: 6px;
}

.cluster-badge {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.08);
  color: #1d4ed8;
}

.cluster-title {
  font-size: 15px;
  font-weight: 600;
  color: #111827;
}

.cluster-status {
  font-size: 12px;
  color: #059669;
}

.status-dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 999px;
  margin-right: 4px;
}

.status-dot.online {
  background: #22c55e;
}

.cluster-desc {
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 10px;
}

.cluster-section-title {
  font-size: 13px;
  font-weight: 600;
  color: #111827;
  margin: 10px 0 6px;
}

.cluster-desc-table :deep(.el-descriptions__body) {
  background-color: #f9fafb;
}

/* 资源概况 */
.cluster-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-top: 6px;
}

.metric-item {
  padding: 8px 10px;
  border-radius: 8px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
}

.metric-label {
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 2px;
}

.metric-value {
  font-size: 16px;
  font-weight: 600;
  color: #111827;
}

/* 健康状态 */
.health-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.health-item {
  display: flex;
  align-items: center;
  font-size: 12px;
  color: #4b5563;
  margin-bottom: 6px;
}

.indicator {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  margin-right: 6px;
}

.indicator.ok {
  background: #22c55e;
}

.indicator.warn {
  background: #f97316;
}

/* 辅助类 */
.mt-16 {
  margin-top: 16px;
}

.mb-8 {
  margin-bottom: 8px;
}

/* 简单响应式 */
@media (max-width: 1024px) {
  .main-layout {
    grid-template-columns: minmax(0, 1fr);
  }

  .right-panel {
    order: -1;
  }
}
</style>
