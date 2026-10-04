<template>
  <section>
    <div class="mb-4">
      <div class="small text-uppercase text-body-secondary fw-semibold mb-1">个人空间</div>
      <h1 class="fs-3 fw-semibold mb-1">额度明细</h1>
      <p class="text-body-secondary mb-0">查看每次充值、解析扣减和额度返还记录。</p>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>
    <div class="card">
      <div class="card-body">
        <div v-if="loading" class="text-center text-body-secondary py-5">正在加载额度明细…</div>
        <div v-else-if="!items.length" class="text-center text-body-secondary py-5">
          <i class="bi bi-journal-text display-6 d-block mb-2"></i>还没有额度变动记录。
        </div>
        <div v-else class="table-responsive">
          <table class="table table-hover align-middle mb-0">
            <thead>
              <tr>
                <th>时间</th>
                <th>说明</th>
                <th class="text-end">变动</th>
                <th class="text-end">变动后余额</th>
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
                  {{ item.delta > 0 ? '+' : '' }}{{ item.delta }} 页
                </td>
                <td class="text-end">{{ item.balance_after.toLocaleString() }} 页</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mt-3">
          <div class="small text-body-secondary">共 {{ total }} 条记录，第 {{ page }} / {{ totalPages }} 页</div>
          <div v-if="totalPages > 1" class="btn-group btn-group-sm">
            <button class="btn btn-outline-secondary" :disabled="page <= 1" @click="goToPage(page - 1)">上一页</button>
            <button class="btn btn-outline-secondary" :disabled="page >= totalPages" @click="goToPage(page + 1)">下一页</button>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { apiFetch, ApiError } from '../lib/api'
import type { PortalQuotaLedgerItem, PortalQuotaLedgerPage } from '../types'

const items = ref<PortalQuotaLedgerItem[]>([])
const page = ref(1)
const total = ref(0)
const totalPages = ref(0)
const loading = ref(false)
const error = ref('')

function reasonLabel(reason: string) {
  const labels: Record<string, string> = {
    task_reservation: '解析任务预扣',
    task_settlement: '解析完成结算',
    task_release: '任务取消或失败，额度已返还',
    task_refund: '任务额度返还',
  }
  return labels[reason] || reason.replace(/_/g, ' ')
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
    error.value = err instanceof ApiError ? err.message : '暂时无法加载额度明细，请稍后重试。'
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
