<template>
  <AdminLayout>
    <h1 class="fs-3 fw-semibold mb-4">{{ t('nav.settings') }}</h1>
    <div v-if="error" class="alert bg-body border border-danger-subtle rounded-3 py-2 text-danger-emphasis">{{ error }}</div>
    <div v-if="success" class="alert bg-body border border-success-subtle rounded-3 py-2 text-success-emphasis">{{ success }}</div>

    <div class="card mb-4">
      <div class="card-body">
        <div class="d-flex flex-wrap align-items-center justify-content-between gap-2 mb-3">
          <h2 class="fs-5 fw-semibold mb-0">{{ t('settings.changePassword') }}</h2>
          <span
            v-if="settings?.admin_security.default_password_in_use"
            class="badge bg-danger-subtle text-danger-emphasis"
          >
            {{ t('settings.usingDefault') }}
          </span>
        </div>
        <form class="row g-3" @submit.prevent="changePassword">
          <div class="col-md-4"><label class="form-label">{{ t('settings.currentPassword') }}</label><input v-model="form.old_password" class="form-control form-control-sm" type="password" required /></div>
          <div class="col-md-4"><label class="form-label">{{ t('settings.newPassword') }}</label><input v-model="form.new_password" class="form-control form-control-sm" type="password" required /></div>
          <div class="col-md-4"><label class="form-label">{{ t('settings.confirmPassword') }}</label><input v-model="confirmPassword" class="form-control form-control-sm" type="password" required /></div>
          <div class="col-12"><button class="btn btn-outline-primary btn-sm" :disabled="submitting">{{ submitting ? t('settings.changing') : t('settings.changeButton') }}</button></div>
        </form>
      </div>
    </div>

    <section class="mt-4">
      <div class="d-flex flex-column flex-md-row justify-content-between align-items-md-start gap-3 mb-3">
        <div>
          <h2 class="fs-5 fw-semibold mb-1">{{ t('settings.runtimeConfig') }}</h2>
          <p class="text-body-secondary small mb-0">{{ t('settings.runtimeConfigIntro') }}</p>
        </div>
        <span class="badge bg-warning-subtle text-warning-emphasis border border-warning-subtle fw-normal text-wrap text-start">{{ t('settings.sensitiveHint') }}</span>
      </div>

      <form v-if="settings" class="d-flex flex-column gap-3" @submit.prevent="saveRuntimeSettings">
        <section class="rounded-3 border bg-white p-3 p-lg-4">
          <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-baseline gap-2 mb-3 pb-2 border-bottom">
              <h3 class="fs-6 fw-semibold mb-0">{{ t('settings.routingSection') }}</h3>
              <p class="small text-body-secondary mb-0">{{ t('settings.routingSectionHelp') }}</p>
            </div>
            <div class="row g-3">
              <div class="col-md-6 col-xl-4">
                <label class="form-label">{{ t('settings.defaultBackend') }}</label>
                <select v-model="runtimeForm.default_backend" class="form-select form-select-sm">
                  <option v-for="backend in settings.valid_backends" :key="backend" :value="backend">{{ backend }}</option>
                </select>
                <div class="d-flex flex-wrap gap-2 mt-1 small text-body-secondary">
                  <span class="text-break">{{ sourceLabel('default_backend') }}</span>
                </div>
              </div>
            </div>
        </section>

        <section class="rounded-3 border bg-white p-3 p-lg-4">
          <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-baseline gap-2 mb-3 pb-2 border-bottom">
              <h3 class="fs-6 fw-semibold mb-0">{{ t('settings.vlmSection') }}</h3>
              <p class="small text-body-secondary mb-0">{{ t('settings.vlmSectionHelp') }}</p>
            </div>
            <div class="row g-3">
              <div class="col-md-6">
                <label class="form-label">{{ t('settings.vlmBaseUrl') }}</label>
                <input v-model="runtimeForm.vlm_base_url" class="form-control form-control-sm" placeholder="https://api.openai.com/v1" />
                <div class="d-flex flex-wrap gap-2 mt-1 small text-body-secondary">
                  <span class="text-break">{{ sourceLabel('vlm_base_url') }}</span>
                </div>
              </div>
              <div class="col-md-6">
                <label class="form-label">{{ t('settings.vlmModel') }}</label>
                <input v-model="runtimeForm.vlm_model" class="form-control form-control-sm" placeholder="gpt-4o" />
                <div class="d-flex flex-wrap gap-2 mt-1 small text-body-secondary">
                  <span class="text-break">{{ sourceLabel('vlm_model') }}</span>
                </div>
              </div>
              <div class="col-md-6">
                <label class="form-label">{{ t('settings.vlmApiKey') }}</label>
                <input v-model="secretForm.vlm_api_key" class="form-control form-control-sm" type="password" autocomplete="new-password" :placeholder="secretPlaceholder('vlm_api_key')" />
                <div class="d-flex flex-wrap gap-2 mt-1 small text-body-secondary">
                  <span class="text-break">{{ secretStatus('vlm_api_key') }}</span>
                </div>
              </div>
              <div class="col-md-6">
                <label class="form-label">{{ t('settings.vlmMaxConcurrency') }}</label>
                <input v-model.number="runtimeForm.vlm_max_concurrency" class="form-control form-control-sm" type="number" min="1" max="100" />
                <div class="d-flex flex-wrap gap-2 mt-1 small text-body-secondary">
                  <span class="text-break">{{ sourceLabel('vlm_max_concurrency') }}</span>
                  <span class="badge bg-warning-subtle text-warning-emphasis border border-warning-subtle fw-normal">{{ t('settings.restartRequired') }}</span>
                </div>
              </div>
            </div>
        </section>

        <section class="rounded-3 border bg-white p-3 p-lg-4">
          <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-baseline gap-2 mb-3 pb-2 border-bottom">
              <h3 class="fs-6 fw-semibold mb-0">{{ t('settings.titleSection') }}</h3>
              <p class="small text-body-secondary mb-0">{{ t('settings.titleSectionHelp') }}</p>
            </div>
            <div class="row g-3">
              <div class="col-md-6">
                <label class="form-label">{{ t('settings.titleBaseUrl') }}</label>
                <input v-model="runtimeForm.title_base_url" class="form-control form-control-sm" placeholder="https://api.openai.com/v1" />
                <div class="d-flex flex-wrap gap-2 mt-1 small text-body-secondary">
                  <span class="text-break">{{ sourceLabel('title_base_url') }}</span>
                </div>
              </div>
              <div class="col-md-6">
                <label class="form-label">{{ t('settings.titleModel') }}</label>
                <input v-model="runtimeForm.title_model" class="form-control form-control-sm" placeholder="gpt-4o-mini" />
                <div class="d-flex flex-wrap gap-2 mt-1 small text-body-secondary">
                  <span class="text-break">{{ sourceLabel('title_model') }}</span>
                </div>
              </div>
              <div class="col-md-6">
                <label class="form-label">{{ t('settings.titleApiKey') }}</label>
                <input v-model="secretForm.title_api_key" class="form-control form-control-sm" type="password" autocomplete="new-password" :placeholder="secretPlaceholder('title_api_key')" />
                <div class="d-flex flex-wrap gap-2 mt-1 small text-body-secondary">
                  <span class="text-break">{{ secretStatus('title_api_key') }}</span>
                </div>
              </div>
              <div class="col-md-6">
                <label class="form-label">{{ t('settings.postprocessContextSize') }}</label>
                <input v-model.number="runtimeForm.postprocess_context_size" class="form-control form-control-sm" type="number" min="4096" step="1024" />
                <div class="d-flex flex-wrap gap-2 mt-1 small text-body-secondary">
                  <span class="text-break">{{ sourceLabel('postprocess_context_size') }}</span>
                </div>
              </div>
              <div class="col-md-6">
                <label class="form-label">{{ t('settings.postprocessMaxConcurrent') }}</label>
                <input v-model.number="runtimeForm.postprocess_max_concurrent" class="form-control form-control-sm" type="number" min="1" max="32" />
                <div class="d-flex flex-wrap gap-2 mt-1 small text-body-secondary">
                  <span class="text-break">{{ sourceLabel('postprocess_max_concurrent') }}</span>
                  <span class="badge bg-warning-subtle text-warning-emphasis border border-warning-subtle fw-normal">{{ t('settings.restartRequired') }}</span>
                </div>
              </div>
            </div>
        </section>

        <section class="rounded-3 border bg-white p-3 p-lg-4">
          <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-baseline gap-2 mb-3 pb-2 border-bottom">
              <h3 class="fs-6 fw-semibold mb-0">{{ t('settings.schedulerSection') }}</h3>
              <p class="small text-body-secondary mb-0">{{ t('settings.schedulerSectionHelp') }}</p>
            </div>
            <div class="row g-3">
              <div class="col-md-6">
                <label class="form-label">{{ t('settings.maxConcurrent') }}</label>
                <input v-model.number="runtimeForm.max_concurrent" class="form-control form-control-sm" type="number" min="1" max="100" />
                <div class="d-flex flex-wrap gap-2 mt-1 small text-body-secondary">
                  <span class="text-break">{{ sourceLabel('max_concurrent') }}</span>
                  <span class="badge bg-warning-subtle text-warning-emphasis border border-warning-subtle fw-normal">{{ t('settings.restartRequired') }}</span>
                </div>
              </div>
              <div class="col-md-6">
                <label class="form-label">{{ t('settings.taskTimeout') }}</label>
                <input v-model.number="runtimeForm.task_timeout" class="form-control form-control-sm" type="number" min="1" />
                <div class="d-flex flex-wrap gap-2 mt-1 small text-body-secondary">
                  <span class="text-break">{{ sourceLabel('task_timeout') }}</span>
                </div>
              </div>
              <div class="col-md-6">
                <label class="form-label">{{ t('settings.retryLimit') }}</label>
                <input v-model.number="runtimeForm.retry_limit" class="form-control form-control-sm" type="number" min="0" max="100" />
                <div class="d-flex flex-wrap gap-2 mt-1 small text-body-secondary">
                  <span class="text-break">{{ sourceLabel('retry_limit') }}</span>
                </div>
              </div>
              <div class="col-md-6">
                <label class="form-label">{{ t('settings.cleanupDays') }}</label>
                <input v-model.number="runtimeForm.cleanup_days" class="form-control form-control-sm" type="number" min="1" />
                <div class="d-flex flex-wrap gap-2 mt-1 small text-body-secondary">
                  <span class="text-break">{{ sourceLabel('cleanup_days') }}</span>
                </div>
              </div>
            </div>
        </section>

        <div class="d-flex flex-column flex-sm-row align-items-sm-center flex-wrap gap-2 p-3 border rounded-3 bg-white">
          <button class="btn btn-outline-primary btn-sm" :disabled="savingRuntime">{{ savingRuntime ? t('settings.saving') : t('settings.saveRuntime') }}</button>
          <button
            v-if="settings.restart.enabled"
            class="btn btn-outline-danger btn-sm"
            type="button"
            :disabled="savingRuntime || restarting || !settings.restart.available"
            :title="settings.restart.available ? '' : t('settings.restartUnavailable')"
            @click="restartService"
          >
            {{ restarting ? t('settings.restarting') : t('settings.restartService') }}
          </button>
        </div>
      </form>
    </section>
  </AdminLayout>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import AdminLayout from '../layouts/AdminLayout.vue'
