<template>
  <div class="system-status-page">
    <!-- 页面标题区 -->
    <div class="page-header">
      <h1>系统状态监控</h1>
      <p class="page-desc">实时监控后端服务与服务器资源状态</p>
    </div>

    <!-- 状态卡片容器 -->
    <div class="status-container">
      <!-- 服务健康状态卡片 -->
      <el-card class="status-card health-card">
        <template #header>
          <div class="card-header">
            <span>服务健康状态</span>
            <el-tag size="small" :type="healthStatus === 'healthy' ? 'success' : 'danger'">
              {{ healthStatus === 'healthy' ? '正常' : '异常' }}
            </el-tag>
          </div>
        </template>
        
        <div class="health-info">
          <div class="info-item">
            <span class="label">服务版本</span>
            <span class="value">{{ serviceInfo.version || '未知' }}</span>
          </div>
          <div class="info-item">
            <span class="label">启动时间</span>
            <span class="value">{{ formatTime(serviceInfo.start_time) || '未知' }}</span>
          </div>
          <div class="info-item">
            <span class="label">最后检查</span>
            <span class="value">{{ lastCheckTime || '未检查' }}</span>
          </div>
          <div class="info-item">
            <span class="label">响应延迟</span>
            <span class="value">{{ responseDelay }} ms</span>
          </div>
        </div>
      </el-card>

      <!-- 服务器资源卡片 -->
      <el-card class="status-card resource-card">
        <template #header>
          <div class="card-header">
            <span>服务器资源</span>
            <el-button 
              size="small" 
              type="text" 
              @click="refreshResources"
              :icon="Refresh"
            >
              刷新
            </el-button>
          </div>
        </template>
        
        <div class="resource-info">
          <!-- CPU 使用率 -->
          <div class="resource-item">
            <div class="resource-header">
              <span class="resource-name">CPU 使用率</span>
              <span class="resource-value">{{ systemInfo.cpu_usage }}%</span>
            </div>
            <el-progress 
              :percentage="systemInfo.cpu_usage" 
              :stroke-width="6" 
              :status="getProgressStatus(systemInfo.cpu_usage)"
            />
          </div>

          <!-- 内存使用率 -->
          <div class="resource-item">
            <div class="resource-header">
              <span class="resource-name">内存使用率</span>
              <span class="resource-value">{{ systemInfo.mem_usage }}%</span>
            </div>
            <el-progress 
              :percentage="systemInfo.mem_usage" 
              :stroke-width="6" 
              :status="getProgressStatus(systemInfo.mem_usage)"
            />
          </div>

          <!-- 磁盘使用率 -->
          <div class="resource-item">
            <div class="resource-header">
              <span class="resource-name">磁盘使用率</span>
              <span class="resource-value">{{ systemInfo.disk_usage }}%</span>
            </div>
            <el-progress 
              :percentage="systemInfo.disk_usage" 
              :stroke-width="6" 
              :status="getProgressStatus(systemInfo.disk_usage)"
            />
          </div>

          <!-- 网络状态 -->
          <div class="resource-item network-item">
            <div class="network-info">
              <div>
                <span class="resource-name">网络流入</span>
                <span class="resource-value">{{ formatBytes(systemInfo.net_in) }}</span>
              </div>
              <div>
                <span class="resource-name">网络流出</span>
                <span class="resource-value">{{ formatBytes(systemInfo.net_out) }}</span>
              </div>
            </div>
          </div>
        </div>
      </el-card>

      <!-- 接口状态卡片 -->
      <el-card class="status-card api-card">
        <template #header>
          <div class="card-header">
            <span>核心接口状态</span>
            <span class="api-count">{{ apiStatusList.length }} 个接口</span>
          </div>
        </template>
        
        <el-table 
          :data="apiStatusList" 
          border 
          size="small"
          :header-cell-style="{ background: '#f5f7fa' }"
        >
          <el-table-column prop="name" label="接口名称" width="180" />
          <el-table-column prop="path" label="接口路径" />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="scope">
              <el-tag 
                size="small" 
                :type="scope.row.status === 'normal' ? 'success' : 'danger'"
              >
                {{ scope.row.status === 'normal' ? '正常' : '异常' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="response_time" label="响应时间(ms)" width="120" />
        </el-table>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import { Refresh } from '@element-plus/icons-vue';
import { ElProgress, ElTag, ElButton, ElTable, ElTableColumn, ElCard } from 'element-plus';

// 定义接口类型
interface HealthResponse {
  status: 'healthy' | 'unhealthy';
  timestamp: number;
}

interface ServiceInfo {
  version: string;
  start_time: number;
}

interface SystemResources {
  cpu_usage: number;
  mem_usage: number;
  disk_usage: number;
  net_in: number; // 字节数
  net_out: number; // 字节数
}

interface ApiStatus {
  name: string;
  path: string;
  status: 'normal' | 'error';
  response_time: number; // ms
}

// 👉 先定义工具函数（确保在状态变量之前）
// 格式化时间戳为本地时间
const formatTime = (timestamp: number): string => {
  if (!timestamp) return '';
  return new Date(timestamp * 1000).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });
};

