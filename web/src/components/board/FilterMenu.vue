<script setup lang="ts">
import { sentence } from '../../lib/format'
import {
  BotIcon,
  Cancel01Icon,
  FilterIcon,
  HelpCircleIcon,
  Tick02Icon,
  UnavailableIcon,
} from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { computed } from 'vue'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import type { FilterGroup } from '../../lib/board'
import { useLabelColor } from '../../lib/labels'
import ColorDot from '../ColorDot.vue'
import { filterCount, type Pairs } from '../../lib/view'
import SavedViews from './SavedViews.vue'
import { Badge } from '@/components/ui/badge'

// The board's filters: every choice is a link, so the address holds them. Saved views hold a form,
// so they open beside the menu in their own popover.
const props = defineProps<{
  query: Pairs
  options: Partial<Record<FilterGroup, string[]>>
  toggleUrl: (key: string, value: string) => string
  clearUrl: string
}>()

const GROUP_TITLES: Record<FilterGroup, string> = {
  type: 'Type',
  priority: 'Priority',
  label: 'Label',
  assignee: 'Assignee',
  repository: 'Repository',
}
const FLAGS = [
  ['blocked', 'Blocked', UnavailableIcon],
  ['questions', 'Waiting on an answer', HelpCircleIcon],
  ['agent', 'Agent running', BotIcon],
] as const
const count = computed(() => filterCount(props.query))
const groups = computed(() =>
  (Object.entries(props.options) as [FilterGroup, string[]][]).filter(
    ([, values]) => values.length,
  ),
)
const has = (key: string, value: string) => props.query.some(([k, v]) => k === key && v === value)
const chosen = (group: string) => props.query.filter(([k]) => k === group).length
const labelColor = useLabelColor()
</script>

<template>
  <SavedViews />
  <DropdownMenu>
    <DropdownMenuTrigger as-child>
      <Button variant="ghost" class="relative gap-1.5" :data-filter-count="count">
        <HugeiconsIcon :icon="FilterIcon" data-icon="inline-start" aria-hidden="true" /><span
          class="max-sm:sr-only"
          >Filter</span
        >
        <Badge v-if="count" class="absolute -top-1.5 -right-1.5">{{ count }}</Badge>
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end" class="w-60" aria-label="Filters">
      <DropdownMenuGroup>
        <DropdownMenuItem v-for="[key, title, glyph] in FLAGS" :key="key" as-child>
          <RouterLink :to="toggleUrl(key, '1')" :aria-current="has(key, '1') ? 'true' : undefined"
            ><HugeiconsIcon :icon="has(key, '1') ? Tick02Icon : glyph" aria-hidden="true" />{{
              title
            }}</RouterLink
          >
        </DropdownMenuItem>
      </DropdownMenuGroup>
      <DropdownMenuGroup v-if="groups.length">
        <DropdownMenuSub v-for="[group, values] in groups" :key="group">
          <DropdownMenuSubTrigger>
            {{ GROUP_TITLES[group] }}<Badge v-if="chosen(group)">{{ chosen(group) }}</Badge>
          </DropdownMenuSubTrigger>
          <DropdownMenuSubContent class="max-h-[70vh] overflow-y-auto">
            <DropdownMenuGroup>
              <DropdownMenuItem v-for="value in values" :key="value" as-child>
                <RouterLink
                  :to="toggleUrl(group, value)"
                  :aria-current="has(group, value) ? 'true' : undefined"
                  ><ColorDot v-if="group === 'label'" :color="labelColor(value)" />{{
                    group === 'type' || group === 'priority' ? sentence(value) : value
                  }}<HugeiconsIcon
                    v-if="has(group, value)"
                    :icon="Tick02Icon"
                    class="ml-auto"
                    aria-hidden="true"
                /></RouterLink>
              </DropdownMenuItem>
            </DropdownMenuGroup>
          </DropdownMenuSubContent>
        </DropdownMenuSub>
      </DropdownMenuGroup>
      <template v-if="count">
        <DropdownMenuSeparator />
        <DropdownMenuGroup>
          <DropdownMenuItem as-child>
            <RouterLink :to="clearUrl"
              ><HugeiconsIcon :icon="Cancel01Icon" aria-hidden="true" />Clear filters</RouterLink
            >
          </DropdownMenuItem>
        </DropdownMenuGroup>
      </template>
    </DropdownMenuContent>
  </DropdownMenu>
</template>
