<template>
  <div class="term-root">
    <div class="header">
      <div>
        <div class="title">kubectl 终端</div>
        <div class="sub">输入 kubectl 子命令（不需要写 kubectl 前缀），示例：get pods -A</div>
      </div>

      <div class="controls">
        <el-input v-model="namespace" placeholder="namespace（可选）" style="width: 200px" />
        <el-select v-model="output" style="width: 140px">
          <el-option label="text" value="text" />
          <el-option label="json" value="json" />
          <el-option label="yaml" value="yaml" />
        </el-select>
        <el-button type="primary" :loading="loading" @click="run">执行</el-button>
      </div>
    </div>

    <el-card shadow="never" class="cmd-card">
      <el-input
        v-model="command"
        type="textarea"
        :rows="3"
        placeholder='例如：get pods -A'
        @keydown.enter.exact.prevent="run"
      />
      <div class="hint">
        允许：get/describe/logs/top/apply/delete/rollout/scale（后端可改白名单）
      </div>
    </el-card>

    <el-card shadow="never" class="out-card">
      <div class="out-header">
        <div class="out-title">输出</div>
        <el-button text @click="clear">清空</el-button>
      </div>

      <pre class="out-pre" v-if="outputText">{{ outputText }}</pre>
      <el-empty v-else description="暂无输出" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { kubectlExec } from '@/api/tools'

const command = ref('get pods -A')
const namespace = ref('')
const output = ref<'text' | 'json' | 'yaml'>('text')
const loading = ref(false)

const stdout = ref('')
const stderr = ref('')
const exitCode = ref<number | null>(null)

const outputText = computed(() => {
  const parts: string[] = []
  if (exitCode.value !== null) parts.push(`exit_code: ${exitCode.value}`)
  if (stdout.value) parts.push(`\n[stdout]\n${stdout.value}`)
  if (stderr.value) parts.push(`\n[stderr]\n${stderr.value}`)
  return parts.join('\n')
})

async function run() {
  if (!command.value.trim()) return ElMessage.warning('请输入命令')
  loading.value = true
  try {
    const resp = await kubectlExec({
      command: command.value.trim(),
      namespace: namespace.value.trim() || undefined,
      output: output.value,
      timeout_seconds: 8,
    })
    stdout.value = resp.stdout || ''
    stderr.value = resp.stderr || ''
    exitCode.value = resp.exit_code
    if (!resp.ok) ElMessage.warning('命令执行失败（请看 stderr）')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '执行失败')
  } finally {
    loading.value = false
  }
}

function clear() {
  stdout.value = ''
  stderr.value = ''
  exitCode.value = null
}
</script>

<style scoped>
.term-root { padding: 16px; display: flex; flex-direction: column; gap: 12px; }
.header { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.title { font-size: 16px; font-weight: 700; color: #111827; }
.sub { margin-top: 2px; font-size: 12px; color: #6b7280; }
.controls { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.cmd-card { border-radius: 10px; border: 1px solid #e5e7eb; }
.hint { margin-top: 6px; font-size: 12px; color: #9ca3af; }
.out-card { border-radius: 10px; border: 1px solid #e5e7eb; }
.out-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.out-title { font-size: 13px; font-weight: 600; color: #111827; }
.out-pre { margin: 0; padding: 10px; background: #0b1020; color: #e5e7eb; border-radius: 8px; overflow: auto; min-height: 320px; }
</style>
