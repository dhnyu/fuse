library(targets)

# Isolated formal execution pipeline. It intentionally does not source or
# concatenate the main research target list from _targets.R.
targets::tar_option_set(
  packages = c("digest", "jsonlite", "yaml"),
  error = "stop",
  garbage_collection = TRUE,
  memory = "transient"
)

source("R/research_p9_formal_execution_isolated.R")
source("targets/research_p9_formal_execution.R")

list_p9_formal_execution
