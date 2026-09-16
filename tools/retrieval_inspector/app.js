"use strict";
// Stored artifacts only: this UI switches presentation visibility.
const control = document.getElementById("mode");
function displayMode() {
  document.querySelectorAll("[data-mode]").forEach(row => {
    row.hidden = row.dataset.mode !== control.value;
  });
}
if (control) { control.addEventListener("change", displayMode); displayMode(); }
