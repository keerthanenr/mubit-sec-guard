---
name: php-unsafe-deserialization
description: Fix PHP code that calls unserialize() (or igbinary_unserialize, maybe_unserialize, phar:// paths) on data an attacker can influence. Use when the security guard flags unsafe_deserialization.
---

# Use JSON for anything that crosses a trust boundary

## Spot it
- `unserialize()` on cookies, POST bodies, headers, query strings, uploaded files, webhook payloads, or cache/DB values that users can write.
- `igbinary_unserialize()`, WordPress `maybe_unserialize()` on request data.
- File functions given a user-controlled path that could be `phar://…` (triggers deserialization).
- A "signature" that is stripped but never verified, or a hash with no secret key.

## Fix it
1. **Replace with JSON:** `json_encode()` / `json_decode($raw, true, 512, JSON_THROW_ON_ERROR)`, then validate the structure.
2. **If you must keep serialize (trusted data only):** `unserialize($data, ['allowed_classes' => false])`.
3. **Data that round-trips through the client:** sign it with a server secret and verify before decoding:
   ```php
   [$payload, $mac] = explode('.', $_COOKIE['prefs'] ?? '', 2) + [null, null];
   $ok = $payload !== null && hash_equals(hash_hmac('sha256', $payload, getenv('PREFS_KEY')), (string) $mac);
   $prefs = $ok ? json_decode(base64_decode($payload), true, 8, JSON_THROW_ON_ERROR) : [];
   ```
4. Block `phar://` (and other wrappers) in any user-supplied path.
