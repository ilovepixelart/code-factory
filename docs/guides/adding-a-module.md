# Adding a module

A module is one domain area: one package under `src/code_factory/`, each file a layer. Layers import
downward only (`module` > `routes | tools | cli` > `service` > `adapters | repository | ports` >
`tables` > `rules` > `models`); another module is reached only through its `service` and `models`;
`platform` imports no module. The contracts are in `pyproject.toml` (`[tool.importlinter]`) and run
by `tests/test_architecture.py`.

1. Create `src/code_factory/<name>/` with the files it needs, and a `module.py` building
   `Module(name=..., provide=..., router=..., register_tools=..., commands=..., background=...)`.
   `provide` builds the service and registers it with `services.add(Class, instance)`.
2. In `app.py`, import its `module` and add it to `MODULES` after the modules it reads.
3. In `pyproject.toml`, add `code_factory.<name>` to `containers` of the `module-layers` contract.
4. For a table: `tables.py` on `platform.db.Base`, imported by `module.py`, then
   `uv run alembic revision --autogenerate -m "..."`; read and edit the draft (`timestamptz`, `text`,
   `NOT NULL`, indexed foreign keys, schema and data in separate revisions), and set
   `EXPECTED_REVISION` in `platform/db/schema.py` to the new head.
5. Tests in `tests/<name>/`, file names unique across `tests/`. `tests/test_architecture.py` fails
   when step 3 or 4 is forgotten.
6. `uv run code-factory docs --out docs/reference` regenerates the module map, the feature map, the
   database tables and the commands page; the tests fail until the committed pages match.

A module another module must call back without a cycle offers a port: the caller declares a
`Protocol` in its `ports.py`, the owner exposes an adapter in its `module.py`, and `app.py` connects
them (see `runs.module.build_module` and `hooks.module.RunHookCommands`).
