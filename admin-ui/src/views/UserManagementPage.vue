<template>
  <AdminLayout>
    <div class="d-flex flex-wrap justify-content-between align-items-end gap-3 mb-4">
      <div>
        <div class="small text-uppercase text-body-secondary fw-semibold mb-1">{{ t('nav.users') }}</div>
        <h1 class="fs-3 fw-semibold mb-0">{{ t('users.title') }}</h1>
      </div>
      <div class="d-flex gap-2">
        <button class="btn btn-outline-secondary" :disabled="loading" @click="loadUsers">
          <i class="bi bi-arrow-clockwise me-1"></i>{{ t('common.refresh') }}
        </button>
        <button class="btn btn-outline-primary" @click="openCreateDialog">
          <i class="bi bi-person-plus me-1"></i>{{ t('users.create') }}
        </button>
      </div>
    </div>

    <div v-if="error" class="alert bg-body border border-danger-subtle rounded-3 py-2 text-danger-emphasis">{{ error }}</div>
    <div v-if="flash" class="alert bg-body border border-success-subtle rounded-3 py-2 text-success-emphasis">{{ flash }}</div>

    <div class="card">
      <div class="card-body">
        <div class="table-responsive">
          <table class="table table-hover align-middle mb-0">
            <thead>
              <tr>
                <th class="small text-body-secondary fw-semibold">{{ t('users.username') }}</th>
                <th class="small text-body-secondary fw-semibold">{{ t('users.displayName') }}</th>
                <th class="small text-body-secondary fw-semibold">{{ t('users.role') }}</th>
                <th class="small text-body-secondary fw-semibold text-end">{{ t('users.quotaTotal') }}</th>
                <th class="small text-body-secondary fw-semibold text-end">{{ t('users.quotaUsed') }}</th>
                <th class="small text-body-secondary fw-semibold text-end">{{ t('users.quotaRemaining') }}</th>
                <th class="small text-body-secondary fw-semibold">{{ t('users.apiKey') }}</th>
                <th class="small text-body-secondary fw-semibold">{{ t('users.status') }}</th>
                <th class="small text-body-secondary fw-semibold text-nowrap">{{ t('users.createdAt') }}</th>
                <th class="small text-body-secondary fw-semibold">{{ t('users.actions') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading">
                <td colspan="10" class="text-center text-body-secondary py-5"><i class="bi bi-arrow-repeat me-2"></i>{{ t('common.loading') }}</td>
              </tr>
              <tr v-else-if="users.length === 0">
                <td colspan="10" class="text-center text-body-secondary py-5"><i class="bi bi-people fs-4 d-block mb-2"></i>{{ t('users.noData') }}</td>
              </tr>
              <tr v-for="user in users" :key="user.user_id">
                <td class="fw-semibold text-nowrap">{{ user.username }}</td>
                <td>{{ user.display_name || '-' }}</td>
                <td>
                  <span class="badge" :class="user.role === 'admin' ? 'bg-primary-subtle text-primary-emphasis' : 'bg-info-subtle text-info-emphasis'">
                    {{ user.role === 'admin' ? t('users.adminRole') : t('users.userRole') }}
                  </span>
                </td>
                <td class="text-end text-nowrap">{{ formatQuota(user.quota_total_pages) }}</td>
                <td class="text-end text-nowrap">{{ formatQuota(user.quota_used_pages) }}</td>
                <td class="text-end text-nowrap">{{ formatQuota(user.quota_remaining_pages) }}</td>
                <td class="font-monospace small text-nowrap">{{ maskApiKey(user) }}</td>
                <td>
                  <span class="badge" :class="user.disabled ? 'bg-secondary-subtle text-secondary-emphasis' : 'bg-success-subtle text-success-emphasis'">
                    {{ user.disabled ? t('users.disabled') : t('users.enabled') }}
                  </span>
                </td>
                <td class="small text-body-secondary text-nowrap">{{ formatDate(user.created_at) }}</td>
                <td>
                  <div class="d-flex flex-wrap gap-1">
                    <button class="btn btn-outline-primary btn-sm" :disabled="actionLoadingUserId === user.user_id" @click="toggleUser(user)">
                      {{ user.disabled ? t('common.enable') : t('common.disable') }}
                    </button>
                    <button class="btn btn-outline-warning btn-sm" :disabled="actionLoadingUserId === user.user_id" @click="resetPassword(user)">
                      {{ t('users.resetPassword') }}
                    </button>
                    <button class="btn btn-outline-success btn-sm" :disabled="actionLoadingUserId === user.user_id" @click="openTopUpDialog(user)">
                      {{ t('users.topUp') }}
                    </button>
                    <button class="btn btn-outline-secondary btn-sm" @click="openLedgerDialog(user)">
                      {{ t('users.ledger') }}
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <template v-if="createDialogOpen">
      <div class="modal-backdrop show"></div>
      <div class="modal d-block" tabindex="-1" role="dialog" aria-modal="true" @keydown.esc.prevent.stop>
        <div class="modal-dialog modal-dialog-centered">
          <div class="modal-content">
            <div class="modal-header">
              <h2 class="modal-title fs-5">{{ createdApiKey ? t('users.createSuccess') : t('users.create') }}</h2>
              <button v-if="!createdApiKey" type="button" class="btn-close" :aria-label="t('common.close')" :disabled="creating" @click="closeCreateDialog"></button>
            </div>
            <div v-if="createdApiKey" class="modal-body">
              <div class="alert alert-warning" role="alert"><i class="bi bi-exclamation-triangle-fill me-2"></i>{{ t('users.apiKeyWarning') }}</div>
              <label class="form-label" for="created-api-key">{{ t('users.apiKey') }}</label>
              <div class="input-group">
                <input id="created-api-key" :value="createdApiKey" class="form-control font-monospace" readonly @focus="selectInput" />
                <button class="btn btn-outline-secondary" type="button" @click="copyCreatedApiKey">{{ t('common.copy') }}</button>
              </div>
              <div v-if="secretCopyError" class="small text-danger mt-2">{{ secretCopyError }}</div>
              <div class="form-check mt-3">
                <input id="api-key-acknowledged" v-model="createKeyAcknowledged" class="form-check-input" type="checkbox" />
                <label class="form-check-label small" for="api-key-acknowledged">{{ t('users.secretAcknowledgement') }}</label>
              </div>
            </div>
            <form v-else class="modal-body" @submit.prevent="createUser">
              <div class="mb-3">
                <label class="form-label" for="new-username">{{ t('users.username') }}</label>
                <input id="new-username" v-model="createForm.username" class="form-control" maxlength="128" required autocomplete="off" />
              </div>
              <div class="mb-3">
                <label class="form-label" for="new-display-name">{{ t('users.displayName') }}</label>
                <input id="new-display-name" v-model="createForm.display_name" class="form-control" maxlength="128" />
              </div>
              <div class="mb-3">
                <label class="form-label" for="new-user-password">{{ t('users.initialPassword') }}</label>
                <div class="input-group">
                  <input id="new-user-password" v-model="createForm.password" class="form-control font-monospace" type="password" minlength="8" required autocomplete="new-password" />
                  <button class="btn btn-outline-secondary" type="button" @click="generateInitialPassword">{{ t('users.generatePassword') }}</button>
                  <button class="btn btn-outline-secondary" type="button" :disabled="!createForm.password" @click="copyValue(createForm.password)">{{ t('users.copyPassword') }}</button>
                </div>
                <div v-if="secretCopyError" class="small text-danger mt-2">{{ secretCopyError }}</div>
              </div>
              <div class="mb-3">
                <label class="form-label" for="new-user-role">{{ t('users.role') }}</label>
                <select id="new-user-role" v-model="createForm.role" class="form-select">
                  <option value="user">{{ t('users.userRole') }}</option>
                  <option value="admin">{{ t('users.adminRole') }}</option>
                </select>
              </div>
              <div v-if="error" class="alert alert-danger py-2 mb-0">{{ error }}</div>
              <div class="d-flex justify-content-end gap-2 mt-3">
                <button class="btn btn-outline-secondary" type="button" :disabled="creating" @click="closeCreateDialog">{{ t('common.cancel') }}</button>
                <button class="btn btn-primary" type="submit" :disabled="creating || !createForm.username.trim() || createForm.password.length < 8">
                  {{ creating ? t('common.creating') : t('common.create') }}
                </button>
              </div>
            </form>
            <div v-if="createdApiKey" class="modal-footer">
              <button class="btn btn-primary" :disabled="!createKeyAcknowledged" @click="closeCreateDialog">{{ t('users.secretClose') }}</button>
            </div>
          </div>
        </div>
      </div>
    </template>

    <template v-if="secretDialogOpen">
      <div class="modal-backdrop show"></div>
      <div class="modal d-block" tabindex="-1" role="dialog" aria-modal="true" @keydown.esc.prevent.stop>
        <div class="modal-dialog modal-dialog-centered">
          <div class="modal-content">
            <div class="modal-header">
              <h2 class="modal-title fs-5">{{ t('users.passwordResetTitle') }} · {{ secretUserName }}</h2>
            </div>
            <div class="modal-body">
              <div class="alert alert-warning" role="alert"><i class="bi bi-exclamation-triangle-fill me-2"></i>{{ t('users.passwordResetWarning') }}</div>
              <div class="input-group">
                <input id="reset-user-password" :value="oneTimePassword" class="form-control font-monospace" readonly @focus="selectInput" />
                <button class="btn btn-outline-secondary" type="button" @click="copyResetPassword">{{ t('common.copy') }}</button>
              </div>
              <div v-if="secretCopyError" class="small text-danger mt-2">{{ secretCopyError }}</div>
              <div class="form-check mt-3">
                <input id="password-acknowledged" v-model="passwordAcknowledged" class="form-check-input" type="checkbox" />
                <label class="form-check-label small" for="password-acknowledged">{{ t('users.secretAcknowledgement') }}</label>
              </div>
            </div>
            <div class="modal-footer">
              <button class="btn btn-primary" :disabled="!passwordAcknowledged" @click="closeSecretDialog">{{ t('users.secretClose') }}</button>
            </div>
          </div>
        </div>
      </div>
    </template>

    <template v-if="topUpDialogOpen && selectedUser">
      <div class="modal-backdrop show"></div>
      <div class="modal d-block" tabindex="-1" role="dialog" aria-modal="true" @keydown.esc.prevent.stop>
        <div class="modal-dialog modal-dialog-centered">
          <div class="modal-content">
            <div class="modal-header">
              <h2 class="modal-title fs-5">{{ t('users.topUpTitle', { name: selectedUser.display_name || selectedUser.username }) }}</h2>
              <button type="button" class="btn-close" :aria-label="t('common.close')" :disabled="topUpSubmitting" @click="closeTopUpDialog"></button>
            </div>
            <form class="modal-body" @submit.prevent="submitTopUp">
              <div v-if="topUpError" class="alert alert-danger py-2">{{ topUpError }}</div>
              <div class="mb-3">
                <label class="form-label" for="top-up-pages">{{ t('users.pages') }}</label>
                <input id="top-up-pages" v-model.number="topUpForm.pages" class="form-control" type="number" min="1" step="1" required />
              </div>
              <div>
                <label class="form-label" for="top-up-reason">{{ t('users.reason') }}</label>
                <textarea id="top-up-reason" v-model="topUpForm.reason" class="form-control" rows="3" maxlength="512" required></textarea>
              </div>
              <div class="d-flex justify-content-end gap-2 mt-3">
                <button class="btn btn-outline-secondary" type="button" :disabled="topUpSubmitting" @click="closeTopUpDialog">{{ t('common.cancel') }}</button>
                <button class="btn btn-primary" type="submit" :disabled="topUpSubmitting || !Number.isSafeInteger(topUpForm.pages) || topUpForm.pages <= 0 || !topUpForm.reason.trim()">
                  {{ topUpSubmitting ? t('common.submitting') : t('users.topUp') }}
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </template>

    <template v-if="ledgerDialogOpen && selectedUser">
      <div class="modal-backdrop show"></div>
      <div class="modal d-block" tabindex="-1" role="dialog" aria-modal="true" @keydown.esc.prevent.stop>
        <div class="modal-dialog modal-dialog-centered modal-lg modal-dialog-scrollable">
          <div class="modal-content">
            <div class="modal-header">
              <h2 class="modal-title fs-5">{{ t('users.ledgerTitle', { name: selectedUser.display_name || selectedUser.username }) }}</h2>
              <button type="button" class="btn-close" :aria-label="t('common.close')" @click="closeLedgerDialog"></button>
            </div>
            <div class="modal-body">
              <div v-if="ledgerError" class="alert alert-danger py-2">{{ ledgerError }}</div>
              <div v-if="ledgerLoading" class="text-center text-body-secondary py-5">{{ t('common.loading') }}</div>
              <div v-else-if="ledgerItems.length === 0" class="text-center text-body-secondary py-5">{{ t('users.ledgerNoData') }}</div>
              <div v-else class="table-responsive">
                <table class="table table-hover align-middle mb-0">
                  <thead>
                    <tr>
                      <th class="text-nowrap">{{ t('users.ledgerTime') }}</th>
                      <th>{{ t('users.ledgerReason') }}</th>
                      <th class="text-end text-nowrap">{{ t('users.ledgerDelta') }}</th>
                      <th class="text-end text-nowrap">{{ t('users.ledgerBalance') }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="item in ledgerItems" :key="item.ledger_id">
                      <td class="small text-body-secondary text-nowrap">{{ formatDate(item.created_at) }}</td>
                      <td>
                        <div>{{ ledgerReason(item.reason) }}</div>
                        <div v-if="item.task_id" class="small text-body-secondary font-monospace">{{ item.task_id }}</div>
                      </td>
                      <td class="text-end fw-semibold text-nowrap" :class="item.delta >= 0 ? 'text-success' : 'text-danger'">
                        {{ item.delta > 0 ? '+' : '' }}{{ formatNumber(item.delta) }}
                      </td>
                      <td class="text-end text-nowrap">{{ formatNumber(item.balance_after) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mt-3">
                <div class="small text-body-secondary">{{ t('users.ledgerPagination', { total: ledgerTotal, page: ledgerPage, totalPages: ledgerTotalPages }) }}</div>
                <div v-if="ledgerTotalPages > 1" class="btn-group btn-group-sm">
                  <button class="btn btn-outline-secondary" :disabled="ledgerPage <= 1 || ledgerLoading" @click="goToLedgerPage(ledgerPage - 1)">{{ t('users.previousPage') }}</button>
                  <button class="btn btn-outline-secondary" :disabled="ledgerPage >= ledgerTotalPages || ledgerLoading" @click="goToLedgerPage(ledgerPage + 1)">{{ t('users.nextPage') }}</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </AdminLayout>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AdminLayout from '../layouts/AdminLayout.vue'
import { apiFetch, ApiError } from '../lib/api'
import type { AdminUserCreated, AdminUserItem, PortalQuotaLedgerItem, PortalQuotaLedgerPage } from '../types'

const { t } = useI18n()

const users = ref<AdminUserItem[]>([])
const loading = ref(false)
const creating = ref(false)
const createDialogOpen = ref(false)
const createdApiKey = ref('')
const createKeyAcknowledged = ref(false)
const secretDialogOpen = ref(false)
const oneTimePassword = ref('')
const secretUserName = ref('')
const passwordAcknowledged = ref(false)
const secretCopyError = ref('')
const error = ref('')
const flash = ref('')
const actionLoadingUserId = ref('')
const createForm = reactive({ username: '', display_name: '', password: '', role: 'user' as 'admin' | 'user' })
const selectedUser = ref<AdminUserItem | null>(null)
const topUpDialogOpen = ref(false)
const topUpSubmitting = ref(false)
const topUpError = ref('')
const topUpForm = reactive({ pages: 1, reason: '' })
const ledgerDialogOpen = ref(false)
const ledgerLoading = ref(false)
const ledgerError = ref('')
const ledgerItems = ref<PortalQuotaLedgerItem[]>([])
const ledgerPage = ref(1)
const ledgerTotal = ref(0)
const ledgerTotalPages = ref(1)
const ledgerPageSize = 20

function formatNumber(value: number) {
  return value.toLocaleString()
}

function formatQuota(value: number | null) {
  return value === null ? t('users.unlimited') : formatNumber(value)
}

function formatDate(value?: string | null) {
  return value ? new Date(value).toLocaleString() : '-'
}

function maskApiKey(user: AdminUserItem) {
  if (!user.api_key_prefix && !user.api_key_suffix) return '-'
  return `${user.api_key_prefix || ''}...${user.api_key_suffix || ''}`
}

function generatePassword() {
  const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789'
  const random = crypto.getRandomValues(new Uint32Array(20))
  return Array.from(random, (value) => alphabet[value % alphabet.length]).join('')
}

function generateInitialPassword() {
  secretCopyError.value = ''
  createForm.password = generatePassword()
}

async function copyValue(value: string) {
  secretCopyError.value = ''
  try {
    await navigator.clipboard.writeText(value)
  } catch {
    secretCopyError.value = t('users.secretCopyFailed')
  }
}

function selectInput(event: FocusEvent) {
  (event.target as HTMLInputElement).select()
}

function openCreateDialog() {
  error.value = ''
  flash.value = ''
  secretCopyError.value = ''
  createDialogOpen.value = true
}

function closeCreateDialog() {
  if (creating.value || (createdApiKey.value && !createKeyAcknowledged.value)) return
  createDialogOpen.value = false
  createdApiKey.value = ''
  createKeyAcknowledged.value = false
  secretCopyError.value = ''
  createForm.username = ''
  createForm.display_name = ''
  createForm.password = ''
  createForm.role = 'user'
}

async function copyCreatedApiKey() {
  if (!createdApiKey.value) return
  secretCopyError.value = ''
  try {
    await navigator.clipboard.writeText(createdApiKey.value)
  } catch {
    secretCopyError.value = t('users.secretCopyFailed')
  }
}

async function createUser() {
  creating.value = true
  error.value = ''
  secretCopyError.value = ''
  try {
    const payload = await apiFetch<AdminUserCreated>('/api/admin/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: createForm.username.trim(),
        display_name: createForm.display_name.trim() || null,
        password: createForm.password,
        role: createForm.role,
      }),
    })
    createdApiKey.value = payload.api_key
    createForm.password = ''
    createKeyAcknowledged.value = false
    await loadUsers()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('users.createFailed')
  } finally {
    creating.value = false
  }
}

async function loadUsers() {
  loading.value = true
  error.value = ''
  try {
    users.value = await apiFetch<AdminUserItem[]>('/api/admin/users?include_disabled=true')
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('common.loadFailed')
  } finally {
    loading.value = false
  }
}

async function toggleUser(user: AdminUserItem) {
  const nextDisabled = !user.disabled
  const action = nextDisabled ? t('users.disableAction') : t('users.enableAction')
  if (!window.confirm(t('users.toggleConfirm', { action, name: user.display_name || user.username }))) return

  actionLoadingUserId.value = user.user_id
  error.value = ''
  flash.value = ''
  try {
    await apiFetch(`/api/admin/users/${encodeURIComponent(user.user_id)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ disabled: nextDisabled }),
    })
    flash.value = nextDisabled ? t('users.userDisabled') : t('users.userEnabled')
    await loadUsers()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('common.updateFailed')
  } finally {
    actionLoadingUserId.value = ''
  }
}

async function resetPassword(user: AdminUserItem) {
  if (!window.confirm(t('users.resetPasswordConfirm', { name: user.display_name || user.username }))) return
  const password = generatePassword()
  actionLoadingUserId.value = user.user_id
  error.value = ''
  secretCopyError.value = ''
  try {
    await apiFetch(`/api/admin/users/${encodeURIComponent(user.user_id)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    })
    oneTimePassword.value = password
    secretUserName.value = user.display_name || user.username
    passwordAcknowledged.value = false
    secretDialogOpen.value = true
    await loadUsers()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('users.resetPasswordFailed')
  } finally {
    actionLoadingUserId.value = ''
  }
}

async function copyResetPassword() {
  await copyValue(oneTimePassword.value)
}

function closeSecretDialog() {
  if (!passwordAcknowledged.value) return
  secretDialogOpen.value = false
  oneTimePassword.value = ''
  secretUserName.value = ''
  passwordAcknowledged.value = false
  secretCopyError.value = ''
}

function openTopUpDialog(user: AdminUserItem) {
  selectedUser.value = user
  topUpForm.pages = 1
  topUpForm.reason = ''
  topUpError.value = ''
  topUpDialogOpen.value = true
}

function closeTopUpDialog() {
  if (topUpSubmitting.value) return
  topUpDialogOpen.value = false
  topUpError.value = ''
  topUpForm.reason = ''
}

async function submitTopUp() {
  if (!selectedUser.value || !Number.isSafeInteger(topUpForm.pages) || topUpForm.pages <= 0 || !topUpForm.reason.trim()) return
  topUpSubmitting.value = true
  topUpError.value = ''
  error.value = ''
  flash.value = ''
  try {
    await apiFetch(`/api/admin/users/${encodeURIComponent(selectedUser.value.user_id)}/quota`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pages: topUpForm.pages, reason: topUpForm.reason.trim() }),
    })
    topUpDialogOpen.value = false
    flash.value = t('users.topUpSuccess')
    await loadUsers()
  } catch (err) {
    topUpError.value = err instanceof ApiError ? err.message : t('users.topUpFailed')
  } finally {
    topUpSubmitting.value = false
  }
}

