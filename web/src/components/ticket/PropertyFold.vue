<script setup lang="ts">
import { ArrowRight01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { FieldGroup } from '@/components/ui/field'

// The rows of a group as they are, or folded under "Tests and parallel" (CF-1206), a chevron
// showing it opens: a fold does not hide a value set, so it opens while one of its rows has one.
// New ticket folds its groups the same way under "More properties".
const {
  fold,
  open,
  label = 'Tests and parallel',
  name = 'More code settings',
  spacing = 'mt-1 gap-1',
} = defineProps<{
  fold: boolean
  open: boolean
  label?: string
  /** The fold's accessible name. */
  name?: string
  /** The space above and between what it holds. */
  spacing?: string
}>()
defineSlots<{ default(): unknown }>()
const shown = ref(false)
watch(
  () => open,
  (value) => (shown.value = value),
  { immediate: true },
)
</script>

<template>
  <Collapsible
    v-if="fold"
    v-model:open="shown"
    :unmount-on-hide="false"
    :aria-label="name"
    class="mt-1"
  >
    <CollapsibleTrigger as-child
      ><Button type="button" variant="link" class="border-0 px-0"
        ><HugeiconsIcon
          :icon="ArrowRight01Icon"
          data-icon="inline-start"
          class="transition-transform group-data-[state=open]/button:rotate-90"
          aria-hidden="true"
        />{{ label }}</Button
      ></CollapsibleTrigger
    >
    <CollapsibleContent
      ><FieldGroup :class="spacing"><slot /></FieldGroup
    ></CollapsibleContent>
  </Collapsible>
  <slot v-else />
</template>
