list_p11_downstream_preprocessing <- list(
  targets::tar_target(
    s11_dataset_sources,
    p11_dataset_source_files(),
    format = "file"
  ),
  targets::tar_target(
    s11_dataset_cache,
    p11_output_paths(p11_execute_preprocessing(
      p11_source_file(s11_dataset_sources, "p11_downstream_preprocessing.yml")
    )),
    format = "file"
  )
)
