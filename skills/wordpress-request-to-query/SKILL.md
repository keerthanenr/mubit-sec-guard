---
name: wordpress-request-to-query
description: Fix WordPress code where request data reaches a $wpdb query or a privileged action behind a weak or home-made auth check — the bug class behind CVE-2024-27956 (WP-Automatic). Use when the security guard flags sql_injection in WordPress/PHP code, or when writing plugin endpoints, AJAX handlers or REST routes that touch the database.
---

# Request data must never reach $wpdb, and every action needs a real capability check

## Why this matters
CVE-2024-27956 in the WP-Automatic plugin (disclosed by Patchstack on 13 March 2024, fixed in 3.92.1) let crafted requests get past the plugin's own authentication check and run database queries. WPScan recorded more than 5.5 million attack attempts after disclosure; attackers created admin users and planted backdoors. Unauthenticated SQL injection in plugins keeps recurring, so treat this as a pattern, not a one-off.

Sources: [SecurityWeek](https://www.securityweek.com/critical-wordpress-automatic-plugin-vulnerability-exploited-to-inject-backdoors/), [SecurityAffairs](https://securityaffairs.com/?p=162364).

## Spot it
Any of these in a plugin or theme:
- `$_GET`, `$_POST`, `$_REQUEST`, `$_COOKIE` or `$request->get_param()` concatenated or interpolated into `$wpdb->query()`, `get_results()`, `get_var()`, `get_row()`.
- `$wpdb->prepare()` called on a template that already contains concatenated input (e.g. a `LIKE '%" . $term . "%'` clause): prepare protects placeholders only.
- An endpoint that "authenticates" with a home-made token, a hash compare, a shared secret in the request, or `is_user_logged_in()` alone, before doing something privileged.
- A REST route with `'permission_callback' => '__return_true'` that writes or reads private data.
- A standalone PHP file in the plugin that is reachable directly over HTTP and talks to the database.

## Fix it
1. **Placeholders for every value:** `$wpdb->prepare( "SELECT * FROM {$wpdb->posts} WHERE ID = %d AND post_status = %s", $id, $status )`.
2. **LIKE:** escape the term, then use a placeholder: `$like = '%' . $wpdb->esc_like( $term ) . '%'; $wpdb->prepare( "... WHERE post_title LIKE %s", $like )`.
3. **Identifiers (table/column/order) cannot be placeholders:** pick them from an allow-list.
4. **Authorise with WordPress, not your own scheme:** `current_user_can( 'manage_options' )` (or the narrowest capability) plus a nonce (`check_ajax_referer()` / `wp_verify_nonce()`); REST routes get a real `permission_callback`.
5. **No directly reachable PHP files:** start every file with `defined( 'ABSPATH' ) || exit;` and route requests through hooks.
6. **Validate types early:** `absint()`, `sanitize_text_field()`, `sanitize_key()` before use (not instead of placeholders).

## Before / after (illustrative, not the plugin's real code)

```php
// Before: home-made token check, request value straight into SQL.
add_action( 'wp_ajax_nopriv_export', function () {
    global $wpdb;
    if ( md5( $_POST['user'] ) !== $_POST['sig'] ) { wp_die(); }
    $rows = $wpdb->get_results( "SELECT * FROM {$wpdb->prefix}leads WHERE campaign = '" . $_POST['campaign'] . "'" );
    wp_send_json( $rows );
} );
```

```php
// After: logged-in only, capability + nonce, placeholder.
add_action( 'wp_ajax_export', function () {
    global $wpdb;
    check_ajax_referer( 'leads_export' );
    if ( ! current_user_can( 'manage_options' ) ) { wp_send_json_error( null, 403 ); }
    $campaign = sanitize_text_field( wp_unslash( $_POST['campaign'] ?? '' ) );
    $rows = $wpdb->get_results( $wpdb->prepare(
        "SELECT id, email, created_at FROM {$wpdb->prefix}leads WHERE campaign = %s", $campaign
    ) );
    wp_send_json_success( $rows );
} );
```

## Also check
- Sites running a vulnerable plugin version need an **update**, not a code fix: use a version scanner (WPScan, Patchstack, OSV) for that.
- After fixing, re-run the guard on the file; it should come back `none`.
