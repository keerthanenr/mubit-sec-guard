---
name: php-sql-injection
description: Fix PHP code where user input reaches an SQL string (mysqli, PDO, pg_*, Laravel, Symfony/Doctrine, CodeIgniter). Use when the security guard flags sql_injection in PHP.
---

# Bind values, allow-list identifiers

## Spot it
- `$_GET` / `$_POST` / `$_REQUEST` / `$_COOKIE` or a function argument concatenated (`.`) or interpolated (`"$x"`, `{$x}`) into a query string.
- `sprintf()` building SQL; `mysqli_real_escape_string()` used on a value placed **unquoted** (numbers, `IN (...)`, `ORDER BY`).
- Laravel `DB::raw()`, `whereRaw()`, `orderByRaw()`; Doctrine DQL built with `.`; `->query()` instead of `->prepare()`.

## Fix it
1. **PDO:** `$st = $pdo->prepare('SELECT * FROM users WHERE id = ?'); $st->execute([$id]);`
2. **mysqli:** `$st = $db->prepare('... WHERE email = ?'); $st->bind_param('s', $email); $st->execute();`
3. **Laravel:** query builder (`->where('email', $email)`) or bindings: `whereRaw('lower(email) = ?', [$email])`.
4. **Doctrine:** `->setParameter('email', $email)` on a `:email` placeholder.
5. **Identifiers can't be bound:** map user choices to an allow-list (`$cols = ['name' => 'name', 'date' => 'created_at']; $col = $cols[$_GET['sort']] ?? 'created_at';`).
6. **Lists:** build one `?` per item and bind them; never `implode` raw input.

```php
// Before
$rows = $pdo->query("SELECT * FROM orders WHERE user_id = " . $_GET['uid'])->fetchAll();
// After
$st = $pdo->prepare('SELECT * FROM orders WHERE user_id = ?');
$st->execute([(int) $_GET['uid']]);
$rows = $st->fetchAll();
```

Casting (`(int)`) is good input hygiene; placeholders are the actual defence.
