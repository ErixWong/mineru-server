<template>
  <div class="app-shell d-flex flex-column">
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
      <div class="container-fluid px-4">
        <RouterLink class="navbar-brand" to="/">{{ t('nav.brandTitle') }}</RouterLink>
        <div class="navbar-nav flex-row gap-3 ms-auto align-items-center">
          <div class="dropdown">
            <button class="btn btn-outline-light btn-sm dropdown-toggle" type="button" data-bs-toggle="dropdown" aria-expanded="false">
              <i class="bi bi-translate me-1"></i>{{ locale === 'zh-CN' ? '中文' : 'EN' }}
            </button>
            <ul class="dropdown-menu dropdown-menu-end">
              <li><button class="dropdown-item" :class="{ active: locale === 'zh-CN' }" @click="switchLocale('zh-CN')">中文</button></li>
              <li><button class="dropdown-item" :class="{ active: locale === 'en' }" @click="switchLocale('en')">English</button></li>
            </ul>
          </div>
          <span class="navbar-text">{{ username }}</span>
          <button class="btn btn-outline-light btn-sm" @click="logout">{{ t('nav.logout') }}</button>
        </div>
      </div>
    </nav>

    <div class="container py-4 flex-grow-1">
      <div v-if="error" class="alert alert-danger">{{ error }}</div>
      <ul class="nav nav-tabs mb-4">
        <li class="nav-item"><RouterLink class="nav-link" to="/">{{ t('nav.dashboard') }}</RouterLink></li>
        <li class="nav-item"><RouterLink class="nav-link" to="/callers">{{ t('nav.callers') }}</RouterLink></li>
        <li class="nav-item"><RouterLink class="nav-link" to="/tasks">{{ t('nav.tasks') }}</RouterLink></li>
        <li class="nav-item"><RouterLink class="nav-link" to="/postprocess-rules">{{ t('nav.postprocessRules') }}</RouterLink></li>
        <li class="nav-item"><RouterLink class="nav-link" to="/settings">{{ t('nav.settings') }}</RouterLink></li>
      </ul>
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { apiFetch, ApiError } from '../lib/api'
import { useAuthStore } from '../stores/auth'
import { setLocale, getLocale, type SupportedLocale } from '../i18n'

const { t, locale } = useI18n()
const router = useRouter()
const auth = useAuthStore()
const username = computed(() => auth.user?.username ?? '')
const error = ref('')
const switchingLocale = ref(false)

async function switchLocale(loc: SupportedLocale) {
  if (getLocale() === loc || switchingLocale.value) return
  switchingLocale.value = true
  try {
    // Write to server first: if this fails, local state stays consistent.
    await apiFetch('/api/admin/me', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ locale: loc }),
    })
    setLocale(loc)
  } catch {
    error.value = t('common.localeSaveFailed')
    setTimeout(() => { if (error.value === t('common.localeSaveFailed')) error.value = '' }, 4000)
  } finally {
    switchingLocale.value = false
  }
}

async function logout() {
  error.value = ''
  try {
    await apiFetch('/api/admin/logout', { method: 'POST' })
    auth.clear()
    router.push({ name: 'login' })
  } catch (err) {
    const message = err instanceof ApiError ? err.message : t('nav.logoutFailed')
    error.value = `${message}。${t('nav.logoutForceRedirect')}`
    auth.clear()
    window.setTimeout(() => {
      router.push({ name: 'login' })
    }, 800)
  }
}
</script>

<style scoped>
.router-link-active.nav-link {
  color: var(--bs-primary);
}
</style>
