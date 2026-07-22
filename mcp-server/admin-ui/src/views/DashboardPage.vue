<template>
  <AdminLayout>
    <div class="card page-card">
      <div class="card-body">
        <h4 class="card-title">{{ t('dashboard.welcomeTitle') }}</h4>
        <p class="text-muted mb-0">{{ t('dashboard.welcomeSubtitle') }}</p>
      </div>
    </div>
  </AdminLayout>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import AdminLayout from '../layouts/AdminLayout.vue'

const { t } = useI18n()
</script>
