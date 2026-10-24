---
name: php-xss
description: Fix PHP output that writes user-controlled data into HTML, attributes or JavaScript without escaping (plain PHP, Blade, Twig, WordPress). Use when the security guard flags xss in PHP.
---

# Escape on output, for the right context

## Spot it
- `echo`, `print`, `printf`, `<?= ?>` or a heredoc containing request data or stored user content.
- Blade `{!! $x !!}`, Twig `|raw`, WordPress output without `esc_html()` / `esc_attr()`, `get_search_query(false)`.
- `htmlspecialchars()` used, but the value lands in an **unquoted** attribute, a `<script>` block, or a URL.
- `strip_tags()` with allowed tags (event handlers survive).

## Fix it by context
| Where the value goes | Use |
|---|---|
| HTML text | `htmlspecialchars($v, ENT_QUOTES, 'UTF-8')`, Blade `{{ $v }}`, WordPress `esc_html()` |
| Attribute (always quoted) | `htmlspecialchars($v, ENT_QUOTES, 'UTF-8')`, `esc_attr()` |
| URL | validate scheme (`https`), then `esc_url()` / `rawurlencode()` for parts |
| JavaScript | `json_encode($v, JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT)`; WordPress `wp_json_encode()` |
| Rich text | an HTML sanitizer allow-list (e.g. HTML Purifier, `wp_kses_post()`), not `strip_tags()` |

```php
// Before
echo "<input name=\"q\" value=" . $_GET['q'] . ">";
// After
echo '<input name="q" value="' . htmlspecialchars($_GET['q'] ?? '', ENT_QUOTES, 'UTF-8') . '">';
```

Add a Content-Security-Policy without `'unsafe-inline'` as a second layer.
