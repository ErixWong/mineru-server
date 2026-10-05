<template>
  <div class="min-vh-100 d-flex flex-column">
    <header class="mk-portal-header">
      <div class="container-fluid px-3 px-lg-4 mk-portal-header-inner mk-portal-content">
        <RouterLink class="mk-portal-brand d-flex align-items-center gap-2 fw-semibold" :to="{ name: 'dashboard' }">
          <span class="mk-portal-brand-icon"><i class="bi bi-file-earmark-richtext"></i></span>
          <span>{{ t('nav.brandTitle') }}</span>
        </RouterLink>

        <nav class="mk-portal-nav" :aria-label="t('nav.ariaLabel')">
          <ul class="nav nav-pills flex-nowrap gap-1">
            <li class="nav-item"><RouterLink class="nav-link text-nowrap" :to="{ name: 'dashboard' }">{{ t('nav.dashboard') }}</RouterLink></li>
            <li class="nav-item"><RouterLink class="nav-link text-nowrap" :to="{ name: 'callers' }">{{ t('nav.callers') }}</RouterLink></li>
            <li class="nav-item"><RouterLink class="nav-link text-nowrap" :to="{ name: 'users' }">{{ t('nav.users') }}</RouterLink></li>
            <li class="nav-item"><RouterLink class="nav-link text-nowrap" :class="{ 'router-link-active': route.name === 'task-detail' }" :to="{ name: 'tasks' }">{{ t('nav.tasks') }}</RouterLink></li>
            <li class="nav-item"><RouterLink class="nav-link text-nowrap" :to="{ name: 'postprocess-rules' }">{{ t('nav.postprocessRules') }}</RouterLink></li>
            <li class="nav-item"><RouterLink class="nav-link text-nowrap" :to="{ name: 'settings' }">{{ t('nav.settings') }}</RouterLink></li>
          </ul>
        </nav>

        <div class="dropdown mk-admin-language">
          <button class="btn btn-light border btn-sm dropdown-toggle" type="button" data-bs-toggle="dropdown" aria-expanded="false" :aria-label="t('nav.language')">
            <i class="bi bi-translate me-1"></i>{{ locale === 'zh-CN' ? t('nav.localeShortChinese') : t('nav.localeShortEnglish') }}
          </button>
          <ul class="dropdown-menu dropdown-menu-end">
            <li><button class="dropdown-item" :class="{ active: locale === 'zh-CN' }" @click="switchLocale('zh-CN')">{{ t('nav.localeChinese') }}</button></li>
            <li><button class="dropdown-item" :class="{ active: locale === 'en' }" @click="switchLocale('en')">{{ t('nav.localeEnglish') }}</button></li>
          </ul>
        </div>

        <div class="dropdown mk-portal-user">
          <button
            class="btn btn-outline-secondary btn-sm mk-portal-user-button d-flex align-items-center gap-2"
            type="button"
            data-bs-toggle="dropdown"
            aria-expanded="false"
            :aria-label="t('nav.userMenu')"
          >
            <i class="bi bi-person-circle"></i>
            <span class="mk-portal-user-name d-none d-sm-inline">{{ username }}</span>
            <i class="bi bi-chevron-down small"></i>
          </button>
          <ul class="dropdown-menu dropdown-menu-end shadow-sm">
            <li><span class="dropdown-item-text small text-body-secondary text-truncate">{{ username }}</span></li>
            <li><hr class="dropdown-divider" /></li>
            <li>
              <button class="dropdown-item text-danger" type="button" @click="logout">
                <i class="bi bi-box-arrow-right me-2"></i>{{ t('nav.logout') }}
              </button>
            </li>
          </ul>
        </div>
      </div>
    </header>

    <main class="container-fluid px-3 px-lg-4 py-4 py-lg-5 flex-grow-1 mk-portal-content">
      <div v-if="error" class="alert bg-body border border-danger-subtle rounded-3 py-2 text-danger-emphasis">{{ error }}</div>
      <slot />
    </main>
    <footer class="container-fluid px-3 px-lg-4 pb-4 small text-body-secondary mk-portal-footer mk-portal-content">{{ t('portal.footer') }}</footer>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { apiFetch, ApiError } from '../lib/api'
import { useAuthStore } from '../stores/auth'
import { setLocale, getLocale, type SupportedLocale } from '../i18n'

const { t, locale } = useI18n()
const route = useRoute()
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
