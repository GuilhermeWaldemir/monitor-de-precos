// "Preço até R$ X" slider above the product grid.
// Each grid item has data-price = its best price, calculated on the server (monitor/compare.py).
// With the slider at its maximum there is no limit, so every product shows, including those
// without a price. Moving it left hides products above the limit and products without a price.
(function () {
  var filter = document.querySelector("[data-price-filter]");
  if (!filter) return;

  var slider = filter.querySelector('input[type="range"]');
  var valueLabel = filter.querySelector("output");
  var countLabel = filter.querySelector(".price-filter-count");
  var emptyMessage = document.querySelector(".price-filter-empty");
  var items = document.querySelectorAll(".product-grid > li");
  var money = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

  function update() {
    var limit = Number(slider.value);
    var min = Number(slider.min);
    var max = Number(slider.max);
    var noLimit = limit >= max;
    var shown = 0;

    items.forEach(function (item) {
      var price = item.dataset.price; // undefined when the product has no price
      // Number() is only for comparing on screen; the exact prices (Decimal) stay on the server.
      var visible = noLimit || (price !== undefined && Number(price) <= limit);
      item.hidden = !visible;
      if (visible) shown++;
    });

    valueLabel.textContent = noLimit ? "Qualquer preço" : money.format(limit);
    countLabel.textContent = "Mostrando " + shown + " de " + items.length;
    emptyMessage.hidden = shown > 0;
    // How much of the track is filled (the CSS paints it with --fill).
    slider.style.setProperty("--fill", ((limit - min) / (max - min)) * 100 + "%");
  }

  slider.addEventListener("input", update);
  update();
})();
