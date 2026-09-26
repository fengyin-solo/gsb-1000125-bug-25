<template>
  <section class="page" data-module="report-detail">
    <header class="page-head">
      <div>
        <h2>检测报告详情</h2>
        <p class="page-desc">查看报告明细并执行与列表页一致的状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" :disabled="loading" @click="goBack">返回列表</button>
      </div>
    </header>

    <div v-if="entry" class="detail-card">
      <dl class="detail-grid">
        <div v-for="column in columns" :key="column">
          <dt>{{ column }}</dt>
          <dd>{{ entry[column] ?? '—' }}</dd>
        </div>
      </dl>

      <div class="detail-actions">
        <button
          v-for="action in actions"
          :key="action"
          class="btn"
          :class="{ primary: canAction(String(entry.status), action) }"
          type="button"
          :disabled="actionLoading || loading || !canAction(String(entry.status), action)"
          @click="runAction(action)"
        >
          {{ action }}
        </button>
      </div>
    </div>

    <div v-else-if="loading" class="detail-empty">正在读取检测报告详情…</div>
    <div v-else class="detail-empty error-text">{{ errorMessage || '检测报告不存在或已归档' }}</div>

    <footer class="page-foot">
      <span v-if="entry">报告编号：{{ String(entry['报告编号']) }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>
type ActionPayload = {
  ok?: boolean
  message?: string
  entry?: Row
}

const route = useRoute()
const router = useRouter()
const columns = ['报告编号', '委托单位', '样品名称', '报告类型', '编制人', '批准人', '签发日期', '报告状态']
const actions = ['编制报告', '提交批准', '签发报告', '撤回报告']
const actionRules: Record<string, string[]> = {
  待编制: ['编制报告'],
  编制中: ['提交批准'],
  待批准: ['签发报告'],
  已签发: ['撤回报告'],
  已撤回: [],
}

const entry = ref<Row | null>(null)
const loading = ref(false)
const actionLoading = ref(false)
const errorMessage = ref('')

function listQuery() {
  return { ...route.query }
}

function goBack() {
  void router.push({ path: '/report', query: listQuery() })
}

function canAction(statusValue: string, action: string) {
  return actionRules[statusValue]?.includes(action) ?? false
}

async function loadEntry() {
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await request(`/api/report/${String(route.params.id)}`)
    if (response.status === 404) {
      entry.value = null
      errorMessage.value = '检测报告不存在或已归档'
      return
    }
    if (!response.ok) {
      throw new Error('检测报告详情读取失败')
    }
    entry.value = (await response.json()) as Row
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '检测报告详情读取失败'
  } finally {
    loading.value = false
  }
}

async function runAction(action: string) {
  if (!entry.value || !canAction(String(entry.value.status), action) || actionLoading.value) return
  actionLoading.value = true
  errorMessage.value = ''
  try {
    const response = await request(`/api/report/${String(route.params.id)}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('检测报告动作未生效，请稍后重试')
    }
    const payload = (await response.json()) as ActionPayload
    if (!payload.ok) {
      throw new Error(payload.message || '检测报告操作失败')
    }
    entry.value = payload.entry ?? null
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '检测报告操作失败'
  } finally {
    actionLoading.value = false
  }
}

onMounted(loadEntry)
</script>
