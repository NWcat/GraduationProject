<template>
  <div class="login-page">
    <!-- 左侧品牌区 -->
    <div class="login-left">
      <div class="brand">
        <div class="logo">
          <span class="logo-mark">K8</span>
          <div class="logo-text">
            <div class="logo-title">CloudSphere</div>
            <div class="logo-sub">Enterprise Kubernetes Platform</div>
          </div>
        </div>

        <div class="slogan">
          <h2>企业级 Kubernetes 集群管理平台</h2>
          <p>
            统一管理 · 多租户 · 可观测 · 智能运维  
            <br />
            为云原生而生
          </p>
        </div>
      </div>
    </div>

    <!-- 右侧登录区 -->
    <div class="login-right">
      <div class="login-card">
        <div class="card-title">用户登录</div>

        <el-form :model="form" class="login-form">
          <el-form-item>
            <el-input
              v-model="form.username"
              placeholder="请输入用户名"
              size="large"
            />
          </el-form-item>

          <el-form-item>
            <el-input
              v-model="form.password"
              type="password"
              placeholder="请输入密码"
              size="large"
              show-password
            />
          </el-form-item>

          <div class="agreement">
            <el-checkbox v-model="agree">
              我已阅读并同意
              <span class="link">《用户协议》</span>
              与
              <span class="link">《隐私政策》</span>
            </el-checkbox>
          </div>

          <el-button
            type="primary"
            size="large"
            class="login-btn"
            :loading="loading"
            @click="handleLogin"
          >
            登录
          </el-button>
        </el-form>
      </div>

      <div class="login-footer">
        © 2024 CloudSphere · Enterprise K8s
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { loginApi } from '@/api/auth'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const loading = ref(false)
const agree = ref(true)

const form = reactive({
  username: '',
  password: '',
})

async function handleLogin() {
  if (!form.username || !form.password) {
    return ElMessage.warning('请输入用户名和密码')
  }
  if (!agree.value) {
    return ElMessage.warning('请先同意用户协议')
  }

  loading.value = true
  try {
    await auth.login({ username: form.username, password: form.password })

    // ✅ 登录成功后：mustChange 强制去改密，否则去 redirect/overview
    const redirect = (router.currentRoute.value.query.redirect as string) || '/overview'
    if (auth.mustChange) {
      router.replace({ path: '/change-password', query: { redirect } })
    } else {
      router.replace(redirect)
    }
    // ElMessage.success('登录成功')
  } catch (e) {
    // http 拦截器已经 ElMessage.error 了，这里不重复也行
  } finally {
    loading.value = false
  }
  const resp = await loginApi({ username: form.username, password: form.password })
  auth.setLogin(resp.access_token, resp.user)

  ElMessage.success('登录成功')
  const redirect = (route.query.redirect as string) || '/overview'
  router.replace(redirect)
}
</script>

<style scoped>
.login-page {
  height: 100vh;
  display: grid;
  grid-template-columns: 62% 38%;
  background: #eef3fb;
}

/* 左侧 */
.login-left {
  background: linear-gradient(135deg, #3b82f6, #60a5fa);
  color: #fff;
  display: flex;
  align-items: center;
  padding-left: 80px;
}

.brand {
  max-width: 420px;
}

.logo {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 40px;
}

.logo-mark {
  width: 44px;
  height: 44px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
}

.logo-title {
  font-size: 20px;
  font-weight: 700;
}

.logo-sub {
  font-size: 12px;
  opacity: 0.85;
}

.slogan h2 {
  font-size: 26px;
  font-weight: 700;
  margin-bottom: 14px;
}

.slogan p {
  line-height: 1.8;
  opacity: 0.95;
}

/* 右侧 */
.login-right {
  background: #f8fafc;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
}

.login-card {
  width: 360px;
  background: #fff;
  border-radius: 16px;
  padding: 32px;
  box-shadow: 0 20px 40px rgba(15, 23, 42, 0.08);
}

.card-title {
  font-size: 18px;
  font-weight: 700;
  margin-bottom: 24px;
  text-align: center;
}

.login-form :deep(.el-input__wrapper) {
  border-radius: 10px;
}

.login-btn {
  width: 100%;
  margin-top: 12px;
  border-radius: 10px;
}

.agreement {
  font-size: 12px;
  margin-bottom: 12px;
}

.link {
  color: #3b82f6;
  cursor: pointer;
}

.login-footer {
  margin-top: 20px;
  font-size: 12px;
  color: #94a3b8;
}
</style>