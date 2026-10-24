---
name: php-hardcoded-secret
description: Remove API keys, passwords, tokens and signing keys written into PHP code or config. Use when the security guard flags hardcoded_secret.
---

# Secrets come from the environment or a secret store, never the code

## Spot it
- String literals that look like keys or passwords (`sk_live_…`, `AKIA…`, `password => '…'`, `define('DB_PASSWORD', '…')`, bearer tokens, JWT/HMAC signing keys).
- A real secret used as a **fallback**: `getenv('KEY') ?: 'sk_live_…'`.
- WordPress `wp-config.php` / Drupal `settings.php` salts and DB passwords committed to the repo.

## Fix it
1. Read from the environment and fail loudly if missing:
   ```php
   $key = getenv('STRIPE_SECRET_KEY');
   if ($key === false || $key === '') { throw new RuntimeException('STRIPE_SECRET_KEY not set'); }
   ```
2. Laravel: `env()` only in `config/*.php`, then `config('services.stripe.secret')`. Symfony: `%env(STRIPE_SECRET_KEY)%` or the secrets vault.
3. Production: inject from a secret manager (Azure Key Vault, AWS Secrets Manager, Vault) into env vars.
4. **The leaked secret is compromised:** rotate it at the provider, then remove it from git history (`git filter-repo`) — deleting the line is not enough.
5. Add the secret file to `.gitignore` and a secret scanner (gitleaks, GitHub secret scanning) to CI.
