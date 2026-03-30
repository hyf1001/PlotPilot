<template>
  <n-card v-if="status" class="job-status-indicator">
    <div class="job-header">
      <n-spin size="small" />
      <span class="job-type">{{ jobTypeLabel }}</span>
    </div>
    <div class="job-message">{{ status.message }}</div>
    <n-progress
      v-if="status.phase && !status.done"
      type="line"
      :percentage="calculateProgress()"
      :show-indicator="true"
    />
    <n-button
      v-if="!status.done"
      size="small"
      @click="handleCancel"
      aria-label="取消任务"
    >
      取消
    </n-button>
  </n-card>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { NCard, NProgress, NButton, NSpin } from 'naive-ui'
import { jobApi } from '@/api/book'
import type { JobStatusResponse } from '@/types/api'

interface Props {
  jobId: string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  completed: [status: JobStatusResponse]
}>()

const status = ref<JobStatusResponse | null>(null)
let pollInterval: number | null = null

const jobTypeLabel = computed(() => {
  if (!status.value) return ''
  const labels: Record<string, string> = {
    plan: '规划中',
    write: '写作中',
    run: '执行中'
  }
  return labels[status.value.kind] || status.value.kind
})

const calculateProgress = (): number => {
  if (!status.value) return 0
  // Simple progress calculation based on status
  if (status.value.status === 'queued') return 10
  if (status.value.status === 'running') return 50
  if (status.value.status === 'done') return 100
  return 0
}

const pollStatus = async () => {
  try {
    const result = await jobApi.getStatus(props.jobId)
    status.value = result

    if (result.done) {
      stopPolling()
      emit('completed', result)
    }
  } catch (error) {
    console.error('Failed to poll job status:', error)
    // Continue polling even on error - the job might still be running
  }
}

const stopPolling = () => {
  if (pollInterval) {
    clearInterval(pollInterval)
    pollInterval = null
  }
}

const handleCancel = async () => {
  if (!props.jobId) return

  try {
    await jobApi.cancelJob(props.jobId)
    stopPolling()
  } catch (error) {
    console.error('Failed to cancel job:', error)
  }
}

onMounted(() => {
  pollStatus()
  pollInterval = window.setInterval(pollStatus, 3000)
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped>
.job-status-indicator {
  margin-bottom: 16px;
}

.job-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.job-type {
  font-weight: 600;
  color: #667eea;
}

.job-message {
  margin-bottom: 12px;
  color: #666;
  font-size: 14px;
}
</style>
