# Fixed output contract: <publication_root>/<content generation ID>/ manifests,
# rankings/<model>/rankings.parquet; <viewer_root>/<content viewer ID>/ display files.
# Every file target returns all payloads only after checksum/contract validation.
list_s10_query_revision <- list(
  tar_target(s10_revision_contract, "config/s10_query_revision.json", format = "file", resources = s10_revision_cpu),
  tar_target(s10_revision_sources, c("python/s10_query_revision.py", "python/s10_query_viewer.py",
    "python/retrieval_artifacts.py", "python/retrieval_ranking.py", "scripts/s10_query_revision.py",
    "R/s10_query_revision.R", "targets/s10_query_revision.R", "_targets_s10_query_revision.R",
    list.files("tools/retrieval_inspector/supplemental", pattern = "\\.(py|js|css|html)$", full.names = TRUE)),
    format = "file", resources = s10_revision_cpu),
  tar_target(s10_revision_parents, {
    cfg <- jsonlite::read_json(s10_revision_contract)
    c(file.path(cfg$parent_generation, c("acceptance.json", "model_manifest.json", "gallery_manifest.json", "query_manifest.json")),
      file.path(cfg$display_parent, "viewer_receipt.json"))
  }, format = "file", resources = s10_revision_cpu),
  tar_target(s10_revision_counts, {
    s10_revision_sources; s10_revision_parents
    s10_revision_run("audit", s10_revision_contract)
  }, format = "file", resources = s10_revision_cpu),
  tar_target(s10_revision_acceptance, s10_revision_run("generation", s10_revision_contract,
    s10_revision_file(s10_revision_counts, "object_counts_manifest.json")),
    format = "file", resources = s10_revision_cpu),
  tar_target(s10_revision_viewer, s10_revision_run("viewer", s10_revision_contract,
    s10_revision_file(s10_revision_acceptance, "acceptance.json")),
    format = "file", resources = s10_revision_cpu)
)
