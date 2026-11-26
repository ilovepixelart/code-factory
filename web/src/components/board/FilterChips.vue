<script setup lang="ts">
import { Cancel01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import type { Chip } from '../../lib/ticketQuery'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

defineProps<{ chips: Chip[]; clearUrl: string }>()

const words = (chip: Chip): string => `${chip.key}: ${chip.value !== '1' ? chip.value : 'yes'}`
</script>

<template>
  <div class="flex flex-wrap items-center gap-1.5 px-4 pt-4" aria-label="Active filters">
    <Badge v-for="chip in chips" :key="`${chip.key}=${chip.value}`" variant="secondary"
      >{{ words(chip) }}
      <Button
        as-child
        variant="ghost"
        size="icon-xs"
        :aria-label="`Remove the filter ${words(chip)}`"
        ><RouterLink :to="chip.href"
          ><HugeiconsIcon :icon="Cancel01Icon" aria-hidden="true" /></RouterLink></Button
    ></Badge>
    <Button as-child variant="link" size="xs"><RouterLink :to="clearUrl">Clear</RouterLink></Button>
  </div>
</template>
