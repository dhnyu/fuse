# Script Workflows

Executable workflow scripts are organized by stage. Numbered scripts indicate the intended execution order within a production workflow. Unnumbered scripts are utilities or optional diagnostics that can be run independently.

Reusable implementation code remains in `R/` and `src/`; scripts should stay thin and call those helpers.
