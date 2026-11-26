<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, type RouteLocationRaw } from 'vue-router'
import { Button } from '@/components/ui/button'
import { lastPage, linkTo, rangeText } from '../../lib/paging'

// The footer of shadcn-vue's Data Table example under a table's bordered box: how many of its
// rows are chosen on the left, the range and Previous and Next on the right. Each page is a link
// (CF-1191), so a copied link and Back return to it; at either end the button is disabled. Nothing
// shows while no row can be chosen and every row fits one page.
const { chosen, rows, pages, prefix } = defineProps<{
  /** The chosen rows of the table, or null when its rows cannot be chosen. */
  chosen: number | null
  /** The rows the table holds, its filter applied. */
  rows: number
  /** The table's pages, or null when it does not page. */
  pages: { label: string; total: number; page: number; size: number; fallback: number } | null
  prefix: string
}>()

const route = useRoute()
const last = computed(() => (pages ? lastPage(pages.total, pages.size) : 1))
const paging = computed(() => Boolean(pages && (last.value > 1 || pages.page > 1)))
const pageLink = (n: number): RouteLocationRaw => ({
  path: route.path,
  query: pages ? linkTo(route.query, prefix, n, pages.size, pages.fallback) : route.query,
})
const range = computed(() => (pages ? rangeText(pages.page, pages.size, pages.total) : ''))
</script>

<template>
  <nav
    v-if="chosen !== null || paging"
    data-slot="data-table-footer"
    :aria-label="pages && paging ? `Pages of ${pages.label}` : undefined"
    class="flex items-center justify-end gap-2"
  >
    <p class="flex-1 text-sm text-muted-foreground tabular-nums">
      <template v-if="chosen !== null">{{ chosen }} of {{ rows }} row(s) selected.</template>
      <span v-else-if="paging" data-testid="page-range">{{ range }}</span>
    </p>
    <template v-if="pages && paging">
      <span
        v-if="chosen !== null"
        data-testid="page-range"
        class="text-sm text-muted-foreground tabular-nums"
        >{{ range }}</span
      >
      <Button v-if="pages.page > 1" key="previous-link" variant="outline" size="sm" as-child
        ><RouterLink :to="pageLink(pages.page - 1)" rel="prev">Previous</RouterLink></Button
      >
      <Button v-else key="previous" type="button" variant="outline" size="sm" disabled
        >Previous</Button
      >
      <Button v-if="pages.page < last" key="next-link" variant="outline" size="sm" as-child
        ><RouterLink :to="pageLink(pages.page + 1)" rel="next">Next</RouterLink></Button
      >
      <Button v-else key="next" type="button" variant="outline" size="sm" disabled>Next</Button>
    </template>
  </nav>
</template>
