<script setup lang="ts">
import { MoreHorizontalIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { inject, ref, watch } from 'vue'
import { STAGE_LABELS, type Stage } from '../lib/board'
import { act } from '../lib/actions'
import { BOARD } from '../lib/live'
import { perform } from '../lib/notice'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Field, FieldLabel } from '@/components/ui/field'
import {
  NumberField,
  NumberFieldContent,
  NumberFieldDecrement,
  NumberFieldIncrement,
  NumberFieldInput,
} from '@/components/ui/number-field'

// A column's menu: its work-in-progress limit.
const { stage, limit } = defineProps<{ stage: Stage; limit: number | undefined }>()
const live = inject(BOARD)
const open = ref(false)
const busy = ref(false)
// Which of the two buttons sent the change in flight, for its Spinner.
const clearing = ref(false)
// The number typed, or null while the field is empty. A number that is not whole goes as typed
// (no snapping to the step), for the board to judge.
const value = ref<number | null>(null)

watch(
  () => limit,
  (current) => {
    value.value = current ?? null
  },
  { immediate: true },
)

async function save(clear: boolean): Promise<void> {
  const wanted = clear || value.value === null || Number.isNaN(value.value) ? null : value.value
  busy.value = true
  clearing.value = clear
  const done = await perform(
    () => act('PUT', `/api/columns/${stage}/limit`, { limit: wanted }),
    live?.refresh ?? (() => Promise.resolve()),
  )
  busy.value = false
  if (done) open.value = false
}
</script>

<template>
  <Popover v-model:open="open">
    <PopoverTrigger as-child>
      <Button
        variant="ghost"
        size="icon-xs"
        class="shrink-0 group-data-[collapsed]/column:hidden"
        :aria-label="`Column menu for ${STAGE_LABELS[stage]}`"
      >
        <HugeiconsIcon :icon="MoreHorizontalIcon" aria-hidden="true" />
      </Button>
    </PopoverTrigger>
    <PopoverContent align="end" class="w-56">
      <form
        class="flex flex-col gap-2"
        :aria-label="`Limit for ${STAGE_LABELS[stage]}`"
        @submit.prevent="save(false)"
      >
        <Field>
          <FieldLabel :for="`limit-${stage}`">WIP limit</FieldLabel>
          <NumberField
            :id="`limit-${stage}`"
            :model-value="value"
            :min="1"
            :step-snapping="false"
            name="limit"
            @update:model-value="value = $event ?? null"
          >
            <NumberFieldContent>
              <NumberFieldDecrement />
              <NumberFieldInput placeholder="no limit" />
              <NumberFieldIncrement />
            </NumberFieldContent>
          </NumberField>
        </Field>
        <div class="flex gap-2">
          <Button type="submit" class="flex-1" :disabled="busy"
            ><Spinner v-if="busy && !clearing" data-icon="inline-start" />Set limit</Button
          >
          <Button type="button" variant="ghost" :disabled="busy" @click="save(true)">
            <Spinner v-if="busy && clearing" data-icon="inline-start" />Clear
          </Button>
        </div>
      </form>
    </PopoverContent>
  </Popover>
</template>
