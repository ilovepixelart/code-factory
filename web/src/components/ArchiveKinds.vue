<script setup lang="ts">
import { KINDS, kindUrl } from '../lib/memory'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'

// The Archive's kinds as links: each keeps the rest of the address (`address`), the one showing
// marked current.
defineProps<{ kind: string; address: Record<string, string> }>()
</script>

<template>
  <nav aria-label="Kind of archived ticket">
    <Tabs :model-value="kind" activation-mode="manual">
      <TabsList>
        <TabsTrigger v-for="[key, label] in KINDS" :key="key" :value="key" as-child>
          <RouterLink
            :to="kindUrl(address, key)"
            :aria-current="kind === key ? 'page' : undefined"
            >{{ label }}</RouterLink
          >
        </TabsTrigger>
      </TabsList>
    </Tabs>
  </nav>
</template>