// 格式化字节数为可读单位
const formatBytes = (bytes: number): string => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

// 修正进度条状态类型
const getProgressStatus = (value: number): 'success' | 'warning' | 'exception' => {
  if (value > 80) return 'exception';
  if (value > 60) return 'warning';
  return 'success';
};

// 👉 再声明状态变量（此时 formatTime 已定义）
const healthStatus = ref<'healthy' | 'unhealthy' | 'unknown'>('healthy');
const lastCheckTime = ref(formatTime(Date.now() / 1000)); // 现在可以正常引用 formatTime
const responseDelay = ref(42);
const serviceInfo = ref<ServiceInfo>({ 
  version: 'v1.0.0', 
  start_time: Date.now() / 1000 - 86400 // 模拟24小时前启动
});
const systemInfo = ref<SystemResources>({
  cpu_usage: 45,
  mem_usage: 62,
  disk_usage: 38,
  net_in: 1024 * 1024 * 2.5, // 2.5MB
  net_out: 1024 * 512 // 512KB
});
const apiStatusList = ref<ApiStatus[]>([
  { name: '监控指标', path: '/metrics', status: 'normal', response_time: 45 },
  { name: '日志查询', path: '/logs', status: 'normal', response_time: 89 },
  { name: '告警管理', path: '/alerts', status: 'error', response_time: 156 },
  { name: '系统状态', path: '/system', status: 'normal', response_time: 18 }
]);

// 刷新资源数据（静态模拟）
const refreshResources = (): void => {
  systemInfo.value = {
    ...systemInfo.value,
    cpu_usage: Math.floor(Math.random() * 30) + 30,
    mem_usage: Math.floor(Math.random() * 30) + 50,
    disk_usage: Math.floor(Math.random() * 20) + 30,
  };
  lastCheckTime.value = formatTime(Date.now() / 1000);
};

// 页面加载时初始化
onMounted(() => {
  const refreshInterval = setInterval(() => {
    refreshResources();
  }, 10000);

  onUnmounted(() => {
    clearInterval(refreshInterval);
  });
});
</script>

<style scoped>
.system-status-page {
  padding: 20px;
  background-color: #f5f7fa;
  min-height: 100vh;
}

.page-header {
  margin-bottom: 24px;
}

.page-header h1 {
  font-size: 24px;
  color: #1f2329;
  margin: 0 0 8px 0;
}

.page-desc {
  font-size: 14px;
  color: #6b7280;
  margin: 0;
}

.status-container {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 20px;
}

.status-card {
  transition: all 0.3s ease;
}

.status-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  transform: translateY(-2px);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

/* 健康状态卡片样式 */
.health-card {
  grid-column: span 1;
}

.health-info {
  padding: 10px 0;
}

.info-item {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid #f0f2f5;
}

.info-item:last-child {
  border-bottom: none;
}

.label {
  color: #6b7280;
  font-size: 14px;
}

.value {
  color: #1f2329;
  font-weight: 500;
}

/* 资源卡片样式 */
.resource-card {
  grid-column: span 1;
}

.resource-info {
  padding: 10px 0;
}

.resource-item {
  margin-bottom: 20px;
}

.resource-item:last-child {
  margin-bottom: 0;
}

.resource-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
}

.resource-name {
  color: #6b7280;
  font-size: 14px;
}

.resource-value {
  color: #1f2329;
  font-weight: 500;
}

.network-item {
  margin-top: 12px;
}

.network-info {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
}

/* 接口状态卡片样式 */
.api-card {
  grid-column: span 2;
}

.api-count {
  font-size: 13px;
  color: #6b7280;
}

/* 响应式调整 */
@media (max-width: 1024px) {
  .status-container {
    grid-template-columns: 1fr;
  }
  
  .api-card {
    grid-column: span 1;
  }
}
</style>