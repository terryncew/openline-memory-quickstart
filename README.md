# Memory + Five-Field Receipts (Quickstart)

Tiny service that:
- saves a MemoryItem, returns a **signed receipt**
- searches your memories
- **revokes** a memory, returning a **revocation receipt**
- verifies receipts offline (or via issuer `.well-known`)

**Endpoints**
- `POST /mem/write`
- `POST /mem/search`
- `POST /mem/revoke`
- `POST /verify`
- `GET  /.well-known/receipts.json`
- `GET  /health`

**Privacy:** fact-not-content. No prompts/chats/photos. Revocation is a receipt.
