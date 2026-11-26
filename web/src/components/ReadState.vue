<script setup lang="ts">
import { Alert, AlertAction, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import ReadSkeleton, { type ReadShape } from './ReadSkeleton.vue'

// A page's read before its answer: the outline of its sections while it is read, or why there is
// no answer and a way to read again.
const { failed = '', shape = 'document' } = defineProps<{
  what: string
  failed?: string
  shape?: ReadShape
}>()
const emit = defineEmits<{ retry: [] }>()
</script>

<template>
  <div v-if="failed" class="page-wide">
    <Alert variant="destructive">
      <AlertTitle>{{ failed }}</AlertTitle>
      <AlertAction>
        <Button type="button" variant="secondary" size="sm" data-read-again @click="emit('retry')">
          Read again
        </Button>
      </AlertAction>
    </Alert>
  </div>
  <div v-else class="page-wide" aria-live="polite" aria-busy="true">
    <span class="sr-only">Reading {{ what }}</span>
    <ReadSkeleton :shape="shape" />
  </div>
</template>
