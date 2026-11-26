<script setup lang="ts">
import { Card } from '@/components/ui/card'

defineSlots<{ default?: () => unknown }>()
</script>

<template>
  <Card class="gap-0 p-0 ring-0">
    <slot />
  </Card>
</template>
