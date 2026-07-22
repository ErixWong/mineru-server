import { i18n } from '../i18n'

export function postprocessStatusLabel(status?: string | null): string {
  switch (status) {
    case 'pending':
      return i18n.global.t('status.pending')
    case 'processing':
    case 'running':
      return i18n.global.t('status.processing')
    case 'completed':
      return i18n.global.t('status.completed')
    case 'failed':
      return i18n.global.t('status.postprocessFailed')
    case 'cancelled':
      return i18n.global.t('status.cancelled')
    case 'skipped':
      return i18n.global.t('status.skipped')
    case 'not_enabled':
      return i18n.global.t('status.notEnabled')
    default:
      return status || '-'
  }
}

export function postprocessBadgeClass(status?: string | null) {
  switch (status) {
    case 'completed':
      return 'text-bg-success'
    case 'failed':
      return 'text-bg-danger'
    case 'processing':
    case 'running':
      return 'text-bg-primary'
    case 'cancelled':
      return 'text-bg-dark'
    case 'skipped':
      return 'text-bg-dark'
    default:
      return 'text-bg-secondary'
  }
}

export function triggerSourceLabel(source?: string | null): string {
  switch (source) {
    case 'auto':
      return i18n.global.t('trigger.auto')
    case 'manual':
      return i18n.global.t('trigger.manual')
    default:
      return source || '-'
  }
}
