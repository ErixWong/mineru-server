<template>
  <div class="container py-5" style="max-width: 420px">
    <div class="d-flex justify-content-end mb-2">
      <div class="dropdown">
        <button class="btn btn-sm btn-outline-secondary dropdown-toggle" type="button" data-bs-toggle="dropdown" aria-expanded="false">
          <i class="bi bi-translate me-1"></i>{{ locale === 'zh-CN' ? '中文' : 'EN' }}
        </button>
        <ul class="dropdown-menu dropdown-menu-end">
          <li><button class="dropdown-item" :class="{ active: locale === 'zh-CN' }" @click="switchLocale('zh-CN')">中文</button></li>
          <li><button class="dropdown-item" :class="{ active: locale === 'en' }" @click="switchLocale('en')">English</button></li>
        </ul>
      </div>
    </div>
    <div class="card page-card">
      <div class="card-body p-4">
        <h3 class="card-title mb-3">{{ t('login.title') }}</h3>
        <p class="text-muted">{{ t('login.subtitle') }}</p>
        <div v-if="error" class="alert alert-danger">{{ error }}</div>
        <form @submit.prevent="submit">
          <div class="mb-3">
            <label class="form-label">{{ t('login.username') }}</label>
            <input v-model="form.username" class="form-control" required />
          </div>
          <div class="mb-3">
            <label class="form-label">{{ t('login.password') }}</label>
            <input v-model="form.password" class="form-control" type="password" required />
          </div>
          <button class="btn btn-primary w-100" :disabled="submitting">
            {{ submitting ? t('login.loggingIn') : t('login.loginButton') }}
          </button>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { apiFetch, ApiError } from '../lib/api'
import { useAuthStore } from '../stores/auth'
import { setLocale, type SupportedLocale } from '../i18n'

const { t, locale } = useI18n()
const router = useRouter()
const auth = useAuthStore()
const submitting = ref(false)
const error = ref('')
const form = reactive({ username: 'admin', password: '' })

function switchLocale(loc: SupportedLocale) {
  setLocale(loc)
}

async function submit() {
  submitting.value = true
  error.value = ''
  try {
    const result = await apiFetch<{ success: boolean; must_change_password: boolean }>('/api/admin/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    })
    await auth.refresh()
    router.push(result.must_change_password ? { name: 'change-password' } : { name: 'dashboard' })
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('login.loginFailed')
  } finally {
    submitting.value = false
  }
}
</script>
