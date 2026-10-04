<template>
  <main class="min-vh-100 bg-body-tertiary d-flex align-items-center py-4 py-lg-5">
    <div class="container">
      <div class="row justify-content-center align-items-stretch g-0">
        <section class="col-lg-5 d-none d-lg-flex">
          <div class="w-100 rounded-start-4 bg-dark text-white p-5 d-flex flex-column justify-content-between">
            <div>
              <div class="d-inline-flex align-items-center gap-2 mb-5">
                <i class="bi bi-file-earmark-richtext fs-3 text-info"></i>
                <span class="fw-semibold">{{ t('nav.brandTitle') }}</span>
              </div>
              <h1 class="display-6 fw-semibold mb-3">{{ t('login.title') }}</h1>
              <p class="text-white-50 mb-0">{{ t('login.subtitle') }}</p>
            </div>
            <i class="bi bi-file-earmark-pdf text-white-50 display-3 align-self-end"></i>
          </div>
        </section>
        <section class="col-12 col-md-8 col-lg-5">
          <div class="d-flex justify-content-end mb-3">
            <div class="dropdown">
              <button class="btn btn-sm btn-outline-secondary dropdown-toggle" type="button" data-bs-toggle="dropdown" aria-expanded="false">
                <i class="bi bi-translate me-1"></i>{{ locale === 'zh-CN' ? '中文' : 'EN' }}
              </button>
              <ul class="dropdown-menu dropdown-menu-end">
                <li><button class="dropdown-item" :class="{ 'text-primary fw-semibold': locale === 'zh-CN' }" @click="switchLocale('zh-CN')">中文</button></li>
                <li><button class="dropdown-item" :class="{ 'text-primary fw-semibold': locale === 'en' }" @click="switchLocale('en')">English</button></li>
              </ul>
            </div>
          </div>
          <div class="card rounded-4 border-0">
            <div class="card-body p-4 p-lg-5">
              <div class="d-lg-none d-flex align-items-center gap-2 mb-4">
                <i class="bi bi-file-earmark-richtext fs-3 text-primary"></i>
                <span class="fw-semibold">{{ t('nav.brandTitle') }}</span>
              </div>
              <h2 class="fs-4 fw-semibold mb-2">{{ t('login.title') }}</h2>
              <p class="text-body-secondary mb-4">{{ t('login.subtitle') }}</p>
              <div v-if="error" class="alert bg-body border border-danger-subtle rounded-3 py-2 text-danger-emphasis">{{ error }}</div>
              <form @submit.prevent="submit">
                <div class="mb-3">
                  <label class="form-label">{{ t('login.username') }}</label>
                  <input v-model="form.username" class="form-control" required />
                </div>
                <div class="mb-4">
                  <label class="form-label">{{ t('login.password') }}</label>
                  <input v-model="form.password" class="form-control" type="password" required />
                </div>
                <button class="btn btn-outline-primary w-100" :disabled="submitting">
                  <i class="bi bi-box-arrow-in-right me-1"></i>
                  {{ submitting ? t('login.loggingIn') : t('login.loginButton') }}
                </button>
              </form>
            </div>
          </div>
        </section>
      </div>
    </div>
  </main>
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
