# User deferred outside-node child lifting and the GPU update pilot. This graph
# completes independent preparation; readiness explicitly records the method gate.
list(
  tar_target(b6b_source_files,b6b_sources(),format="file",resources=b6b_cpu),
  tar_target(b6b_method,b6b_run("contract",b6b_source_files),format="file",resources=b6b_cpu),
  tar_target(b6b_inventory,b6b_run("inventory",b6b_method),format="file",resources=b6b_cpu),
  tar_target(b6b_lineage,b6b_run("lineage",b6b_inventory),format="file",resources=b6b_cpu),
  tar_target(b6b_original_parity,b6b_run("parity",b6b_lineage),format="file",resources=b6b_cpu),
  tar_target(b6b_readiness,b6b_run("readiness",list(b6b_original_parity,b6b_lineage)),format="file",resources=b6b_cpu)
)
