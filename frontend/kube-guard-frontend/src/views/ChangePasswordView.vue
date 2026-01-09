<template>
  <div class="cp-page">
    <div class="cp-card">
      <div class="title">首次登录 · 强制修改密码</div>
      <div class="sub">为保障安全，请设置一个新密码后继续使用系统。</div>

      <el-form :model="form" class="form">
        <el-form-item>
          <el-input v-model="form.oldPassword" type="password" show-password size="large" placeholder="旧密码" />
        </el-form-item>

        <el-form-item>
          <el-input v-model="form.newPassword" type="password" show-password size="large" placeholder="新密码（建议至少 8 位）" />
        </el-form-item>

        <el-form-item>
          <el-input v-model="form.confirm" type="password" show-password size="large" placeholder="确认新密码" />
        </el-form-item>

        <el-button class="btn" type="primary" size="large" :loading="loading" @click="submit">
          保存并进入系统
        </el-button>

        <el-button class="btn2" text @click="logout">退出登录</el-button>
      </el-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

const loading = ref(false)
const form = reactive({
  oldPassword: '',
  newPassword: '',
  confirm: '',
})

async function submit() {
  if (!form.oldPassword || !form.newPassword) return ElMessage.warning('请填写完整')
  if (form.newPassword.length < 6) return ElMessage.warning('新密码至少 6 位')
  if (form.newPassword !== form.confirm) return ElMessage.warning('两次输入的新密码不一致')

  loading.value = true
  try {
    await auth.changePassword(form.oldPassword, form.newPassword)
    ElMessage.success('修改成功')
    router.replace('/overview')
  } finally {
    loading.value = false
  }
}

function logout() {
  auth.clear()
  router.replace('/login')
}
</script>

<style scoped>
.cp-page {
  height: 100vh;
  background: #eef3fb;
  display: flex;
  align-items: center;
  justify-content: center;
}

.cp-card {
  width: 420px;
  background: #fff;
  border-radius: 16px;
  padding: 28px 26px 18px;
  box-shadow: 0 20px 40px rgba(15, 23, 42, 0.08);
  border: 1px solid rgba(15, 23, 42, 0.06);
}

.title {
  font-size: 18px;
  font-weight: 800;
  color: #0f172a;
}
.sub {
  margin-top: 8px;
  font-size: 12px;
  color: #64748b;
}

.form {
  margin-top: 18px;
}

.form :deep(.el-input__wrapper) {
  border-radius: 10px;
}

.btn {
  width: 100%;
  border-radius: 10px;
  margin-top: 6px;
}
.btn2 {
  width: 100%;
  margin-top: 8px;
  color: #64748b;
}
</style>
