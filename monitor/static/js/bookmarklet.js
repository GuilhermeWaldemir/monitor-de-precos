// "Capturar preço" bookmarklet. It runs INSIDE the store page the user has open (no robot
// visits the store), reads the product data that page already shows, and opens this site's
// /capture page in a new tab. Nothing is saved until the user confirms there.
// monitor/capture.py turns this file into a "javascript:" link and fills in __APP_URL__.
// Keep one statement per line and only full-line comments: they are removed when building the link.
(function () {
  var appUrl = "__APP_URL__";
  var found = { name: "", price: "", image: "", mpn: "", gtin: "" };

  // 1. JSON-LD (schema.org Product), the same block the Python reader uses.
  function walk(data, visit) {
    if (Array.isArray(data)) {
      data.forEach(function (item) { walk(item, visit); });
    } else if (data && typeof data === "object") {
      visit(data);
      if (data["@graph"]) walk(data["@graph"], visit);
    }
  }
  document.querySelectorAll('script[type="application/ld+json"]').forEach(function (script) {
    try {
      walk(JSON.parse(script.textContent), function (item) {
        if (found.price || [].concat(item["@type"]).indexOf("Product") === -1) return;
        var offer = [].concat(item.offers || [])[0] || {};
        var image = [].concat(item.image || [])[0] || "";
        found.price = String(offer.price || offer.lowPrice || "");
        found.name = item.name || "";
        found.image = typeof image === "object" ? image.url || "" : image;
        found.mpn = item.mpn || "";
        found.gtin = item.gtin13 || item.gtin || item.gtin12 || item.gtin14 || item.gtin8 || "";
      });
    } catch (error) {
      // A broken JSON-LD block: ignore it and try the next one.
    }
  });

  // 2. Fallbacks: common price meta tags, then Amazon's visible price.
  function meta(selector) {
    var element = document.querySelector(selector);
    return element ? element.getAttribute("content") || "" : "";
  }
  function text(selector) {
    var element = document.querySelector(selector);
    return element ? element.textContent.trim() : "";
  }
  found.price = found.price || meta('meta[itemprop="price"]') || meta('meta[property="product:price:amount"]') || text("#corePrice_feature_div .a-offscreen");
  found.name = found.name || text("#productTitle") || meta('meta[property="og:title"]') || document.title;
  found.image = found.image || meta('meta[property="og:image"]');

  var params = new URLSearchParams(found);
  params.set("url", location.href);
  window.open(appUrl + "capture?" + params.toString(), "_blank");
})();
