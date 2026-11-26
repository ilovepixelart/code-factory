<script setup lang="ts">
import { computed } from 'vue'
import SectionCard from './SectionCard.vue'
import { asked, rate, type Scorer } from '../lib/scorers'
import { ticketHref } from '../lib/ticket'
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { AMOUNT, FRAME, HEAD, TEXT } from './data-table/look'

// The yes or no questions the judge asks of sampled sessions (CF-1303), each with how often it
// was asked and how often the answer was the wanted one, and the open ticket its failures filed.
// The repository is a column only while the scorers come from more than one.
const { scorers } = defineProps<{ scorers: Scorer[] }>()
const several = computed(() => new Set(scorers.map((s) => s.repository)).size > 1)
</script>

<template>
  <SectionCard
    heading="scorers-heading"
    title="Scorers"
    :count="scorers.length"
    description="a pass rate is yes over yes and no"
  >
    <div :class="FRAME">
      <Table :class="TEXT">
        <TableCaption class="sr-only">Scorers</TableCaption>
        <TableHeader :class="HEAD">
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead v-if="several">Repository</TableHead>
            <TableHead>Question</TableHead>
            <TableHead :class="AMOUNT.head">Asked, 30 days</TableHead>
            <TableHead :class="AMOUNT.head">Pass rate, 7 days</TableHead>
            <TableHead :class="AMOUNT.head">Pass rate, 30 days</TableHead>
            <TableHead>Open ticket</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-for="s in scorers" :key="`${s.repository}/${s.name}`" data-scorer>
            <TableCell class="font-mono whitespace-nowrap font-medium">{{ s.name }}</TableCell>
            <TableCell
              v-if="several"
              class="whitespace-nowrap text-muted-foreground"
              data-repository
              >{{ s.repository }}</TableCell
            >
            <TableCell class="whitespace-normal wrap-anywhere min-w-56">{{ s.question }}</TableCell>
            <TableCell :class="AMOUNT.cell" data-asked>{{ asked(s.month) }}</TableCell>
            <TableCell :class="AMOUNT.cell" data-week>{{ rate(s.week) }}</TableCell>
            <TableCell :class="AMOUNT.cell" data-month>{{ rate(s.month) }}</TableCell>
            <TableCell class="whitespace-nowrap">
              <RouterLink
                v-if="s.ticket"
                :to="ticketHref(s.repository, s.ticket)"
                class="font-mono hover:underline"
                >{{ s.ticket }}</RouterLink
              >
              <span v-else class="text-muted-foreground">none</span>
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>
  </SectionCard>
</template>
