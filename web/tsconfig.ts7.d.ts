// TypeScript 7 cannot read a .vue file: this stands in for one only in the `tsc` pass over the .ts
// files (tsconfig.ts7.src.json). The .vue files themselves are type-checked by vue-tsc, which never sees this.
declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<Record<string, unknown>>
  export default component
}
