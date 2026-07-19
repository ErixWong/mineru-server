export function postprocessStatusLabel(status?: string | null) {
  switch (status) {
    case 'pending':
      return '待处理'
    case 'processing':
      return '处理中'
    case 'completed':
      return '已完成'
    case 'failed':
      return '后处理失败'
    case 'skipped':
      return '未执行（解析阶段失败）'
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
      return 'text-bg-primary'
    case 'skipped':
      return 'text-bg-dark'
    default:
      return 'text-bg-secondary'
  }
}
