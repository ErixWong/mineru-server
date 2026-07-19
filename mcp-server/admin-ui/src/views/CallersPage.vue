<template>
  <AdminLayout>
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h3 class="mb-0">调用方管理</h3>
      <button class="btn btn-primary" @click="showCreate = !showCreate">{{ showCreate ? '取消' : '新建调用方' }}</button>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>
    <div v-if="flash" class="alert alert-success">{{ flash }}</div>

    <div v-if="showCreate" class="card page-card mb-3">
      <div class="card-body">
        <h5 class="card-title">新建调用方</h5>
        <form class="row g-3" @submit.prevent="createCaller">
          <div class="col-md-6">
            <label class="form-label">名称</label>
            <input v-model="createForm.name" class="form-control" required />
          </div>
          <div class="col-md-6">
            <label class="form-label">有效期（可选）</label>
            <input v-model="createForm.expires_at" class="form-control" type="datetime-local" />
          </div>
          <div class="col-md-6">
            <label class="form-label">默认后处理</label>
            <select v-model="createForm.default_postprocess_rule_id" class="form-select">
              <option value="">不启用</option>
              <option v-for="rule in rules" :key="rule.rule_id" :value="rule.rule_id">{{ rule.title }}</option>
            </select>
          </div>
          <div class="col-12">
            <button class="btn btn-primary" :disabled="creating">{{ creating ? '创建中...' : '创建' }}</button>
          </div>
        </form>
      </div>
    </div>

    <div class="card page-card">
      <div class="card-body">
        <div class="table-wrap">
          <table class="table table-hover align-middle mb-0">
            <thead>
              <tr>
                <th>名称</th>
                <th>API Key</th>
                <th>默认后处理</th>
                <th>有效期</th>
                <th>状态</th>
                <th>最近使用</th>
                <th>近7天统计</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading"><td colspan="8" class="text-center text-muted py-4">加载中...</td></tr>
              <tr v-else-if="callers.length === 0"><td colspan="8" class="text-center text-muted py-4">暂无调用方</td></tr>
              <tr v-for="caller in callers" :key="caller.caller_id">
                <td>{{ caller.name }}</td>
                <td>
                  <div class="d-flex align-items-center gap-2">
                    <span class="monospace small">{{ maskApiKey(caller) }}</span>
                    <button class="btn btn-outline-secondary btn-sm" @click="copyApiKey(caller)">复制</button>
                  </div>
                </td>
                <td style="min-width: 220px;">
                  <select class="form-select form-select-sm" :value="caller.default_postprocess_rule_id || ''" @change="updateCallerDefaultRule(caller, $event)">
                    <option value="">不启用</option>
                    <option v-for="rule in rules" :key="rule.rule_id" :value="rule.rule_id">{{ rule.title }}</option>
                  </select>
                </td>
                <td>{{ formatDate(caller.expires_at) || '永久' }}</td>
                <td>
                  <span class="badge" :class="caller.disabled ? 'text-bg-secondary' : 'text-bg-success'">
                    {{ caller.disabled ? '已禁用' : '启用' }}
                  </span>
                </td>
                <td>{{ formatDate(caller.last_used_at) || '从未' }}</td>
                <td>总计: {{ caller.stats_last_7_days?.total ?? 0 }} / 失败: {{ caller.stats_last_7_days?.failed ?? 0 }}</td>
                <td>
                  <div class="btn-group btn-group-sm">
                    <button class="btn btn-outline-primary" @click="toggleCaller(caller)">{{ caller.disabled ? '启用' : '禁用' }}</button>
                    <button class="btn btn-outline-warning" @click="resetKey(caller)">重置</button>
                    <button class="btn btn-outline-danger" @click="deleteCaller(caller)">删除</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </AdminLayout>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import AdminLayout from '../layouts/AdminLayout.vue'
import { apiFetch, ApiError } from '../lib/api'
import type { CallerItem, PostprocessRuleItem, PostprocessRuleListResponse } from '../types'

