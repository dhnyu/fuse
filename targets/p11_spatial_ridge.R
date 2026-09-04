list_p11_spatial_ridge <- list(
  targets::tar_target(
    p11_e_contract,
    "config/p11_ridge_evaluation.yml",
    format = "file"
  ),
  targets::tar_target(
    p11_e_authorized_inputs,
    c(
      "config/p11_spatial_readiness_acceptance.yml",
      "config/p11_target_transformation_methodology.json",
      "config/p11_downstream_dataset.yml"
    ),
    format = "file"
  ),
  targets::tar_target(
    p11_e_acceptance,
    {
      p11_e_authorized_inputs
      status <- system2(
        "python",
        c("scripts/p11_spatial_ridge.py", "--config", p11_e_contract),
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
