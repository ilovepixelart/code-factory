<script setup lang="ts">
import { computed } from 'vue'
import { ESTIMATE_NOTE, cost } from '../../lib/format'
import { prs, sizeLabel, type Cost } from '../../lib/factory'
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { AMOUNT, FRAME, HEAD, TEXT } from '../data-table/look'

// Cost per pull request two ways, side by side from `lg`: by the stage of the run that spent it
// and by the size of the pull request; and how many pull requests have no cost at all.
const { costs } = defineProps<{ costs: Cost }>()

const COMPONENTS = { spec: 'Spec', build: 'Build', review: 'Review', other: 'Other' } as const
const money = (value: number): string => cost(value, costs.estimated)
const note = computed(() => (costs.estimated ? ESTIMATE_NOTE : undefined))
const unpriced = (): string => {
  const n = costs.of - costs.priced
  return `${prs(n)} ${n === 1 ? 'has' : 'have'} no recorded cost`
}
</script>

<template>
  <div class="grid grid-cols-1 gap-3 lg:grid-cols-2">
    <div :class="FRAME">
      <Table :class="TEXT">
        <TableCaption class="sr-only">Cost per pull request by component</TableCaption>
        <TableHeader :class="HEAD">
          <TableRow>
            <TableHead>Component</TableHead>
            <TableHead :class="AMOUNT.head">Median</TableHead>
            <TableHead :class="AMOUNT.head">Total</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-for="row in costs.by_component" :key="row.component">
            <TableCell class="whitespace-nowrap">{{ COMPONENTS[row.component] }}</TableCell>
            <TableCell :class="AMOUNT.cell" :title="note"
              ><span v-if="row.median === null" class="font-normal text-muted-foreground"
                >No data</span
              ><template v-else>{{ money(row.median) }}</template></TableCell
            >
            <TableCell :class="AMOUNT.cell" :title="note"
              ><span v-if="row.total === null" class="font-normal text-muted-foreground"
                >No data</span
              ><template v-else>{{ money(row.total) }}</template></TableCell
            >
          </TableRow>
        </TableBody>
      </Table>
    </div>
    <div :class="FRAME">
      <Table :class="TEXT">
        <TableCaption class="sr-only">Cost per pull request by size</TableCaption>
        <TableHeader :class="HEAD">
          <TableRow>
            <TableHead>Size</TableHead>
            <TableHead :class="AMOUNT.head">Median</TableHead>
            <TableHead :class="AMOUNT.head">Pull requests priced</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-for="row in costs.by_size" :key="row.size">
            <TableCell class="whitespace-nowrap">{{ sizeLabel(row.size) }}</TableCell>
            <TableCell :class="AMOUNT.cell" :title="note"
              ><span
                v-if="!row.priced || row.median === null"
                class="font-normal text-muted-foreground"
                >No data</span
              ><template v-else>{{ money(row.median) }}</template></TableCell
            >
            <TableCell :class="AMOUNT.cell">{{ row.priced }} of {{ row.of }}</TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>
  </div>
  <p v-if="costs.of > costs.priced" data-unpriced class="text-sm text-muted-foreground">
    {{ unpriced() }}
  </p>
</template>
