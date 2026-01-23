<!-- src/components/AiAssistantFloat.vue -->
<template>
  <!-- 悬浮按钮 -->
  <div
    class="float-ball"
    :style="{ left: pos.x + 'px', top: pos.y + 'px' }"
    @pointerdown="onDown"
    @click="onClick"
  >
    <el-tooltip content="智能助手" placement="left">
      <el-icon class="ball-icon"><ChatDotRound /></el-icon>
    </el-tooltip>
  </div>

  <!-- Drawer：助手面板 -->
  <el-drawer v-model="store.open" title="智能助手" size="420px" :with-header="true" direction="rtl">
    <div class="drawer-body">
      <!-- 快捷区 -->
      <div class="quick">
        <el-button size="small" @click="goSuggestions">
          <el-icon class="mr6"><MagicStick /></el-icon>
          去智能建议
        </el-button>

        <!-- ✅ 用 canExplain；并且我们会把 sugStore.resp 自动同步到 store.lastSuggestions -->
        <el-button size="small" @click="explainLast" :disabled="!canExplain">
          <el-icon class="mr6"><Document /></el-icon>
          解释最近建议
        </el-button>

        <el-button size="small" type="danger" plain @click="store.clearChat">
          清空
        </el-button>
      </div>

      <!-- 最近建议摘要 -->
      <el-card v-if="store.lastSuggestions" shadow="never" class="last-sug">
        <div class="row">
          <div class="label">最近建议</div>
          <el-tag :type="riskTagType(store.lastSuggestions.risk_level)">
            {{ store.lastSuggestions.risk_level }}
          </el-tag>
        </div>
        <div class="small">对象：{{ store.lastSuggestions.node }}</div>
        <ul class="reasons">
          <li v-for="(r, i) in (store.lastSuggestions.reasons || []).slice(0, 3)" :key="i">
            {{ r }}
          </li>
        </ul>
      </el-card>

      <!-- 聊天消息区 -->
      <div class="chat">
        <div v-for="m in store.messages" :key="m.id" class="msg" :class="m.role">
          <div class="bubble">
            <div class="content" v-text="m.content"></div>
            <div class="meta">{{ formatTime(m.ts) }}</div>
          </div>
        </div>

        <div v-if="store.messages.length === 0" class="empty">
          你可以在智能建议页生成建议后，让我解释“为什么这么建议”和“下一步怎么做”。
        </div>
      </div>

      <!-- 输入区 -->
      <div class="input">
        <el-input
          v-model="text"
          type="textarea"
          :rows="2"
          placeholder="输入问题，比如：为什么提示要扩容？我应该怎么验证？"
          @keydown.enter.exact.prevent="send()"
        />
        <div class="actions">
          <el-button type="primary" :loading="sending" @click="send">
            <el-icon class="mr6"><Promotion /></el-icon>
            发送
          </el-button>
        </div>
      </div>

      <el-alert
        v-if="llmError"
        class="mt12"
        type="warning"
        show-icon
        :closable="false"
        title="助手后端未接通或返回错误"
        :description="llmError"
      />
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive, ref, computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ChatDotRound, MagicStick, Promotion, Document } from '@element-plus/icons-vue'
import { useAssistantStore } from '@/stores/assistant'
import { assistantChat } from '@/api/ai_unified'
import { useAiSuggestionsStore } from '@/stores/aiSuggestions'
import { storeToRefs } from 'pinia'

type Target = 'node_cpu' | 'node_mem' | 'pod_cpu'

const store = useAssistantStore()
const router = useRouter()
const route = useRoute()

// ✅ 从智能建议 store 拿最新 resp/form，保证 node/ns/pod 不缺
const sugStore = useAiSuggestionsStore()
const { resp, form } = storeToRefs(sugStore)

const sending = ref(false)
const text = ref('')
const llmError = ref('')

// 悬浮球可拖拽位置
const pos = reactive({ x: 24, y: 180 })
let dragging = false
let downAt = { x: 0, y: 0 }
let posAt = { x: 0, y: 0 }

function clamp() {
  const vw = window.innerWidth
  const vh = window.innerHeight
  pos.x = Math.max(8, Math.min(vw - 60, pos.x))
  pos.y = Math.max(8, Math.min(vh - 60, pos.y))
}

