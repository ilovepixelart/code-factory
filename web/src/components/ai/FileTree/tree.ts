/** A changed file, or a folder of them, in the tree of a branch's changes. */
export type FileNode =
  | { type: 'file'; name: string; path: string }
  | { type: 'folder'; name: string; path: string; children: FileNode[] }

/** The folder tree of `paths`, folders first and each level by name; an empty path is a removed
 *  file, which keeps no name, so it is listed as `removed` at the top. */
export function fileTree(paths: string[], removed: string): FileNode[] {
  const root: FileNode[] = []
  for (const path of paths) {
    if (path === '') {
      root.push({ type: 'file', name: removed, path })
      continue
    }
    const parts = path.split('/')
    let level = root
    parts.slice(0, -1).forEach((name, at) => {
      const folderPath = parts.slice(0, at + 1).join('/')
      let folder = level.find((node) => node.type === 'folder' && node.path === folderPath)
      if (!folder) {
        folder = { type: 'folder', name, path: folderPath, children: [] }
        level.push(folder)
      }
      level = folder.type === 'folder' ? folder.children : level
    })
    level.push({ type: 'file', name: parts.at(-1) ?? path, path })
  }
  return sorted(root)
}

function sorted(nodes: FileNode[]): FileNode[] {
  return nodes
    .map((node) => (node.type === 'folder' ? { ...node, children: sorted(node.children) } : node))
    .sort((a, b) =>
      a.type === b.type ? a.name.localeCompare(b.name, 'en') : a.type === 'folder' ? -1 : 1,
    )
}
