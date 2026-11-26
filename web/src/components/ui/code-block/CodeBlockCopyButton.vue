<script setup lang="ts">
import type { PrimitiveProps } from 'reka-ui'

import type { HTMLAttributes } from 'vue'
import type { ButtonVariants } from '@/components/ui/button'
import { Tick02Icon, Copy01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { useClipboard } from '@vueuse/core'
import { cn } from 'cn'
import { Button } from '@/components/ui/button'

defineOptions({ inheritAttrs: false })

const props = withDefaults(
  defineProps<
    PrimitiveProps & {
      value: string
      variant?: ButtonVariants['variant']
      size?: ButtonVariants['size']
      class?: HTMLAttributes['class']
    }
  >(),
  {
    as: 'button',
    variant: 'ghost',
    size: 'icon-xs',
  },
)

const { copy, copied } = useClipboard({ copiedDuring: 2000, legacy: true })
</script>

<template>
  <Button
    v-bind="$attrs"
    data-slot="code-block-copy-button"
    :data-copied="copied || undefined"
    :as="as"
    :as-child="asChild"
    :variant="variant"
    :size="size"
    :aria-label="copied ? 'Copied' : 'Copy'"
    :class="cn('', props.class)"
    @click="copy(props.value)"
  >
    <HugeiconsIcon v-if="copied" key="hugeicons-icon-1" :icon="Tick02Icon" />
    <HugeiconsIcon v-else key="hugeicons-icon-2" :icon="Copy01Icon" />
  </Button>
  <span aria-live="polite" class="sr-only">{{ copied ? 'Copied' : '' }}</span>
</template>
