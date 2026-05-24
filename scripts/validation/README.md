# Validation Scripts

Validation scripts are independent utilities and are intentionally unnumbered.

They check path configuration, write permissions, expected files, and other lightweight invariants. They are callable before or after any stage and are not tied to one strict execution order.

These scripts should remain cheap to run and should not launch expensive OSM, metadata, or image acquisition work.
