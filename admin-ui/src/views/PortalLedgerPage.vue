<template>
  <section>
    <div class="mb-4">
      <div class="small text-uppercase text-body-secondary fw-semibold mb-1">{{ t('portal.ledger.eyebrow') }}</div>
      <h1 class="fs-3 fw-semibold mb-1">{{ t('portal.ledger.title') }}</h1>
      <p class="text-body-secondary mb-0">{{ t('portal.ledger.subtitle') }}</p>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>
    <div class="card">
      <div class="card-body">
        <div v-if="loading" class="text-center text-body-secondary py-5">{{ t('portal.ledger.loading') }}</div>
        <div v-else-if="!items.length" class="mk-empty">
          <i class="bi bi-journal-text mk-empty-icon"></i>
          <h2 class="mk-empty-title">{{ t('portal.ledger.emptyTitle') }}</h2>
          <p class="mk-empty-description">{{ t('portal.ledger.emptyDescription') }}</p>
        </div>
        <div v-else class="table-responsive">
          <table class="table table-hover align-middle mb-0">
            <thead>
              <tr>
                <th>{{ t('portal.ledger.time') }}</th>
                <th>{{ t('portal.ledger.reason') }}</th>
                <th class="text-end">{{ t('portal.ledger.change') }}</th>
                <th class="text-end">{{ t('portal.ledger.balance') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in items" :key="item.ledger_id">
                <td class="small text-body-secondary text-nowrap">{{ formatDate(item.created_at) }}</td>
                <td>
                  <div>{{ reasonLabel(item.reason) }}</div>
                  <div v-if="item.task_id" class="small text-body-secondary font-monospace">{{ item.task_id }}</div>
                </td>
                <td class="text-end fw-semibold" :class="item.delta >= 0 ? 'text-success' : 'text-danger'">
                  {{ item.delta > 0 ? '+' : '' }}{{ item.delta }} {{ t('portal.ledger.pageUnit') }}
                </td>
                <td class="text-end">{{ item.balance_after.toLocaleString() }} {{ t('portal.ledger.pageUnit') }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mt-3">
          <div class="small text-body-secondary">{{ t('portal.ledger.pagination', { total, page, totalPages }) }}</div>
          <div v-if="totalPages > 1" class="btn-group btn-group-sm">
            <button class="btn btn-outline-secondary" :disabled="page <= 1" @click="goToPage(page - 1)">{{ t('portal.ledger.previous') }}</button>
            <button class="btn btn-outline-secondary" :disabled="page >= totalPages" @click="goToPage(page + 1)">{{ t('portal.ledger.next') }}</button>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { apiFetch, ApiError } from '../lib/api'
import type { PortalQuotaLedgerItem, PortalQuotaLedgerPage } from '../types'

const { t } = useI18n()
const items = ref<PortalQuotaLedgerItem[]>([])
const page = ref(1)
const total = ref(0)
const totalPages = ref(0)
const loading = ref(false)
const error = ref('')

function reasonLabel(reason: string) {
  const labels: Record<string, string> = {
    task_reservation: 'portal.ledger.reasonReservation',
    task_settlement: 'portal.ledger.reasonSettlement',
    task_release: 'portal.ledger.reasonRelease',
    task_refund: 'portal.ledger.reasonRefund',
  }
  return labels[reason] ? t(labels[reason]) : reason.replace(/_/g, ' ')
}

function formatDate(value: string) {
  return new Date(value).toLocaleString()
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const result = await apiFetch<PortalQuotaLedgerPage>(`/api/portal/quota/ledger?page=${page.value}&size=20`)
    items.value = result.items
    total.value = result.total
    totalPages.value = Math.max(1, result.total_pages)
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('portal.ledger.loadFailed')
  } finally {
    loading.value = false
  }
}

function goToPage(nextPage: number) {
  page.value = nextPage
  void load()
}

onMounted(() => void load())
</script>
