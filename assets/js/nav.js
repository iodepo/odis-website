/* Submenu toggles for the main nav.
   CSS already reveals submenus on hover and focus-within, which covers mouse
   and desktop keyboard use. This keeps aria-expanded truthful and gives touch
   and mobile users an explicit control. */
(function () {
  "use strict";

  var toggles = document.querySelectorAll(".nav__toggle");
  if (!toggles.length) return;

  function closeAll(except) {
    Array.prototype.forEach.call(toggles, function (t) {
      if (t !== except) {
        t.setAttribute("aria-expanded", "false");
        t.parentNode.classList.remove("is-open");
      }
    });
  }

  Array.prototype.forEach.call(toggles, function (toggle) {
    toggle.addEventListener("click", function () {
      var open = toggle.getAttribute("aria-expanded") === "true";
      closeAll(toggle);
      toggle.setAttribute("aria-expanded", open ? "false" : "true");
      toggle.parentNode.classList.toggle("is-open", !open);
    });
  });

  document.addEventListener("click", function (e) {
    if (!e.target.closest(".nav__item")) closeAll(null);
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeAll(null);
  });
})();