import { apiFetch, ApiError } from '../lib/api'
import { useAuthStore } from '../stores/auth'
import type { RuntimeSettingsResponse } from '../types'

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()
const settings = ref<RuntimeSettingsResponse | null>(null)
const error = ref('')
const success = ref('')
const submitting = ref(false)
const savingRuntime = ref(false)
const restarting = ref(false)
const confirmPassword = ref('')
const form = reactive({ old_password: '', new_password: '' })
const runtimeForm = reactive({
  default_backend: '',
  vlm_base_url: '',
  vlm_model: '',
  vlm_max_concurrency: 2,
  title_base_url: '',
  title_model: '',
  postprocess_context_size: 131072,
  postprocess_max_concurrent: 2,
  max_concurrent: 3,
  task_timeout: 3600,
  retry_limit: 3,
  cleanup_days: 300,
})
const secretForm = reactive({ vlm_api_key: '', title_api_key: '' })

async function loadSettings() {
  settings.value = await apiFetch<RuntimeSettingsResponse>('/api/admin/settings/runtime')
  Object.assign(runtimeForm, settings.value.config)
  secretForm.vlm_api_key = ''
  secretForm.title_api_key = ''
}

function sourceLabel(key: string) {
  const source = settings.value?.sources?.[key] || 'environment'
  return source === 'database' ? t('settings.sourceDatabase') : t('settings.sourceEnvironment')
}

