<template>
  <div class="min-vh-100 d-flex flex-column">
    <header class="mk-portal-header">
      <div class="container-xl px-3 px-lg-4 mk-portal-header-inner">
        <RouterLink class="mk-portal-brand d-flex align-items-center gap-2 fw-semibold" :to="{ name: 'portal-home' }">
          <span class="mk-portal-brand-icon"><i class="bi bi-file-earmark-richtext"></i></span>
          <span>MinerU 文档解析</span>
        </RouterLink>

        <nav class="mk-portal-nav" :aria-label="t('portal.nav.ariaLabel')">
          <ul class="nav nav-pills flex-nowrap gap-1">
            <li class="nav-item"><RouterLink class="nav-link text-nowrap" :to="{ name: 'portal-home' }">{{ t('portal.nav.home') }}</RouterLink></li>
            <li class="nav-item"><RouterLink class="nav-link text-nowrap" :to="{ name: 'portal-new-task' }">{{ t('portal.nav.newTask') }}</RouterLink></li>
            <li class="nav-item"><RouterLink class="nav-link text-nowrap" :to="{ name: 'portal-tasks' }">{{ t('portal.nav.tasks') }}</RouterLink></li>
            <li class="nav-item"><RouterLink class="nav-link text-nowrap" :to="{ name: 'portal-ledger' }">{{ t('portal.nav.ledger') }}</RouterLink></li>
          </ul>
        </nav>

        <div class="dropdown mk-portal-user">
          <button
            class="btn btn-outline-secondary btn-sm mk-portal-user-button d-flex align-items-center gap-2"
            type="button"
            data-bs-toggle="dropdown"
            aria-expanded="false"
            :aria-label="t('portal.nav.userMenu')"
          >
            <i class="bi bi-person-circle"></i>
            <span class="mk-portal-user-name d-none d-sm-inline">{{ displayName }}</span>
            <i class="bi bi-chevron-down small"></i>
          </button>
          <ul class="dropdown-menu dropdown-menu-end shadow-sm">
            <li><span class="dropdown-item-text small text-body-secondary text-truncate">{{ displayName }}</span></li>
            <li><hr class="dropdown-divider" /></li>
            <li>
              <button class="dropdown-item text-danger" type="button" @click="logout">
                <i class="bi bi-box-arrow-right me-2"></i>{{ t('portal.nav.logout') }}
              </button>
            </li>
          </ul>
        </div>
      </div>
    </header>

    <main class="container-xl px-3 px-lg-4 py-4 py-lg-5 flex-grow-1 mk-portal-content">
      <div v-if="error" class="alert alert-danger">{{ error }}</div>
      <RouterView />
    </main>
    <footer class="container-xl px-3 px-lg-4 pb-4 mk-portal-footer">{{ t('portal.footer') }}</footer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { ApiError, apiFetch } from '../lib/api'
import { useAuthStore } from '../stores/auth'
import { usePortalStore } from '../stores/portal'

const router = useRouter()
const auth = useAuthStore()
const portal = usePortalStore()
const { t } = useI18n()
const error = ref('')
const displayName = computed(() => portal.profile?.display_name || auth.user?.display_name || auth.user?.username || '')

onMounted(async () => {
  try {
    await portal.loadProfile()
  } catch (caught) {
    if (caught instanceof ApiError && (caught.status === 401 || caught.status === 403)) {
      try {
        await auth.refresh()
      } catch {
        error.value = t('portal.layout.sessionFailed')
      }
    } else {
      error.value = caught instanceof Error ? caught.message : t('portal.layout.profileFailed')
    }
  }
})

async function logout() {
  try {
    await apiFetch('/api/admin/logout', { method: 'POST' })
  } catch (err) {
    error.value = err instanceof Error ? t('portal.layout.logoutFailedDetail', { detail: err.message }) : t('portal.layout.logoutFailed')
    return
  }
  auth.clear()
  portal.clear()
  await router.push({ name: 'login' })
}
</script>