function openLedgerDialog(user: AdminUserItem) {
  selectedUser.value = user
  ledgerDialogOpen.value = true
  ledgerPage.value = 1
  ledgerItems.value = []
  ledgerTotal.value = 0
  ledgerTotalPages.value = 1
  void loadLedger()
}

function closeLedgerDialog() {
  ledgerDialogOpen.value = false
  ledgerError.value = ''
  ledgerItems.value = []
}

async function loadLedger() {
  if (!selectedUser.value) return
  ledgerLoading.value = true
  ledgerError.value = ''
  try {
    const result = await apiFetch<PortalQuotaLedgerPage>(
      `/api/admin/users/${encodeURIComponent(selectedUser.value.user_id)}/quota/ledger?page=${ledgerPage.value}&size=${ledgerPageSize}`,
    )
    ledgerItems.value = result.items
    ledgerTotal.value = result.total
    ledgerTotalPages.value = Math.max(1, result.total_pages)
  } catch (err) {
    ledgerError.value = err instanceof ApiError ? err.message : t('common.loadFailed')
  } finally {
    ledgerLoading.value = false
  }
}

function goToLedgerPage(page: number) {
  ledgerPage.value = page
  void loadLedger()
}

function ledgerReason(reason: string) {
  const knownReasons: Record<string, string> = {
    task_reservation: t('users.taskReservation'),
    task_settlement: t('users.taskSettlement'),
    task_release: t('users.taskRelease'),
    task_refund: t('users.taskRefund'),
  }
  return knownReasons[reason] || reason.replace(/_/g, ' ')
}

onMounted(() => void loadUsers())
</script>
