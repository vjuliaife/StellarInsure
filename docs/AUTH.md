# Auth Flow for Integrators

## Overview

StellarInsure uses Stellar wallet signature verification for authentication. Users prove ownership of a Stellar keypair by signing a message, and the backend issues JWT tokens for subsequent requests.

This is **not** SEP-10. There is no challenge endpoint or structured handshake — the client constructs a message, signs it locally, and sends the signature directly to `/auth/login`.

---

## Auth Sequence

```
1. Client chooses a message to sign (e.g. a timestamped nonce)
   ↓
2. Client signs the message with the Stellar private key (Ed25519)
   ↓
3. POST /auth/login  { stellar_address, message, signature }
   ↓
4. Backend verifies the signature against the public key
   ↓
5. Backend returns access_token + refresh_token
   ↓
6. Client includes access_token in Authorization header for all requests
   ↓
7. When access_token expires, POST /auth/refresh to get new tokens
```

New users are automatically created on first login — there is no separate registration step required.

---

## Step 1 — Construct a message

The backend does not enforce a specific message format; it only verifies that the signature matches whatever message is sent. Use a timestamped nonce to prevent replay across sessions:

```
Sign in to StellarInsure: <unix_timestamp>
```

Example:
```
Sign in to StellarInsure: 1714204800
```

---

## Step 2 — Sign with Freighter

```javascript
import freighter from "@stellar/freighter-api";

const message = `Sign in to StellarInsure: ${Math.floor(Date.now() / 1000)}`;
const { signedMessage } = await freighter.signMessage(message);
// signedMessage is a base64-encoded Ed25519 signature
```

### Sign with stellar-sdk (server/testing)

```javascript
import { Keypair } from "@stellar/stellar-sdk";

const keypair = Keypair.fromSecret("S...");
const message = `Sign in to StellarInsure: ${Math.floor(Date.now() / 1000)}`;
const msgBytes = Buffer.from(message, "utf8");
const signature = keypair.sign(msgBytes).toString("base64");
```

```python
from stellar_sdk import Keypair
import base64, time

keypair = Keypair.from_secret("S...")
message = f"Sign in to StellarInsure: {int(time.time())}"
signature = base64.b64encode(keypair.sign(message.encode())).decode()
```

---

## Step 3 — Login

**Endpoint:** `POST /auth/login`

**Rate limit:** 10 requests / minute per IP

**Request body:**

```json
{
  "stellar_address": "GXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
  "message": "Sign in to StellarInsure: 1714204800",
  "signature": "<base64-encoded Ed25519 signature>"
}
```

**curl example:**

```bash
curl -X POST https://api.example.com/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "stellar_address": "GXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
    "message": "Sign in to StellarInsure: 1714204800",
    "signature": "ABC123...base64..."
  }'
```

**Response (200):**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

**Error responses:**

| HTTP | Code | Meaning |
|------|------|---------|
| 401 | AUTH_001 | Signature is invalid or does not match the message |
| 429 | — | Rate limit exceeded |

---

## Token Lifetimes and Headers

| Token | Lifetime | Usage |
|-------|----------|-------|
| `access_token` | 30 minutes (`expires_in: 1800`) | Sent as `Authorization: Bearer <token>` on every request |
| `refresh_token` | 7 days | Sent to `POST /auth/refresh` to obtain a new token pair |

**JWT claims** (decoded payload):

```json
{
  "sub": "42",
  "stellar_address": "GXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
  "exp": 1714206600,
  "type": "access"
}
```

- `sub` — internal user ID (integer as string)
- `stellar_address` — Stellar public key
- `exp` — expiry as Unix timestamp
- `type` — `"access"` or `"refresh"`; the backend rejects access tokens presented to `/auth/refresh` and vice versa

---

## Step 4 — Authenticated Requests

Include the access token in every request:

```bash
curl https://api.example.com/policies \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

A missing or invalid token returns:

```json
HTTP 401
{
  "error": { "code": "AUTH_002", "message": "User not found" }
}
```

An expired token returns HTTP 401 with code `AUTH_004`.

---

## Step 5 — Refresh Tokens

**Endpoint:** `POST /auth/refresh`

```bash
curl -X POST https://api.example.com/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."}'
```

**Response (200):** same shape as login — a new `access_token` and `refresh_token`.

**Error:** HTTP 401 if the refresh token is expired or has the wrong type.

When the refresh token itself expires (after 7 days), the user must sign again via `/auth/login`.

---

## How Signature Verification Works

The backend uses the Stellar Python SDK's `Keypair.verify()`:

```python
keypair = Keypair.from_public_key(stellar_address)
keypair.verify(
    data=message.encode("utf-8"),
    signature=base64.b64decode(signature),
)
```

This is a standard Ed25519 signature check. The signature must be a base64-encoded raw Ed25519 signature (64 bytes) over the UTF-8 bytes of the message string.

---

## Error Code Reference

| Code | HTTP | Description |
|------|------|-------------|
| AUTH_001 | 401 | Invalid wallet signature |
| AUTH_002 | 401 | User not found |
| AUTH_003 | 400 | User already exists (only relevant on `/auth/register`) |
| AUTH_004 | 401 | Token expired or invalid |

---

## Notes for Integrators

- **`/auth/login` vs `/auth/register`:** Both accept the same request body and perform the same signature check. `/auth/login` auto-creates a new user record on first login. You do not need to call `/auth/register` separately.
- **Session storage:** The reference frontend stores the session in `sessionStorage` under the key `stellarinsure-session` and clears it on tab close.
- **Logout:** `POST /auth/logout` is a client-side operation only — the backend is stateless and does not invalidate tokens. Discard tokens client-side.
- **Account deletion:** `DELETE /auth/me` requires re-authentication (send the same body as `/auth/login`). It soft-deletes the account, cancels active policies, and anonymises personal data.
