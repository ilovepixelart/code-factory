<script setup lang="ts">
import ContentCard from './ContentCard.vue'
import { InformationCircleIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'

// A page's section, in the one order every page uses (docs/design.md, Page anatomy), flat on the
// inset panel: a heading row with the title, the list's count and the section's own action, then
// the section's toolbar (what narrows its list), its Empty while `empty` holds, and what the
// section holds. The description is not a line of its own: an info mark beside the title shows it
// on hover, and a screen reader hears it as the section's description; the mark adds no tab stop.
const {
  heading,
  title,
  count = null,
  description = '',
  empty,
} = defineProps<{
  /** The heading's id, which names the section. */
  heading: string
  title: string
  /** The number of rows when the section is a list, or "n of m" while a filter narrows it. */
  count?: number | string | null
  description?: string
  /** Whether the section shows its `empty` slot, at the top of its content. */
  empty?: boolean
}>()
defineSlots<{
  default?: () => unknown
  action?: () => unknown
  /** What narrows the list, such as its filter: above the Empty, so it stays where it was. */
  toolbar?: () => unknown
  empty?: () => unknown
  /** Words the title carries after its count, such as a hint for a screen reader. */
  title?: () => unknown
}>()
</script>

<template>
  <section
    :aria-labelledby="heading"
    :aria-describedby="description ? `${heading}-about` : undefined"
    data-section
    class="flex min-w-0 flex-col gap-4 [[data-section]+&]:pt-3"
  >
    <div data-section-head class="flex min-h-7 items-center gap-3">
      <h2
        :id="heading"
        data-slot="section-title"
        class="cn-font-heading flex min-w-0 flex-1 items-center gap-2 text-base font-medium"
      >
        {{ title
        }}<template v-if="count !== null"
          ><span class="sr-only">, </span
          ><span data-section-count class="font-normal text-muted-foreground tabular-nums">{{
            count
          }}</span></template
        ><slot name="title" />
        <span
          v-if="description"
          data-section-about
          :title="description"
          aria-hidden="true"
          class="inline-flex text-muted-foreground"
          ><HugeiconsIcon :icon="InformationCircleIcon" class="size-3.5"
        /></span>
      </h2>
      <p
        v-if="description"
        :id="`${heading}-about`"
        data-slot="section-description"
        class="sr-only"
      >
        {{ description }}
      </p>
      <div v-if="$slots.action" data-slot="section-action" class="shrink-0">
        <slot name="action" />
      </div>
    </div>
    <div data-section-body data-slot="section-content" class="min-w-0">
      <div v-if="$slots.toolbar" class="mb-3"><slot name="toolbar" /></div>
      <ContentCard
        v-if="empty"
        data-section-empty
        class="*:data-[slot=empty]:px-5 *:data-[slot=empty]:py-8 **:data-[slot=empty-icon]:mb-0 **:data-[slot=empty-icon]:bg-transparent **:data-[slot=empty-icon]:text-muted-foreground"
      >
        <slot name="empty" />
      </ContentCard>
      <slot />
    </div>
  </section>
</template>
