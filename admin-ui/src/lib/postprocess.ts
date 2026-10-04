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
      return 'bg-success-subtle text-success-emphasis'
    case 'failed':
      return 'bg-danger-subtle text-danger-emphasis'
    case 'processing':
    case 'running':
      return 'bg-primary-subtle text-primary-emphasis'
    case 'cancelled':
    case 'skipped':
      return 'bg-secondary-subtle text-secondary-emphasis'
    default:
      return 'bg-secondary-subtle text-secondary-emphasis'
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
