export function postprocessStatusLabel(status?: string | null) {
  switch (status) {
    case 'pending':
      return '待处理'
    case 'processing':
    case 'running':
      return '处理中'
    case 'completed':
      return '已完成'
    case 'failed':
      return '后处理失败'
    case 'cancelled':
      return '已取消'
    case 'skipped':
      return '未执行'
    case 'not_enabled':
      return '未启用'
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

export function triggerSourceLabel(source?: string | null) {
  switch (source) {
    case 'auto':
      return '自动'
    case 'manual':
      return '手动'
    default:
      return source || '-'
  }
}
