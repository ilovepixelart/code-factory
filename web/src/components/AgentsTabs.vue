<script setup lang="ts">
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'

// The Agents page's two tabs (CF-1208): what runs (the agents and Claude Code's) and where it runs
// (connections). Each is a link: the address names the tab.
const { connections } = defineProps<{ connections: boolean }>()
const current = (on: boolean) => (on ? 'page' : undefined)
</script>

<template>
  <Tabs :model-value="connections ? 'connections' : 'agents'" activation-mode="manual">
    <TabsList aria-label="Show">
      <TabsTrigger value="agents" as-child>
        <RouterLink to="/agents" :aria-current="current(!connections)">Agents</RouterLink>
      </TabsTrigger>
      <TabsTrigger value="connections" as-child>
        <RouterLink to="/agents?tab=connections" :aria-current="current(connections)"
          >Connections</RouterLink
        >
      </TabsTrigger>
    </TabsList>
  </Tabs>
</template>
