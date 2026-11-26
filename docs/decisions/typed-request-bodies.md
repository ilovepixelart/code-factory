# Request bodies are typed

Every request body is a pydantic model with `extra="forbid"`: Swagger shows its fields, and an
unknown field or one of the wrong kind is a 400 pointing at it.

**Why.** An untyped dictionary accepted anything and coerced what it found: a line given as text
was dropped, a misspelt field ignored without a word.

**What follows.** `tests/contract/test_contract_openapi.py` fails for any body in the OpenAPI
document that names no fields or accepts others. The one exception is
`POST /api/hooks/permission`, which takes the coding agent's own hook payload whole: its keys change
between runtime versions, and a key the board does not know must not cost a run its request.
