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
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="applyFilters">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <label class="filter-item">
        <span>报告状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="item in statuses" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <button class="btn" type="submit" :disabled="loading">查询</button>
      <button class="btn ghost" type="button" :disabled="loading" @click="resetFilters">重置条件</button>
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
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              :disabled="acting"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无检测报告数据，可先登记检测报告</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条检测报告记录，第 {{ total === 0 ? 0 : page }} / {{ maxPage }} 页</span>
      <span class="pager">
        <button class="btn ghost" type="button" :disabled="loading || page <= 1" @click="goPage(page - 1)">上一页</button>
        <button class="btn ghost" type="button" :disabled="loading || page >= maxPage" @click="goPage(page + 1)">下一页</button>
      </span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type StatCard = { label: string; value: number }

const ENDPOINT = '/api/report'
const columns = ["报告编号", "委托单位", "样品名称", "报告类型", "编制人", "批准人", "签发日期", "报告状态"]
const actions = ["编制报告", "提交批准", "撤回报告"]
const statuses = ["待编制", "编制中", "待批准", "已签发", "已撤回"]
const PAGE_SIZE = 20

const rows = ref<Row[]>([])
const total = ref(0)
const page = ref(1)
const errorMessage = ref('')
const loading = ref(false)
const acting = ref(false)
const filters = ref<Record<string, string>>({})
const statusFilter = ref('')
const stats = ref<StatCard[]>([
  { label: '待编制报告', value: 0 },
  { label: '待批准报告', value: 0 },
  { label: '本月签发', value: 0 },
])
const filterFields = columns.slice(0, 4)

const maxPage = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))

// 单调递增的查询序号：快速连续操作时只采用最后一次响应，避免旧数据覆盖新数据
let requestSeq = 0

function buildQuery(withPage = true): string {
  const params = new URLSearchParams()
  for (const field of filterFields) {
    const value = (filters.value[field] ?? '').trim()
    if (value) {
      params.set(field, value)
    }
  }
  if (statusFilter.value) {
    params.set('status', statusFilter.value)
  }
  if (withPage) {
    params.set('page', String(page.value))
    params.set('size', String(PAGE_SIZE))
  }
  return params.toString()
}

function applyFilters() {
  page.value = 1
  void reload()
}

function resetFilters() {
  filters.value = {}
  statusFilter.value = ''
  page.value = 1
  void reload()
}

function goPage(target: number) {
  if (target < 1 || target > maxPage.value || target === page.value) {
    return
  }
  page.value = target
  void reload()
}

function exportRows() {
  // 导出与列表共用同一套筛选口径，只去掉分页参数
  window.open(`${ENDPOINT}/export?${buildQuery(false)}`, '_blank')
}

function openCreate() {
  errorMessage.value = '检测报告登记入口尚未接入审批流'
}

function readDetail(payload: unknown, fallback: string): string {
  if (payload && typeof payload === 'object') {
    const detail = (payload as { detail?: unknown }).detail
    if (typeof detail === 'string' && detail) {
      return detail
    }
    const message = (payload as { message?: unknown }).message
    if (typeof message === 'string' && message) {
      return message
    }
  }
  return fallback
}

async function runAction(action: string, row: Row) {
  if (acting.value) {
    return
  }
  errorMessage.value = ''
  acting.value = true
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload: unknown = await response.json().catch(() => null)
    if (!response.ok) {
      throw new Error(readDetail(payload, '检测报告动作未生效，请稍后重试'))
    }
    if (payload && typeof payload === 'object' && (payload as { ok?: boolean }).ok === false) {
      // 业务校验未通过同样按失败处理，不能把拒绝当成成功
      throw new Error(readDetail(payload, '检测报告动作未生效，请稍后重试'))
    }
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '检测报告操作失败'
  } finally {
    acting.value = false
  }
}

async function reload() {
  errorMessage.value = ''
  loading.value = true
  const seq = ++requestSeq
  try {
    const response = await request(`${ENDPOINT}?${buildQuery()}`)
    const payload: unknown = await response.json().catch(() => null)
    if (seq !== requestSeq) {
      return
    }
    if (!response.ok) {
      throw new Error(readDetail(payload, '检测报告列表读取失败'))
    }
    const data = payload as { items?: Row[]; total?: number }
    rows.value = data.items ?? []
    total.value = data.total ?? rows.value.length
    if (total.value > 0 && page.value > maxPage.value) {
      // 筛选或动作让结果变少时回到最后一页，不停留在空页上
      page.value = maxPage.value
      void reload()
    }
  } catch (error) {
    if (seq === requestSeq) {
      errorMessage.value = error instanceof Error ? error.message : '检测报告列表读取失败'
    }
  } finally {
    if (seq === requestSeq) {
      loading.value = false
    }
  }
}

async function loadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (!response.ok) {
      return
    }
    const payload = (await response.json()) as { cards?: StatCard[] }
    if (Array.isArray(payload.cards)) {
      stats.value = payload.cards
    }
  } catch {
    // 指标读取失败时保留旧值，不打断列表操作
  }
}

onMounted(() => {
  void reload()
  void loadStats()
})
</script>
