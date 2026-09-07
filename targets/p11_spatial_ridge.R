list_p11_spatial_ridge <- list(
  targets::tar_target(
    s11_ridge_sources,
    p11_ridge_source_files(),
    format = "file"
  ),
  targets::tar_target(
    s11_ridge_acceptance,
    {
      status <- system2(
        "python",
        c("scripts/p11_spatial_ridge.py", "--config",
          p11_source_file(s11_ridge_sources, "p11_ridge_evaluation.yml")),
        stdout = TRUE,
        stderr = TRUE,
        env = c("PYTHONPATH=python", "PYTHONDONTWRITEBYTECODE=1")
      )
      if (!identical(attr(status, "status"), NULL)) stop(paste(status, collapse = "\n"))
      "/mnt/hdd002/dhnyu/fusedata/downstream_data/p11_ridge/p11e_047e764ed7467b72ebe846df/p11_e_acceptance.json"
    },
    format = "file"
  )
)
