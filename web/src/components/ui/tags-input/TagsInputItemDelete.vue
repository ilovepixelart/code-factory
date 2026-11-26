<script setup lang="ts">
import type { TagsInputItemDeleteProps } from 'reka-ui'

import type { HTMLAttributes } from 'vue'
import { Cancel01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { reactiveOmit } from '@vueuse/core'
import { cn } from 'cn'
import { TagsInputItemDelete, useForwardProps } from 'reka-ui'

const props = defineProps<TagsInputItemDeleteProps & { class?: HTMLAttributes['class'] }>()

const delegatedProps = reactiveOmit(props, 'class')

const forwardedProps = useForwardProps(delegatedProps)
</script>

<template>
  <TagsInputItemDelete
    v-bind="forwardedProps as TagsInputItemDeleteProps"
    :class="cn('flex rounded bg-transparent mr-1', props.class)"
  >
    <slot>
      <HugeiconsIcon :icon="Cancel01Icon" :stroke-width="2" class="w-4 h-4" />
    </slot>
  </TagsInputItemDelete>
</template>
