<template>
  <AdminLayout>
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h3 class="mb-0">{{ t('callers.title') }}</h3>
      <button class="btn btn-primary" @click="showCreate = !showCreate">{{ showCreate ? t('common.cancel') : t('callers.create') }}</button>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>
    <div v-if="flash" class="alert alert-success">{{ flash }}</div>

    <div v-if="showCreate" class="card page-card mb-3">
      <div class="card-body">
        <h5 class="card-title">{{ t('callers.create') }}</h5>
        <form class="row g-3" @submit.prevent="createCaller">
          <div class="col-md-6">
            <label class="form-label">{{ t('callers.name') }}</label>
            <input v-model="createForm.name" class="form-control" required />
          </div>
          <div class="col-md-6">
            <label class="form-label">{{ t('callers.expiresAtOptional') }}</label>
            <input v-model="createForm.expires_at" class="form-control" type="datetime-local" />
          </div>
          <div class="col-md-6">
            <label class="form-label">{{ t('callers.defaultPostprocess') }}</label>
              <select v-model="createForm.default_postprocess_rule_id" class="form-select">
              <option value="">{{ t('callers.notEnabled') }}</option>
              <option v-for="rule in rules" :key="rule.plan_id" :value="rule.plan_id">{{ rule.title }}</option>
            </select>
          </div>
          <div class="col-12">
            <button class="btn btn-primary" :disabled="creating">{{ creating ? t('common.creating') : t('common.create') }}</button>
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
                <th>{{ t('callers.name') }}</th>
                <th>{{ t('callers.apiKey') }}</th>
                <th>{{ t('callers.defaultPostprocess') }}</th>
                <th>{{ t('callers.expiresAt') }}</th>
                <th>{{ t('callers.status') }}</th>
                <th>{{ t('callers.lastUsed') }}</th>
                <th>{{ t('callers.stats7Days') }}</th>
                <th>{{ t('callers.actions') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading"><td colspan="8" class="text-center text-muted py-4">{{ t('common.loading') }}</td></tr>
              <tr v-else-if="callers.length === 0"><td colspan="8" class="text-center text-muted py-4">{{ t('callers.noData') }}</td></tr>
              <tr v-for="caller in callers" :key="caller.caller_id">
                <td>{{ caller.name }}</td>
                <td>
                  <div class="d-flex align-items-center gap-2">
                    <span class="monospace small">{{ maskApiKey(caller) }}</span>
                    <button class="btn btn-outline-secondary btn-sm" @click="copyApiKey(caller)">{{ t('common.copy') }}</button>
                  </div>
                </td>
                <td style="min-width: 220px;">
                  <select class="form-select form-select-sm" :value="caller.default_postprocess_rule_id || ''" @change="updateCallerDefaultRule(caller, $event)">
                    <option value="">{{ t('callers.notEnabled') }}</option>
                    <option v-for="rule in rules" :key="rule.plan_id" :value="rule.plan_id">{{ rule.title }}</option>
                  </select>
                </td>
                <td>{{ formatDate(caller.expires_at) || t('callers.permanent') }}</td>
                <td>
                  <span class="badge" :class="caller.disabled ? 'text-bg-secondary' : 'text-bg-success'">
                    {{ caller.disabled ? t('callers.disabled') : t('callers.enabled') }}
                  </span>
                </td>
                <td>{{ formatDate(caller.last_used_at) || t('callers.never') }}</td>
                <td>{{ t('callers.statFormat', { total: caller.stats_last_7_days?.total ?? 0, failed: caller.stats_last_7_days?.failed ?? 0 }) }}</td>
                <td>
                  <div class="btn-group btn-group-sm">
                    <button class="btn btn-outline-primary" @click="toggleCaller(caller)">{{ caller.disabled ? t('common.enable') : t('common.disable') }}</button>
                    <button class="btn btn-outline-warning" @click="resetKey(caller)">{{ t('common.reset') }}</button>
                    <button class="btn btn-outline-danger" @click="deleteCaller(caller)">{{ t('common.delete') }}</button>
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
import { useI18n } from 'vue-i18n'
import AdminLayout from '../layouts/AdminLayout.vue'
import { apiFetch, ApiError } from '../lib/api'
import type { CallerItem, PostprocessPlanItem, PostprocessPlanListResponse } from '../types'

const { t } = useI18n()

const callers = ref<CallerItem[]>([])
const rules = ref<PostprocessPlanItem[]>([])
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
    error.value = t('callers.noApiKeyAvailable')
    return
  }
  await navigator.clipboard.writeText(raw)
  flash.value = t('callers.keyCopied', { name: caller.name })
}

async function loadCallers() {
  loading.value = true
  error.value = ''
  try {
    callers.value = await apiFetch<CallerItem[]>('/api/admin/callers?include_disabled=true')
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('common.loadFailed')
  } finally {
    loading.value = false
  }
}

async function loadRules() {
  const payload = await apiFetch<PostprocessPlanListResponse>('/api/admin/postprocess-plans?include_disabled=false')
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
    flash.value = t('callers.created', { key: payload.api_key })
    createForm.name = ''
    createForm.expires_at = ''
    createForm.default_postprocess_rule_id = ''
    showCreate.value = false
    await loadCallers()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('common.createFailed')
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
    flash.value = t('callers.ruleUpdated')
    await loadCallers()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('common.updateFailed')
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
    flash.value = caller.disabled ? t('callers.toggleEnabled') : t('callers.toggleDisabled')
    await loadCallers()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('common.error')
  }
}

async function resetKey(caller: CallerItem) {
  if (!window.confirm(t('callers.resetKeyConfirm', { name: caller.name }))) return
  error.value = ''
  flash.value = ''
  try {
    const payload = await apiFetch<{ api_key: string }>('/api/admin/callers/' + caller.caller_id + '/reset-key', {
      method: 'POST',
    })
    flash.value = t('callers.keyReset', { key: payload.api_key })
    await loadCallers()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('common.error')
  }
}

async function deleteCaller(caller: CallerItem) {
  if (!window.confirm(t('callers.deleteConfirm', { name: caller.name }))) return
  error.value = ''
  flash.value = ''
  try {
    await apiFetch('/api/admin/callers/' + caller.caller_id, { method: 'DELETE' })
    flash.value = t('callers.deleted')
    await loadCallers()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('common.deleteFailed')
  }
}

onMounted(() => {
  loadRules().catch(() => { rules.value = [] })
  loadCallers()
})
</script>
