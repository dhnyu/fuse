# P9 v1 control-plane retirement. Historical readers remain available.
retired_training_stop <- function(interface) {
  stop(
    paste0(
      "TRAINING_V1_EXECUTION_RETIRED: ", interface,
      ": historical training is read-only and cannot execute; ",
      "use the current accepted-checkpoint resolver."
    ),
    call. = FALSE
  )
}
