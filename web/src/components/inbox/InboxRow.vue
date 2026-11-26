<script setup lang="ts">
import ContentCard from '../ContentCard.vue'
import type { InboxItem } from '../../lib/metrics'
import InboxAge from './InboxAge.vue'
import InboxTicketLink from './InboxTicketLink.vue'
import { FieldError } from '@/components/ui/field'
import { cn } from '@/lib/utils'
import { Item, ItemActions, ItemContent, ItemFooter, ItemHeader } from '@/components/ui/item'

// An Inbox row in Item's parts: its header is the lead and the age, or, without a lead, the ticket
// with the age and the actions at the right; the default slot is its content, an error its footer.
const {
  item,
  now,
  error = '',
  wrap,
  id = '',
} = defineProps<{
  item: InboxItem
  now: number
  error?: string
  /** The row's element id, which a push link names after `#` (CF-627). */
  id?: string
  /** Whether the line's actions wrap. */
  wrap?: boolean
}>()
defineSlots<{ lead?: () => unknown; default?: () => unknown; actions?: () => unknown }>()
</script>

<template>
  <ContentCard :id="id || undefined" role="listitem">
    <Item class="py-3">
      <ItemHeader v-if="$slots.lead" key="lead" class="min-w-0 max-sm:flex-wrap">
        <slot name="lead" />
        <InboxAge :since="item.since" :now="now" />
      </ItemHeader>
      <ItemHeader v-else key="line" class="min-w-0 max-sm:flex-wrap">
        <InboxTicketLink
          :item="item"
          class="max-sm:basis-full max-sm:whitespace-normal max-sm:wrap-anywhere"
        />
        <ItemActions class="min-w-0 max-sm:flex-wrap" :class="cn(wrap && 'flex-wrap')">
          <InboxAge :since="item.since" :now="now" />
          <slot name="actions" />
        </ItemActions>
      </ItemHeader>
      <ItemContent v-if="$slots.default" class="min-w-0"><slot /></ItemContent>
      <ItemFooter v-if="error"
        ><FieldError>{{ error }}</FieldError></ItemFooter
      >
    </Item>
  </ContentCard>
</template>
