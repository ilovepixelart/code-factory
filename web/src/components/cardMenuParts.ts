// The parts each of a card's two menus is built from: the same items render in the button's
// DropdownMenu and in the card's right-click ContextMenu.

import type { Component } from 'vue'
import {
  ContextMenuGroup,
  ContextMenuItem,
  ContextMenuRadioGroup,
  ContextMenuRadioItem,
  ContextMenuSub,
  ContextMenuSubContent,
  ContextMenuSubTrigger,
} from '@/components/ui/context-menu'
import {
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
} from '@/components/ui/dropdown-menu'

export interface MenuParts {
  Group: Component
  Item: Component
  Sub: Component
  SubTrigger: Component
  SubContent: Component
  RadioGroup: Component
  RadioItem: Component
}

export const DROPDOWN: MenuParts = {
  Group: DropdownMenuGroup,
  Item: DropdownMenuItem,
  Sub: DropdownMenuSub,
  SubTrigger: DropdownMenuSubTrigger,
  SubContent: DropdownMenuSubContent,
  RadioGroup: DropdownMenuRadioGroup,
  RadioItem: DropdownMenuRadioItem,
}

export const CONTEXT: MenuParts = {
  Group: ContextMenuGroup,
  Item: ContextMenuItem,
  Sub: ContextMenuSub,
  SubTrigger: ContextMenuSubTrigger,
  SubContent: ContextMenuSubContent,
  RadioGroup: ContextMenuRadioGroup,
  RadioItem: ContextMenuRadioItem,
}
