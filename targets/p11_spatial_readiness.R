list_p11_spatial_readiness <- list(
  targets::tar_target(
    s11_readiness_sources,
    p11_readiness_source_files(),
    format = "file"
  ),
  targets::tar_target(
    s11_readiness_acceptance,
    {
      status <- system2(
        "python",
        c("scripts/p11_spatial_readiness.py", "--config",
          p11_source_file(s11_readiness_sources, "p11_spatial_readiness.yml")),
        stdout = TRUE,
        stderr = TRUE,
        env = c("PYTHONPATH=python", "PYTHONDONTWRITEBYTECODE=1")
      )
      if (!identical(attr(status, "status"), NULL)) stop(paste(status, collapse = "\n"))
      "/mnt/hdd002/dhnyu/fusedata/downstream_data/p11_readiness/p11c_e78d7c740edc49f1f646ebc3/p11_c_acceptance.json"
    },
    format = "file"
  )
)
