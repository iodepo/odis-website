/* Minimal image lightbox, replacing the Simplelightbox WordPress plugin.
   Uses <dialog>, so Escape-to-close, focus trapping and inertness of the
   page behind it all come from the browser. No dependency. */
(function () {
  "use strict";

  var triggers = document.querySelectorAll("a[data-lightbox]");
  if (!triggers.length || typeof HTMLDialogElement === "undefined") return;

  var dialog = document.createElement("dialog");
  dialog.className = "lightbox";
  dialog.innerHTML =
    '<button class="lightbox__close" aria-label="Close image">&times;</button>' +
    '<img alt="">';
  document.body.appendChild(dialog);

  var img = dialog.querySelector("img");

  dialog.querySelector(".lightbox__close").addEventListener("click", function () {
    dialog.close();
  });

  /* Clicking the backdrop, i.e. outside the image, closes it. */
  dialog.addEventListener("click", function (e) {
    if (e.target === dialog) dialog.close();
  });

  Array.prototype.forEach.call(triggers, function (a) {
    a.addEventListener("click", function (e) {
      e.preventDefault();
      var thumb = a.querySelector("img");
      img.src = a.getAttribute("href");
      img.alt = thumb ? thumb.alt : "";
      dialog.showModal();
    });
  });
})();
