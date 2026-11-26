<script setup lang="ts">
import type { PaginationNextProps } from 'reka-ui'

import type { HTMLAttributes } from 'vue'
import type { ButtonVariants } from '@/components/ui/button'
import { ArrowRight01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { reactiveOmit } from '@vueuse/core'
import { cn } from 'cn'
import { PaginationNext, useForwardProps } from 'reka-ui'
import { buttonVariants } from '@/components/ui/button'

const props = withDefaults(
  defineProps<
    PaginationNextProps & {
      size?: ButtonVariants['size']
      class?: HTMLAttributes['class']
    }
  >(),
  {
    size: 'default',
  },
)

const delegatedProps = reactiveOmit(props, 'class', 'size')
const forwarded = useForwardProps(delegatedProps)
</script>

<template>
  <PaginationNext
    data-slot="pagination-next"
    :class="cn(buttonVariants({ variant: 'ghost', size }), 'pr-2!', props.class)"
    v-bind="forwarded as PaginationNextProps"
  >
    <slot>
      <span class="hidden sm:block">Next</span>
      <HugeiconsIcon :icon="ArrowRight01Icon" data-icon="inline-end" class="cn-rtl-flip" />
    </slot>
  </PaginationNext>
</template>
