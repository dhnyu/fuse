list_p11_spatial_readiness <- list(
  targets::tar_target(
    p11_c_contract,
    "config/p11_spatial_readiness.yml",
    format = "file"
  ),
  targets::tar_target(
    p11_c_methodology,
    c("config/dissertation_authority_p11_transformation.json",
      "config/p11_target_transformation_methodology.json"),
    format = "file"
  ),
  targets::tar_target(
    p11_c_acceptance,
    {
      p11_c_methodology
      status <- system2(
        "python",
        c("scripts/p11_spatial_readiness.py", "--config", p11_c_contract),
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
