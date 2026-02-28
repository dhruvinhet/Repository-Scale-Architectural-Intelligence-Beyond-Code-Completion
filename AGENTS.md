# Style & Formatting

- Keep changes minimal and focused on the requested intent.
- Preserve existing naming conventions and public APIs unless explicitly requested.

# Architecture Rules

- Business logic modules must not directly read environment variables outside configuration boundaries.
- Shared interfaces should be introduced before adapter-specific implementations.
- Prefer dependency injection patterns over hard-coded singleton access.

# Critical Regions

- Do not modify deployment manifests under `.azure/` without explicit intent.
- Do not alter CI workflow files unless the request explicitly references CI/CD behavior.