const callers = ref<CallerItem[]>([])
const rules = ref<PostprocessRuleItem[]>([])
const loading = ref(false)
const creating = ref(false)
const showCreate = ref(false)
const error = ref('')
const flash = ref('')
const createForm = reactive({ name: '', expires_at: '', default_postprocess_rule_id: '' })

function formatDate(value?: string | null) {
  return value ? new Date(value).toLocaleString() : ''
}

function maskApiKey(caller: CallerItem) {
  const raw = caller.api_key || ''
  if (raw) {
    if (raw.length <= 12) return raw
    return `${raw.slice(0, 6)}...${raw.slice(-6)}`
  }
  return `${caller.api_key_prefix || ''}...${caller.api_key_suffix || ''}`
}

async function copyApiKey(caller: CallerItem) {
  const raw = caller.api_key || ''
  if (!raw) {
    error.value = '当前列表未提供可复制的完整 API Key'
    return
  }
  await navigator.clipboard.writeText(raw)
  flash.value = `已复制 ${caller.name} 的 API Key`
}

async function loadCallers() {
  loading.value = true
  error.value = ''
  try {
    callers.value = await apiFetch<CallerItem[]>('/api/admin/callers?include_disabled=true')
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '加载失败'
  } finally {
    loading.value = false
  }
}

async function loadRules() {
  const payload = await apiFetch<PostprocessRuleListResponse>('/api/admin/postprocess-rules?include_disabled=false')
  rules.value = payload.items
}

async function createCaller() {
  creating.value = true
  error.value = ''
  flash.value = ''
  try {
    const payload = await apiFetch<{ api_key: string }>('/api/admin/callers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: createForm.name,
        expires_at: createForm.expires_at ? new Date(createForm.expires_at).toISOString() : null,
        default_postprocess_rule_id: createForm.default_postprocess_rule_id || null,
      }),
    })
    flash.value = `调用方创建成功，API Key：${payload.api_key}`
    createForm.name = ''
    createForm.expires_at = ''
    createForm.default_postprocess_rule_id = ''
    showCreate.value = false
    await loadCallers()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '创建失败'
  } finally {
    creating.value = false
  }
}

async function updateCallerDefaultRule(caller: CallerItem, event: Event) {
  const value = (event.target as HTMLSelectElement).value
  error.value = ''
  flash.value = ''
  try {
    await apiFetch('/api/admin/callers/' + caller.caller_id, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ default_postprocess_rule_id: value }),
    })
    flash.value = '默认后处理已更新'
    await loadCallers()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '更新失败'
  }
}

async function toggleCaller(caller: CallerItem) {
  error.value = ''
  flash.value = ''
  try {
    await apiFetch('/api/admin/callers/' + caller.caller_id, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ disabled: !caller.disabled }),
    })
    flash.value = `调用方已${caller.disabled ? '启用' : '禁用'}`
    await loadCallers()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '操作失败'
  }
}

async function resetKey(caller: CallerItem) {
  if (!window.confirm(`确定重置 ${caller.name} 的 API Key 吗？`)) return
  error.value = ''
  flash.value = ''
  try {
    const payload = await apiFetch<{ api_key: string }>('/api/admin/callers/' + caller.caller_id + '/reset-key', {
      method: 'POST',
    })
    flash.value = `API Key 已重置：${payload.api_key}`
    await loadCallers()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '重置失败'
  }
}

async function deleteCaller(caller: CallerItem) {
  if (!window.confirm(`确定删除 ${caller.name} 吗？`)) return
  error.value = ''
  flash.value = ''
  try {
    await apiFetch('/api/admin/callers/' + caller.caller_id, { method: 'DELETE' })
    flash.value = '调用方已删除'
    await loadCallers()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '删除失败'
  }
}

onMounted(() => {
  // Load rules independently (non-blocking): if the postprocess endpoint is
  // unavailable (e.g. version skew), the caller list must still render.
  loadRules().catch(() => { rules.value = [] })
  loadCallers()
})
</script>
