# Spatial Scene Inspector Hub

This navigation-only root exposes two existing immutable viewers through relative
symlinks. It neither copies their large payloads nor edits their files. The Hub
uses plain HTML/CSS; no launcher JavaScript or scientific computation is needed.

```bash
python scripts/build_viewer_hub.py
python scripts/serve_viewer_hub.py
python scripts/serve_viewer_hub.py --check
python scripts/validate_viewer_hub.py
```

The builder creates `/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/viewer_hub`
with `canonical` and `extreme` links. Existing Hub roots are verified, not
replaced. The server binds only `127.0.0.1:8765`, verifies the Hub and viewer
identities, and refuses another listener. It never kills a process or chooses
another port. The old `serve_s10_viewer.py` remains unchanged and still expects
the old canonical root; use the new helper for the Hub.

The HTTP server supports reading static files, not modifying them. Symlinks do
not change target filesystem permissions. Run a persistent service in a dedicated
terminal or tmux session if restarting it later; no restart is needed to change
viewers once the Hub is running.

Windows PowerShell:

```powershell
ssh -N -o ExitOnForwardFailure=yes -p 22 -L 28765:127.0.0.1:8765 dhnyu@147.46.167.49
```

Open `http://127.0.0.1:28765/` in a new tab. The launcher separates **Canonical
S10** from **HIGH/LOW Extreme**. The viewer paths retain that distinction without
changing either viewer. Use Ctrl+Shift+R, or DevTools → Network → Disable cache
and reload, if an old document persists.

The live validator uses a fresh Chromium context, disables cache, navigates
through all five links, verifies controls, checks unchanged server PID, and
verifies every file listed in both viewer receipts before and after browsing.
`--offline` is available for local file-route UI checks, but does not establish
that the Hub is serving over HTTP.

The current Extreme route prefers `STANDARD_HIGH_OBJ20` and
`NONLOCAL_HIGH_OBJ20` (query B+R+P ≥ 20). LOW sets are unchanged.
The earlier NONEMPTY (≥1) variants remain historical advanced options.
Original all-scene HIGH sets remain in the viewer’s advanced selector.
This is a display refinement; population statistics and original sets remain
immutable. See `scripts/build_s10_obj20_high.py` and the OBJ20 addendum
report for lineage and validation.
