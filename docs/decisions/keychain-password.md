# A database URL without a password takes it from the keychain

When `CODE_FACTORY_DATABASE_URL` names a user and no password, every connection (the engine, the
migrations, the session listener) takes the password of the keychain item `code-factory-postgres`
for that user (`platform/db/engine.py` `connection_url`, `platform/keychain.py`).

**Why.** A URL with the password must live in a file or the environment; one without it can be
written anywhere. `.env.local` holding the whole URL still works, and wins when it has a password.

**What follows.** No password and no keychain entry is refused with the command that adds one. The
placeholder URL of commands that never open the database carries a dummy password so they never ask.
