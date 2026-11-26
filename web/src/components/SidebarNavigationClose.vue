<script setup lang="ts">
import { watch } from 'vue'
import { useRoute } from 'vue-router'
import { useSidebar } from '@/components/ui/sidebar'

// On a phone the sidebar is a sheet over the page: a page chosen in it closes the sheet, so the
// page is what shows. It reads the sidebar's state, so it sits inside SidebarProvider.
const route = useRoute()
const { setOpenMobile } = useSidebar()
watch(
  () => route.fullPath,
  () => {
    setOpenMobile(false)
  },
)
</script>

<template><span hidden></span></template>
