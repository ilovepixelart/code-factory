# REST conventions

- A create answers 201 with `Location`, the address that reads the new thing back (tickets, a
  ticket's copy, memory entries).
- A DELETE carries no body: what it removes is named in the path
  (`DELETE /api/tickets/{repository}/{id}/links/{kind}/{target}`, `DELETE /api/views/{name}`).
- Action routes stay POST (`/approve`, `/merge`, `/allow`); there is no version in the path, since
  one build serves the web app and MCP is the external contract.
- Paging stays by offset and page number. The lists that page (the archive, memory search) sort in
  memory by any column, show numbered pages and cap a page at 100 rows: a cursor would cost the
  numbered pages and save no work.

The routes themselves are in [../reference/modules.md](../reference/modules.md) and Swagger.