function onDown(e: PointerEvent) {
  dragging = false
  downAt = { x: e.clientX, y: e.clientY }
  posAt = { x: pos.x, y: pos.y }
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
}

function onMove(e: PointerEvent) {
  if (downAt.x === 0 && downAt.y === 0) return
  const dx = e.clientX - downAt.x
  const dy = e.clientY - downAt.y
  if (Math.abs(dx) + Math.abs(dy) > 6) dragging = true
  pos.x = posAt.x + dx
  pos.y = posAt.y + dy
  clamp()
}

function onUp() {
  downAt = { x: 0, y: 0 }
  posAt = { x: pos.x, y: pos.y }
  setTimeout(() => (dragging = false), 0)
}

function onClick() {
  if (dragging) return
  store.toggle(true)
}

function formatTime(ts: number) {
  return new Date(ts).toLocaleTimeString()
}

/** ✅ 你模板在用 riskTagType，所以必须保留 */
function riskTagType(level: string) {
  if (level === 'HIGH') return 'danger'
  if (level === 'MEDIUM') return 'warning'
  if (level === 'LOW') return 'success'
  return 'info'
}

function goSuggestions() {
  router.push('/ai/suggestions')
  store.toggle(true)
}

/** 从 resp.key 拆出 node / namespace / pod */
function parseFromRespKey(target: Target, key: string): Record<string, unknown> {
  if (target === 'pod_cpu') {
    const [namespace = '', pod = ''] = key.split('/')
    return { namespace, pod }
  }
  return { node: key }
}

/** ✅ 关键：按 target 裁剪字段，node_* 不要带 namespace/pod，避免 LLM 跑偏 */
function pruneByTarget(obj: Record<string, unknown>) {
  const t = obj.target as Target

  if (t === 'node_cpu' || t === 'node_mem') {
    delete obj.namespace
    delete obj.pod

    if (obj.form && typeof obj.form === 'object' && obj.form !== null) {
      const f = obj.form as any
      delete f.namespace
      delete f.pod
    }
  }

  // pod_cpu 场景：node 可留可删（你后端目前只看 namespace/pod，不影响）
  // if (t === 'pod_cpu') delete obj.node

  return obj
}

/** ✅ 返回 object，并确保必填字段齐全（避免后端 required 报错） */
function buildContextObj(): Record<string, unknown> {
  const base: Record<string, unknown> = {
    page: route.path,
    // 给后端做参数校验的兜底来源：当前表单
    form: { ...form.value }
  }

  // 优先用 resp（最近建议真实对象）
  const r = resp.value
  if (r) {
    const extra = parseFromRespKey(r.target as Target, r.key)

    const ctx = {
      ...base,
      target: r.target,
      key: r.key,
      ...extra,

      // 同时给 node/ns/pod 兜底（注意：后面会 prune）
      node: (r.target !== 'pod_cpu' ? r.key : form.value.node) || '',
      namespace: (r.target === 'pod_cpu' ? (extra.namespace as string) : form.value.namespace) || '',
      pod: (r.target === 'pod_cpu' ? (extra.pod as string) : form.value.pod) || '',

      // ✅ 给 assistant.py 用的默认参数（否则会用后端默认 240/120/60/85/15）
      history_minutes: Number((form.value as any).history_minutes ?? (form.value as any).minutes ?? 240),
      horizon_minutes: Number((form.value as any).horizon_minutes ?? (form.value as any).horizon ?? 120),
      step: Number(form.value.step ?? 60),
      threshold: Number(form.value.threshold ?? 85),
      sustain_minutes: Number(form.value.sustain_minutes ?? 15)
    } as Record<string, unknown>

    return pruneByTarget(ctx)
  }

  // 没有 resp：用表单兜底
  const t = form.value.target as Target
  const fallbackKey =
    t === 'pod_cpu' ? `${form.value.namespace || ''}/${form.value.pod || ''}` : (form.value.node || '')
  const extra = parseFromRespKey(t, fallbackKey)

  const ctx = {
    ...base,
    target: t,
    key: fallbackKey,
    ...extra,
    node: form.value.node || '',
    namespace: form.value.namespace || '',
    pod: form.value.pod || '',
    history_minutes: Number((form.value as any).history_minutes ?? (form.value as any).minutes ?? 240),
    horizon_minutes: Number((form.value as any).horizon_minutes ?? (form.value as any).horizon ?? 120),
    step: Number(form.value.step ?? 60),
    threshold: Number(form.value.threshold ?? 85),
    sustain_minutes: Number(form.value.sustain_minutes ?? 15)
  } as Record<string, unknown>

  return pruneByTarget(ctx)
}

