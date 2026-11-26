<script setup lang="ts">
import SectionCard from '../../components/SectionCard.vue'
import { ref } from 'vue'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import {
  Combobox,
  ComboboxAnchor,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
  ComboboxViewport,
} from '@/components/ui/combobox'
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import {
  Popover,
  PopoverContent,
  PopoverDescription,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from '@/components/ui/popover'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

// The overlays and pickers of the /design page: Dialog, Sheet, AlertDialog, Popover, Tooltip,
// Command and Combobox, each opened from its trigger as the board opens it.
const TICKETS = [
  ['CF-1', 'Build the thing'],
  ['CF-2', 'Fix the other thing'],
] as const
const query = ref('')
</script>

<template>
  <SectionCard
    heading="overlays-heading"
    title="Overlays and pickers"
    description="Dialog, Sheet, AlertDialog, Popover, Tooltip, Command, Combobox"
  >
    <div class="grid gap-6">
      <div class="flex flex-wrap items-center gap-2">
        <Dialog>
          <DialogTrigger as-child><Button variant="outline">Dialog</Button></DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>A dialog</DialogTitle>
              <DialogDescription>The keyboard shortcuts open in one.</DialogDescription>
            </DialogHeader>
          </DialogContent>
        </Dialog>
        <Sheet>
          <SheetTrigger as-child><Button variant="outline">Sheet</Button></SheetTrigger>
          <SheetContent>
            <SheetHeader>
              <SheetTitle>A sheet</SheetTitle>
              <SheetDescription>A ticket and the New ticket form open in one.</SheetDescription>
            </SheetHeader>
          </SheetContent>
        </Sheet>
        <AlertDialog>
          <AlertDialogTrigger as-child
            ><Button variant="outline">Alert dialog</Button></AlertDialogTrigger
          >
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete ticket</AlertDialogTitle>
              <AlertDialogDescription>
                Delete CF-1 Build the thing? Undo in the notice that follows brings it back.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction variant="destructive">Delete</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
        <Popover>
          <PopoverTrigger as-child><Button variant="outline">Popover</Button></PopoverTrigger>
          <PopoverContent>
            <PopoverHeader>
              <PopoverTitle>A popover</PopoverTitle>
              <PopoverDescription>A menu that holds a form opens in one.</PopoverDescription>
            </PopoverHeader>
          </PopoverContent>
        </Popover>
        <!-- CommandInput takes focus when it mounts: drawn inline, it would scroll the page to it. -->
        <Popover>
          <PopoverTrigger as-child><Button variant="outline">Command</Button></PopoverTrigger>
          <PopoverContent class="w-64 p-0">
            <Command>
              <CommandInput placeholder="Jump to a page" aria-label="Jump to a page" />
              <CommandList aria-label="Pages">
                <CommandEmpty>No page matches.</CommandEmpty>
                <CommandGroup heading="Pages">
                  <CommandItem value="tickets">Tickets</CommandItem>
                  <CommandItem value="inbox">Inbox</CommandItem>
                  <CommandItem value="analytics">Analytics</CommandItem>
                </CommandGroup>
              </CommandList>
            </Command>
          </PopoverContent>
        </Popover>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger as-child><Button variant="outline">Tooltip</Button></TooltipTrigger>
            <TooltipContent>A cut value, whole</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>
      <div class="grid items-start gap-6 md:grid-cols-2">
        <Combobox ignore-filter :reset-search-term-on-blur="false">
          <ComboboxAnchor>
            <ComboboxInput
              v-model="query"
              aria-label="Find a ticket by id or title"
              placeholder="Find a ticket by id or title"
            />
          </ComboboxAnchor>
          <ComboboxList aria-label="Matching tickets">
            <ComboboxViewport>
              <ComboboxEmpty>No ticket matches.</ComboboxEmpty>
              <ComboboxItem v-for="[id, title] in TICKETS" :key="id" :value="id"
                ><span class="shrink-0 font-mono text-xs">{{ id }}</span
                ><span class="min-w-0 truncate">{{ title }}</span></ComboboxItem
              >
            </ComboboxViewport>
          </ComboboxList>
        </Combobox>
      </div>
    </div>
  </SectionCard>
</template>
