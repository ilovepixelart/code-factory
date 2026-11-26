<script lang="ts" setup>
import type { CalendarPrevProps } from 'reka-ui'

import type { HTMLAttributes } from 'vue'
import { ArrowLeft01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { reactiveOmit } from '@vueuse/core'
import { cn } from 'cn'
import { CalendarPrev, useForwardProps } from 'reka-ui'
import { buttonVariants } from '@/components/ui/button'

const props = defineProps<CalendarPrevProps & { class?: HTMLAttributes['class'] }>()

const delegatedProps = reactiveOmit(props, 'class')

const forwardedProps = useForwardProps(delegatedProps)
</script>

<template>
  <CalendarPrev
    data-slot="calendar-prev-button"
    :class="
      cn(
        buttonVariants({ variant: 'outline' }),
        'pointer-events-auto size-7 bg-transparent p-0 opacity-50 hover:opacity-100',
        props.class,
      )
    "
    v-bind="forwardedProps as CalendarPrevProps"
  >
    <slot>
      <HugeiconsIcon :icon="ArrowLeft01Icon" :stroke-width="2" class="cn-rtl-flip size-4" />
    </slot>
  </CalendarPrev>
</template>
