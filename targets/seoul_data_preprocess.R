# The complete Seoul study-data preprocessing transaction. Implementation and
# hard-gate validation remain in reusable R/ functions.
list_seoul_data_preprocess <- list(
  targets::tar_target(
    name = seoul_data_preprocess,
    command = preprocess_seoul_data(
      workers = 5,
      threads = 4
    ),
    format = "file",
    resources = targets::tar_resources(
      crew = targets::tar_resources_crew(
        controller = "controller_20"
      )
    )
  )
)
