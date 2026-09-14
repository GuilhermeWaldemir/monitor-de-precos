// Soft light that follows the mouse over product cards.
// Idea from the "spotlight card" component (21st.dev/@jahed), rewritten without React
// and much subtler. The light itself is drawn by CSS ("Card glow" in style.css), which
// also decides whether it shows (Configurações → Animações). This file only tells the
// CSS where the mouse is, as --glow-x / --glow-y relative to the card.
(function () {
  if (!window.matchMedia("(hover: hover)").matches) return; // touch screens: no mouse to follow

  document.addEventListener("pointermove", function (event) {
    var card = event.target.closest(".product-card");
    if (!card) return;
    var rect = card.getBoundingClientRect();
    card.style.setProperty("--glow-x", event.clientX - rect.left + "px");
    card.style.setProperty("--glow-y", event.clientY - rect.top + "px");
  });
})();
