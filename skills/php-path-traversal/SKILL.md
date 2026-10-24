---
name: php-path-traversal
description: Fix PHP code where user input builds a file path for include/require, readfile, file_get_contents, fopen, unlink, uploads or zip extraction. Use when the security guard flags path_traversal.
---

# Never build paths from input: map, then confine

## Spot it
- Request data in `include` / `require` (local file inclusion, often remote code execution), `readfile`, `file_get_contents`, `fopen`, `unlink`, `move_uploaded_file`, `ZipArchive::extractTo`, `highlight_file`.
- "Checks" that don't work: `str_replace('../', '', $f)` (bypassed with `....//`), an extension check (`.pdf`) alone, `str_starts_with()` on the **unresolved** path, `realpath()` without comparing to the base directory.

## Fix it
1. **Best: an allow-list map.** `$pages = ['home' => 'home.php', 'about' => 'about.php']; include __DIR__ . '/pages/' . ($pages[$_GET['p'] ?? 'home'] ?? 'home.php');`
2. **Files by id, not name:** store uploads under a generated name; look up the real path from the database.
3. **If a name is unavoidable:** strip directories, resolve, and confine:
   ```php
   $base = realpath(__DIR__ . '/uploads');
   $path = realpath($base . '/' . basename($_GET['file'] ?? ''));
   if ($path === false || !str_starts_with($path, $base . DIRECTORY_SEPARATOR)) {
       http_response_code(404); exit;
   }
   readfile($path);
   ```
4. **Zip extraction:** validate every entry name (no `..`, no absolute paths) before extracting.
5. Never `include` anything derived from a request.
