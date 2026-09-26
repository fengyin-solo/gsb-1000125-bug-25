<template>
  <section class="page" data-module="report">
    <header class="page-head">
      <div>
        <h2>检测报告管理</h2>
        <p class="page-desc">维护检测报告，围绕报告编号、委托单位、样品名称、报告类型做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记检测报告</button>
        <button class="btn" type="button" @click="exportRows">导出检测报告清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in statCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="submitFilters">
      <label v-for="field in filterFields" :key="field.key" class="filter-item">
        <span>{{ field.label }}</span>
        <input v-model="filters[field.key]" :placeholder="`按${field.label}检索`" />
      </label>
      <label class="filter-item">
        <span>报告状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit" :disabled="listLoading || !canSubmitFilters">查询</button>
      <button class="btn ghost" type="button" :disabled="listLoading" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">详情</button>
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              :disabled="actionLoading || !canAction(row.status, action)"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无符合条件的检测报告，请调整筛选条件或登记检测报告</td>
        </tr>
      </tbody>
    </table>

    <div class="pagination">
      <button class="btn" type="button" :disabled="listLoading || page <= 1" @click="goPage(page - 1)">上一页</button>
      <span>第 {{ page }} / {{ totalPages }} 页</span>
      <button class="btn" type="button" :disabled="listLoading || page >= totalPages" @click="goPage(page + 1)">下一页</button>
      <label>
        每页
        <select v-model.number="size" :disabled="listLoading" @change="changePageSize">
          <option :value="2">2</option>
          <option :value="10">10</option>
          <option :value="20">20</option>
        </select>
        条
      </label>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 条检测报告记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>
type FilterKey = 'reportNo' | 'client' | 'sampleName' | 'reportType'
type ListPayload = {
  items?: Row[]
  total?: number
  page?: number
  size?: number
  stats?: Partial<Record<string, number>>
}
type ActionPayload = {
  ok?: boolean
  message?: string
  entry?: Row
}

const ENDPOINT = '/api/report'
const columns = ['报告编号', '委托单位', '样品名称', '报告类型', '编制人', '批准人', '签发日期', '报告状态']
const actions = ['编制报告', '提交批准', '签发报告', '撤回报告']
const statuses = ['待编制', '编制中', '待批准', '已签发', '已撤回']
const actionRules: Record<string, string[]> = {
  待编制: ['编制报告'],
  编制中: ['提交批准'],
  待批准: ['签发报告'],
  已签发: ['撤回报告'],
  已撤回: [],
}
const filterFields: Array<{ key: FilterKey; label: string }> = [
  { key: 'reportNo', label: '报告编号' },
  { key: 'client', label: '委托单位' },
  { key: 'sampleName', label: '样品名称' },
  { key: 'reportType', label: '报告类型' },
]

const route = useRoute()
const router = useRouter()
const rows = ref<Row[]>([])
const total = ref(0)
const page = ref(1)
const size = ref(10)
const stats = ref<Partial<Record<string, number>>>({})
const errorMessage = ref('')
const listLoading = ref(false)
const actionLoading = ref(false)
const statusFilter = ref('')
const filters = ref<Record<FilterKey, string>>({
  reportNo: '',
  client: '',
  sampleName: '',
  reportType: '',
})

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / size.value)))
const canSubmitFilters = computed(() => statusFilter.value === '' || statuses.includes(statusFilter.value))
const statCards = computed(() => [
  { label: '待编制报告', value: stats.value['待编制报告'] ?? 0 },
  { label: '待批准报告', value: stats.value['待批准报告'] ?? 0 },
  { label: '本月签发', value: stats.value['本月签发'] ?? 0 },
])

function readInitialQuery() {
  const queryPage = Number(route.query.page)
  const querySize = Number(route.query.size)
  if (Number.isInteger(queryPage) && queryPage > 0) page.value = queryPage
  if ([2, 10, 20].includes(querySize)) size.value = querySize
  const queryStatus = typeof route.query.status === 'string' ? route.query.status : ''
  statusFilter.value = statuses.includes(queryStatus) ? queryStatus : ''
  for (const field of filterFields) {
    const value = route.query[field.key]
    filters.value[field.key] = typeof value === 'string' ? value : ''
  }
}

function currentQuery(includePage = true) {
  const query: Record<string, string> = {}
  for (const field of filterFields) {
    const value = filters.value[field.key].trim()
    if (value) query[field.key] = value
  }
  if (statusFilter.value) query.status = statusFilter.value
  if (includePage) {
    query.page = String(page.value)
    query.size = String(size.value)
  }
  return query
}

let listController: AbortController | null = null
let listRequestId = 0

async function reload(syncUrl = true) {
  listController?.abort()
  const controller = new AbortController()
  const requestId = ++listRequestId
  listController = controller
  listLoading.value = true
  errorMessage.value = ''

  const query = new URLSearchParams(currentQuery()).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`, { signal: controller.signal })
    if (!response.ok) {
      throw new Error('检测报告列表读取失败')
    }
    const payload = (await response.json()) as ListPayload
    if (requestId !== listRequestId) return
    rows.value = payload.items ?? []
    total.value = payload.total ?? 0
    page.value = payload.page ?? page.value
    size.value = payload.size ?? size.value
    stats.value = payload.stats ?? {}
    if (syncUrl) {
      await router.replace({ query: currentQuery() })
    }
  } catch (error) {
    if (requestId !== listRequestId || (error instanceof DOMException && error.name === 'AbortError')) return
    errorMessage.value = error instanceof Error ? error.message : '检测报告列表读取失败'
  } finally {
    if (requestId === listRequestId) {
      listLoading.value = false
      listController = null
    }
  }
}

async function submitFilters() {
  page.value = 1
  await reload()
}

async function resetFilters() {
  filters.value = { reportNo: '', client: '', sampleName: '', reportType: '' }
  statusFilter.value = ''
  page.value = 1
  await reload()
}

async function goPage(nextPage: number) {
  page.value = nextPage
  await reload()
}

async function changePageSize() {
  page.value = 1
  await reload()
}

function exportRows() {
  const query = new URLSearchParams(currentQuery(false)).toString()
  window.open(`${ENDPOINT}/export${query ? `?${query}` : ''}`, '_blank')
}

function openCreate() {
  errorMessage.value = '检测报告登记入口尚未接入审批流'
}

function openDetail(row: Row) {
  void router.push({ path: `${ENDPOINT}/${String(row.id)}`, query: currentQuery() })
}

function canAction(statusValue: Row['status'], action: string) {
  return actionRules[String(statusValue)]?.includes(action) ?? false
}

async function runAction(action: string, row: Row) {
  if (!canAction(row.status, action) || actionLoading.value) return
  actionLoading.value = true
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${String(row.id)}/actions`, {
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
    await reload(false)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '检测报告操作失败'
  } finally {
    actionLoading.value = false
  }
}

onMounted(() => {
  readInitialQuery()
  void reload(false)
})
</script>
