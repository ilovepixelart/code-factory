<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { RANGES, rangeOf, rangeQuery, type RangeKey } from '../lib/analytics'
import AnalyticsTabs from './AnalyticsTabs.vue'
import { Button } from '@/components/ui/button'
import { Alert, AlertAction, AlertTitle } from '@/components/ui/alert'
import { Spinner } from '@/components/ui/spinner'
import ReadState from './ReadState.vue'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'

// What every Analytics page shares, in one place on each: the header's switch between the pages,
// then a toolbar row with the range (or, on a page that reads no range, a line saying so, so
// nothing below moves between tabs) and the page's note at its right, then the states of its read.
// Until the first answer (`ready`) the page says it is reading or why it cannot; after it a later
// read shows `Reading` beside the range, and a read that failed shows its reason in a row, with
// Read again, above the figures it left.
const {
  page,
  what,
  ready,
  failed = '',
  busy,
  ranged,
  note = '',
  shown = null,
} = defineProps<{
  /** The address of the page showing, one of `ANALYTICS_TABS`. */
  page: string
  what: string
  ready: boolean
  failed?: string
  busy?: boolean
  ranged?: boolean
  /** A line about how to read the page's figures, at the toolbar's right. */
  note?: string
  /** The range the figures on the page were read for: a failed read of another range says so. */
  shown?: RangeKey | null
}>()
const emit = defineEmits<{ retry: [] }>()
defineSlots<{ default?: () => unknown }>()

const route = useRoute()
const range = computed(() => rangeOf(route.query.range))
const words = (key: RangeKey): string => RANGES.find(([k]) => k === key)?.[1] ?? key
const notice = computed(() =>
  ranged && shown !== null && shown !== range.value
    ? `${failed}; still showing the last ${words(shown)}`
    : failed,
)
</script>

<template>
  <AnalyticsTabs :page="page" :query="rangeQuery(range)" />
  <div class="page-wide grid grid-cols-1 gap-6">
    <div data-analytics-toolbar class="flex min-h-8 flex-wrap items-center gap-3">
      <nav v-if="ranged" aria-label="Range">
        <Tabs :model-value="range" activation-mode="manual">
          <TabsList>
            <TabsTrigger v-for="[key, label] in RANGES" :key="key" :value="key" as-child>
              <RouterLink
                :to="{ path: page, query: rangeQuery(key) }"
                :aria-current="range === key ? 'page' : undefined"
                >{{ label }}</RouterLink
              >
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </nav>
      <p v-else class="text-muted-foreground text-sm">Not limited to a range</p>
      <span
        v-if="ready && busy"
        class="flex items-center gap-2 text-sm text-muted-foreground"
        data-reading
        ><Spinner />Reading</span
      >
      <p v-if="note" class="wrap-anywhere text-muted-foreground ml-auto text-sm">{{ note }}</p>
    </div>
    <template v-if="ready">
      <Alert v-if="failed" variant="destructive" data-factory-notice>
        <AlertTitle>{{ notice }}</AlertTitle>
        <AlertAction>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            data-read-again
            @click="emit('retry')"
          >
            Read again
          </Button>
        </AlertAction>
      </Alert>
      <slot />
    </template>
    <!-- p-0: the frame already holds the page margin. -->
    <ReadState
      v-else
      class="p-0"
      shape="tiles"
      :what="what"
      :failed="failed"
      @retry="emit('retry')"
    />
  </div>
</template>
