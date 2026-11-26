<script setup lang="ts">
import type { ComboboxInputEmits, ComboboxInputProps } from 'reka-ui'

import { nextTick, ref, watch, type HTMLAttributes } from 'vue'
import { SearchIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { reactiveOmit } from '@vueuse/core'
import { cn } from 'cn'
import { ComboboxInput, injectComboboxRootContext, useForwardPropsEmits } from 'reka-ui'
import { InputGroup, InputGroupAddon } from '@/components/ui/input-group'

defineOptions({
  inheritAttrs: false,
})

const props = defineProps<
  ComboboxInputProps & {
    class?: HTMLAttributes['class']
  }
>()

const emits = defineEmits<ComboboxInputEmits>()

const delegatedProps = reactiveOmit(props, 'class')

const forwarded = useForwardPropsEmits(delegatedProps, emits)

// reka-ui keeps the list's id in a plain field set as the list mounts, after the input rendered,
// so its aria-controls stays empty: it is read again once the list is on the page.
const root = injectComboboxRootContext()
const controls = ref<string>()
watch(
  root.open,
  async (open) => {
    await nextTick()
    controls.value = open && root.contentId ? root.contentId : undefined
  },
  { immediate: true },
)
</script>

<template>
  <InputGroup class="w-auto">
    <InputGroupAddon>
      <HugeiconsIcon :icon="SearchIcon" class="size-4 shrink-0 opacity-50" />
    </InputGroupAddon>
    <ComboboxInput
      data-slot="combobox-input"
      :class="
        cn('flex-1 outline-hidden disabled:cursor-not-allowed disabled:opacity-50', props.class)
      "
      v-bind="{ ...$attrs, ...(forwarded as ComboboxInputProps) }"
      :aria-controls="controls"
    />
  </InputGroup>
</template>
