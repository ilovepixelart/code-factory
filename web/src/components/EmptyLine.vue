<script setup lang="ts">
// An Empty inside a page's content is one quiet row: its icon, then its title and sentence, so an
// empty section or block takes a line, not a centred block. Its title is a row's title (text-sm, as
// ItemTitle), never larger than the section heading over it; the icon box shrinks to the line. A page-wide Empty (a ticket that does
// not exist) keeps shadcn-vue's own layout and is not wrapped.
defineSlots<{ default: () => unknown }>()
</script>

<template>
  <div
    data-empty-line
    class="*:data-[slot=empty]:items-start *:data-[slot=empty]:p-0 *:data-[slot=empty]:text-left **:data-[slot=empty-header]:grid **:data-[slot=empty-header]:max-w-none **:data-[slot=empty-header]:grid-cols-[auto_1fr] **:data-[slot=empty-header]:items-center **:data-[slot=empty-header]:gap-x-3 **:data-[slot=empty-header]:gap-y-0.5 **:data-[slot=empty-media]:row-span-2 **:data-[slot=empty-media]:mb-0 **:data-[slot=empty-title]:col-start-2 **:data-[slot=empty-title]:text-sm **:data-[slot=empty-media]:size-8 **:data-[slot=empty-description]:col-start-2"
  >
    <slot />
  </div>
</template>
