<script setup lang="ts">
import { sentence } from '../lib/format'
import {
  Archive02Icon,
  ArrowRight02Icon,
  Cancel01Icon,
  UnfoldMoreIcon,
} from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { inject, ref } from 'vue'
import { act } from '../lib/actions'
import { PRIORITIES, STAGE_LABELS, STAGES } from '../lib/board'
import { BOARD } from '../lib/live'
import { perform } from '../lib/notice'
import { chosen, clearSelection } from '../lib/selection'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { usePressed } from '../lib/pressed'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ButtonGroup, ButtonGroupText } from '@/components/ui/button-group'
import { Input } from '@/components/ui/input'

// The bulk bar: one change for every chosen card,
// all or nothing; the selection empties once it is done.
const live = inject(BOARD)
const busy = ref(false)
const { press, spins } = usePressed()
const label = ref('')

async function apply(change: Record<string, string>): Promise<void> {
  busy.value = true
  const done = await perform(
    () => act('POST', '/api/tickets/bulk', { tickets: [...chosen], ...change }),
    live?.refresh ?? (() => Promise.resolve()),
  )
  busy.value = false
  if (done) {
    clearSelection()
    label.value = ''
  }
}

function addLabel(): void {
  if (label.value.trim()) void apply({ label: label.value })
}
</script>

<template>
  <div
    id="bulk-bar"
    data-holds-bottom
    role="toolbar"
    aria-label="Bulk actions"
    class="fixed inset-x-3 bottom-6 z-40 flex flex-wrap items-center gap-2 rounded-lg border bg-background p-1.5 shadow-lg md:inset-x-auto md:left-1/2 md:-translate-x-1/2 md:flex-nowrap"
  >
    <ButtonGroup>
      <ButtonGroupText class="tabular-nums">{{ chosen.size }} selected</ButtonGroupText>
    </ButtonGroup>
    <ButtonGroup aria-label="Change the selected tickets">
      <DropdownMenu>
        <DropdownMenuTrigger as-child>
          <Button variant="outline" class="gap-1.5">
            <HugeiconsIcon
              :icon="ArrowRight02Icon"
              data-icon="inline-start"
              aria-hidden="true"
            />Move to
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent side="top" class="w-44" aria-label="Move selected to">
          <DropdownMenuGroup>
            <DropdownMenuItem
              v-for="s in STAGES"
              :key="s"
              :disabled="busy"
              @select="apply({ stage: s })"
            >
              {{ STAGE_LABELS[s] }}
            </DropdownMenuItem>
          </DropdownMenuGroup>
        </DropdownMenuContent>
      </DropdownMenu>
      <DropdownMenu>
        <DropdownMenuTrigger as-child>
          <Button variant="outline" class="gap-1.5">
            <HugeiconsIcon
              :icon="UnfoldMoreIcon"
              data-icon="inline-start"
              aria-hidden="true"
            />Priority
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent side="top" class="w-40" aria-label="Set priority of selected">
          <DropdownMenuGroup>
            <DropdownMenuItem
              v-for="p in PRIORITIES"
              :key="p"
              :disabled="busy"
              @select="apply({ priority: p })"
              >{{ sentence(p) }}</DropdownMenuItem
            >
          </DropdownMenuGroup>
        </DropdownMenuContent>
      </DropdownMenu>
      <Button
        type="button"
        variant="outline"
        class="gap-1.5"
        :disabled="busy"
        @click="press('archive', () => apply({ archived: 'true' }))"
      >
        <Spinner v-if="spins('archive', busy)" data-icon="inline-start" />
        <HugeiconsIcon
          v-else
          :icon="Archive02Icon"
          data-icon="inline-start"
          aria-hidden="true"
        />Archive
      </Button>
    </ButtonGroup>
    <form class="flex items-center gap-1" @submit.prevent="addLabel()">
      <Input
        :model-value="label"
        class="w-32"
        name="label"
        required
        aria-label="Add label to selected"
        placeholder="Add label"
        :disabled="busy"
        @update:model-value="label = String($event)"
      />
    </form>
    <Button
      type="button"
      variant="ghost"
      size="icon"
      aria-label="Clear selection"
      @click="clearSelection()"
    >
      <HugeiconsIcon :icon="Cancel01Icon" aria-hidden="true" />
    </Button>
  </div>
</template>
