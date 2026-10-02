# Performance display draft — NOT PUBLISHED

The 2026-09-22 optimization was stopped at the Phase 1 public validation gate
because Chromium reported `net::ERR_NETWORK_CHANGED` and the viewer stopped on
`Failed to fetch`. Production was rolled back to the original server. The
Cloudflare tunnel and original viewer routes are unchanged.

`runtime.js` and `scripts/build_viewer_performance.py` are preparatory source,
not a validated/published viewer generation. Only syntax and the isolated cache
unit test were run. Do not publish this bundle without completing the origin
public validation and full scientific/display regression matrix.

See `reports/20260922_viewer_remote_performance_optimization.md` for evidence,
rollback status, and the outstanding validation gates.