/**
 * ✅ 关键修复：把 aiSuggestionsStore.resp 自动同步到 assistantStore.lastSuggestions
 * 这样刷新页面/切历史/重新生成建议后，“解释最近建议”都会可点
 */
watch(
  resp,
  (r) => {
    try {
      store.setLastSuggestions((r as any) ?? null)
    } catch {
      // ignore
    }
  },
  { immediate: true }
)

const canExplain = computed(() => !!store.lastSuggestions)

async function explainLast() {
  if (!canExplain.value) return
  const prompt =
    `请用简洁中文解释这条智能建议：为什么这么判断？证据是什么？下一步我该如何验证？并给出3条可执行步骤。\n` +
    `上下文(JSON)：\n${JSON.stringify(buildContextObj(), null, 2)}\n`
  text.value = prompt
  await send()
}

async function send() {
  const content = text.value.trim()
  if (!content) return

  llmError.value = ''
  store.push('user', content)
  text.value = ''
  sending.value = true

  try {
    const { data } = await assistantChat({
      message: content,
      page: route.path,
      context: buildContextObj()
      // use_llm: true/false 由后端默认处理；你也可以这里显式传
    })
    store.push('assistant', (data as any)?.reply || '（助手未返回内容）')
  } catch (e: unknown) {
    const msg = toErrorMessage(e, '请求失败')
    llmError.value = msg
    store.push(
      'assistant',
      '助手接口返回错误。请确认 /api/ai/assistant/chat 可用，并且 context 已包含 node 或 namespace/pod。'
    )
  } finally {
    sending.value = false
  }
}

function toErrorMessage(e: unknown, fallback: string): string {
  const anyE = e as any
  const detail = anyE?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (e instanceof Error) return e.message
  return fallback
}

const BALL = 52
const MARGIN = 16
function initBottomRight() {
  pos.x = window.innerWidth - BALL - MARGIN
  pos.y = window.innerHeight - BALL - MARGIN
}

onMounted(() => {
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
  window.addEventListener('resize', clamp)
  initBottomRight()
  clamp()
})

onBeforeUnmount(() => {
  window.removeEventListener('pointermove', onMove)
  window.removeEventListener('pointerup', onUp)
  window.removeEventListener('resize', clamp)
})
</script>

<style scoped>
.float-ball {
  position: fixed;
  width: 52px;
  height: 52px;
  border-radius: 999px;
  background: rgba(64, 158, 255, 0.95);
  box-shadow: 0 10px 26px rgba(0, 0, 0, 0.18);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  user-select: none;
  cursor: pointer;
}

.ball-icon {
  color: #fff;
  font-size: 22px;
}

.drawer-body {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 120px);
  gap: 12px;
}

.quick {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.last-sug {
  border-radius: 10px;
}
.last-sug .row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.last-sug .label {
  font-weight: 700;
}
.last-sug .small {
  color: #8a8f98;
  font-size: 12px;
}
.reasons {
  margin: 6px 0 0;
  padding-left: 18px;
  color: #606266;
  font-size: 12px;
}

.chat {
  flex: 1;
  overflow: auto;
  padding-right: 4px;
  border: 1px solid #f0f2f5;
  border-radius: 10px;
  padding: 10px;
}

.empty {
  color: #8a8f98;
  font-size: 13px;
  line-height: 1.6;
}

.msg {
  display: flex;
  margin-bottom: 10px;
}
.msg.user {
  justify-content: flex-end;
}
.msg.assistant {
  justify-content: flex-start;
}

.bubble {
  max-width: 86%;
  border-radius: 12px;
  padding: 10px 12px;
  background: #f5f7fa;
}
.msg.user .bubble {
  background: rgba(64, 158, 255, 0.14);
}

.content {
  white-space: pre-wrap;
  font-size: 13px;
  line-height: 1.55;
}
.meta {
  margin-top: 6px;
  color: #a3a6ad;
  font-size: 11px;
  text-align: right;
}

.input {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.actions {
  display: flex;
  justify-content: flex-end;
}

.mr6 {
  margin-right: 6px;
}
.mt12 {
  margin-top: 12px;
}
</style>
