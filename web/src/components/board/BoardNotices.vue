<script setup lang="ts">
import HaltNotice from '../HaltNotice.vue'
import type { Board } from '../../lib/board'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'

defineProps<{ problems: Board['problems'] }>()
</script>

<template>
  <HaltNotice />
  <Alert
    v-if="problems.length"
    variant="destructive"
    role="region"
    aria-labelledby="problems-heading"
    class="mt-3 shrink-0"
  >
    <AlertTitle id="problems-heading">Ticket problems</AlertTitle>
    <AlertDescription>
      <ul aria-label="Ticket problems" class="flex flex-col gap-1">
        <li v-for="p in problems" :key="p.path">
          <code :title="p.path">{{ p.repository }}/{{ p.file }}</code
          >&#32;· {{ p.reason }}
        </li>
      </ul>
    </AlertDescription>
  </Alert>
</template>
