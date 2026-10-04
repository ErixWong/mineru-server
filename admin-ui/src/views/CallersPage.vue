<template>
  <AdminLayout>
    <div class="d-flex flex-wrap justify-content-between align-items-end gap-3 mb-4">
      <div>
        <div class="small text-uppercase text-body-secondary fw-semibold mb-1">{{ t('nav.callers') }}</div>
        <h1 class="fs-3 fw-semibold mb-0">{{ t('callers.title') }}</h1>
      </div>
      <button class="btn btn-outline-primary" @click="showCreate = !showCreate">
        <i class="bi" :class="showCreate ? 'bi-x-lg' : 'bi-person-plus'"></i>
        <span class="ms-1">{{ showCreate ? t('common.cancel') : t('callers.create') }}</span>
      </button>
    </div>

    <div v-if="error" class="alert bg-body border border-danger-subtle rounded-3 py-2 text-danger-emphasis">{{ error }}</div>
    <div v-if="flash" class="alert bg-body border border-success-subtle rounded-3 py-2 text-success-emphasis">{{ flash }}</div>

    <div v-if="showCreate" class="card mb-4">
      <div class="card-body">
        <h2 class="fs-5 fw-semibold mb-3">{{ t('callers.create') }}</h2>
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
            <button class="btn btn-outline-primary" :disabled="creating">{{ creating ? t('common.creating') : t('common.create') }}</button>
          </div>
        </form>
      </div>
    </div>

    <div class="card">
      <div class="card-body">
        <div class="table-responsive">
          <table class="table table-hover align-middle mb-0">
            <thead>
              <tr>
                <th class="small text-body-secondary fw-semibold">{{ t('callers.name') }}</th>
                <th class="small text-body-secondary fw-semibold">{{ t('callers.apiKey') }}</th>
                <th class="small text-body-secondary fw-semibold">{{ t('callers.defaultPostprocess') }}</th>
                <th class="small text-body-secondary fw-semibold">{{ t('callers.expiresAt') }}</th>
                <th class="small text-body-secondary fw-semibold">{{ t('callers.status') }}</th>
                <th class="small text-body-secondary fw-semibold">{{ t('callers.lastUsed') }}</th>
                <th class="small text-body-secondary fw-semibold">{{ t('callers.stats7Days') }}</th>
                <th class="small text-body-secondary fw-semibold">{{ t('callers.actions') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading"><td colspan="8" class="text-center text-body-secondary py-5"><i class="bi bi-arrow-repeat me-2"></i>{{ t('common.loading') }}</td></tr>
              <tr v-else-if="callers.length === 0"><td colspan="8" class="text-center text-body-secondary py-5"><i class="bi bi-person-lines-fill fs-4 d-block mb-2"></i>{{ t('callers.noData') }}</td></tr>
              <tr v-for="caller in callers" :key="caller.caller_id">
                <td>{{ caller.name }}</td>
                <td>
                  <div class="d-flex align-items-center gap-2">
                    <span class="font-monospace small">{{ maskApiKey(caller) }}</span>
                    <button class="btn btn-outline-secondary btn-sm" @click="copyApiKey(caller)">{{ t('common.copy') }}</button>
                  </div>
                </td>
                <td>
                  <select class="form-select form-select-sm" :value="caller.default_postprocess_rule_id || ''" @change="updateCallerDefaultRule(caller, $event)">
                    <option value="">{{ t('callers.notEnabled') }}</option>
                    <option v-for="rule in rules" :key="rule.plan_id" :value="rule.plan_id">{{ rule.title }}</option>
                  </select>
                </td>
                <td>{{ formatDate(caller.expires_at) || t('callers.permanent') }}</td>
                <td>
                  <span class="badge" :class="callerStatusClass(caller)">
                    {{ callerStatusLabel(caller) }}
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
  return `${caller.api_key_prefix || ''}...${caller.api_key_suffix || ''}`
}

function isExpired(caller: CallerItem) {
  return caller.expires_at ? new Date(caller.expires_at).getTime() <= Date.now() : false
}

function callerStatusLabel(caller: CallerItem) {
  if (caller.disabled) return t('callers.disabled')
  if (isExpired(caller)) return t('callers.expired')
  return t('callers.enabled')
}

function callerStatusClass(caller: CallerItem) {
  if (caller.disabled) return 'bg-secondary-subtle text-secondary-emphasis'
  if (isExpired(caller)) return 'bg-warning-subtle text-warning-emphasis'
  return 'bg-success-subtle text-success-emphasis'
}

async function copyApiKey(caller: CallerItem) {
  error.value = ''
  flash.value = ''
  try {
    const payload = await apiFetch<{ api_key: string }>('/api/admin/callers/' + caller.caller_id + '/reveal-key', {
      method: 'POST',
    })
    await navigator.clipboard.writeText(payload.api_key)
    flash.value = t('callers.keyCopied', { name: caller.name })
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('callers.noApiKeyAvailable')
  }
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
