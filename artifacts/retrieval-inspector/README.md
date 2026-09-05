# Current and Legacy Retrieval Inspectors

**Current: 10K-capable dual-gallery inspector, default Expanded 10,000.**

Run `python tools/render_retrieval_inspector.py` and open the printed
`current/<inspector_id>/index.html`. `current.json` identifies the current package
and acceptance `retr10k_0672df44ea0fb5adceafbec9`.

**Legacy: old 1,600-only application.**

Run `python tools/render_retrieval_inspector.py --legacy-canonical`.
`legacy.json` and `legacy/retrieval_inspector_c612a074a9211c222eb9a811/` explicitly
identify the legacy inspector, bound to P10 `p10acc_6e5071beee7616750dec7907`.
The original root-level `retrieval_inspector_c612a074a9211c222eb9a811/` is retained
unchanged for old links; it is **not current**.

Inside the current application, Canonical 1,600 is a comparison mode, not the
legacy application. Scientific P10/P11 remain unchanged. Current HTML/JS/CSS
and manifests are local; its lazy `assets/` link reuses the accepted external
scene assets and requires the data mount. Heavy packages are not committed.