function secretPlaceholder(key: string) {
  const secret = settings.value?.secrets?.[key]
  return secret?.configured ? t('settings.keepExistingSecret') : t('settings.notConfigured')
}

function secretStatus(key: string) {
  const secret = settings.value?.secrets?.[key]
  if (!secret?.configured) return t('settings.notConfigured')
  const masked = `${secret.prefix || ''}...${secret.suffix || ''}`
  const source = secret.source === 'database' ? t('settings.sourceDatabase') : t('settings.sourceEnvironment')
  return t('settings.secretConfigured', { masked, source })
}

async function changePassword() {
  if (form.new_password !== confirmPassword.value) {
    error.value = t('settings.mismatch')
    return
  }
  submitting.value = true
  error.value = ''
  success.value = ''
  try {
    await apiFetch('/api/admin/change-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    })
    form.old_password = ''
    form.new_password = ''
    confirmPassword.value = ''
    success.value = t('settings.success')
    auth.clear()
    window.setTimeout(() => {
      router.push({ name: 'login' })
    }, 800)
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('settings.changeFailed')
  } finally {
    submitting.value = false
  }
}

async function saveRuntimeSettings() {
  savingRuntime.value = true
  error.value = ''
  success.value = ''
  try {
    const payload: Record<string, unknown> = { ...runtimeForm }
    if (secretForm.vlm_api_key.trim()) payload.vlm_api_key = secretForm.vlm_api_key.trim()
    if (secretForm.title_api_key.trim()) payload.title_api_key = secretForm.title_api_key.trim()
    settings.value = await apiFetch<RuntimeSettingsResponse>('/api/admin/settings/runtime', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    Object.assign(runtimeForm, settings.value.config)
    secretForm.vlm_api_key = ''
    secretForm.title_api_key = ''
    success.value = t('settings.runtimeSaved')
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('settings.runtimeSaveFailed')
  } finally {
    savingRuntime.value = false
  }
}

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

async function waitForHealthRestore() {
  const startedAt = Date.now()
  const deadline = startedAt + 60000
  let sawUnavailable = false

  await sleep(1000)
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`/health?restart_probe=${Date.now()}`, {
        cache: 'no-store',
      })
      if (response.ok && (sawUnavailable || Date.now() - startedAt > 5000)) {
        success.value = t('settings.restartCompletedLogin')
        auth.clear()
        window.setTimeout(() => {
          router.push({ name: 'login' })
        }, 800)
        return
      }
      if (!response.ok) {
        sawUnavailable = true
      }
    } catch {
      sawUnavailable = true
    }
    await sleep(1000)
  }
}

async function restartService() {
  restarting.value = true
  error.value = ''
  success.value = ''
  try {
    await apiFetch('/api/admin/system/restart', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    })
    success.value = t('settings.restartRequested')
    await waitForHealthRestore()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('settings.restartFailed')
  } finally {
    restarting.value = false
  }
}

onMounted(async () => {
  try {
    await loadSettings()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('settings.loadFailed')
  }
})
</script>
