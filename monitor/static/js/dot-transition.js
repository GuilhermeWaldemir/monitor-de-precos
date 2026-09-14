// Dot grid that grows into the category icon when a category page opens.
//
// Ported from the React component "Dot Transition" (21st.dev/@hyperiux) to plain JavaScript,
// keeping its main idea and math: the icon is shrunk onto the dot grid to get a "mask"
// (how much of the icon covers each dot), then a band that starts at the middle line and
// spreads up and down makes those dots grow and light up.
// Simplified for this site: one icon, it grows once and stays (no cycling), click replays it.
// Turned on/off in Configurações → Animações; with "reduce motion" the icon appears ready.
(function () {
  var banner = document.querySelector("[data-dot-banner]");
  if (!banner) return;

  var canvas = banner.querySelector("canvas");
  var ctx = canvas.getContext("2d");

  var SPACING = 7;        // px between dots
  var DOT_SIZE = 1.4;     // resting dot, px
  var MAX_DOT_SIZE = 5;   // fully lit dot, px
  var GROW_SECONDS = 1.4;
  var ICON_HEIGHT = 0.8;  // icon height as a fraction of the banner height

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var color = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim();

  var width = 0, height = 0, cols = 0, rows = 0, cellW = SPACING, cellH = SPACING;
  var mask = null;        // Float32Array: 0..1 per dot, how much of the icon covers it
  var progress = 0;       // 0 = only resting dots, 1 = icon fully formed
  var frameId = null;

  var clamp01 = function (v) { return Math.max(0, Math.min(1, v)); };
  var lerp = function (a, b, t) { return a + (b - a) * t; };
  var smoothstep = function (e0, e1, v) {
    var t = clamp01((v - e0) / (e1 - e0));
    return t * t * (3 - 2 * t);
  };
  var smootherstep = function (t) { return t * t * t * (t * (t * 6 - 15) + 10); };

  // The icon comes from the page (a <template> with the same SVG used in the sidebar).
  // It becomes a white-on-transparent image, so its alpha channel is the silhouette.
  var svg = banner.querySelector("template").innerHTML.trim()
    .replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ')
    .replace(/currentColor/g, "#fff")
    .replace('stroke-width="2"', 'stroke-width="2.4"'); // slightly bolder lines read better as dots
  var image = new Image();
  image.onload = function () { resize(); play(); };
  image.src = "data:image/svg+xml," + encodeURIComponent(svg);

  function resize() {
    var rect = canvas.getBoundingClientRect();
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    width = rect.width;
    height = rect.height;
    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); // draw in CSS pixels, sharp on high-DPI screens

    cols = Math.max(1, Math.round(width / SPACING));
    rows = Math.max(1, Math.round(height / SPACING));
    cellW = width / cols;
    cellH = height / rows;
    buildMask();
    draw();
  }

  // Draw the icon into a tiny canvas with one pixel per dot, then read how opaque each pixel is.
  function buildMask() {
    if (!image.complete) return;
    var small = document.createElement("canvas");
    small.width = cols;
    small.height = rows;
    var smallCtx = small.getContext("2d", { willReadFrequently: true });
    var size = rows * ICON_HEIGHT;
    smallCtx.drawImage(image, (cols - size) / 2, (rows - size) / 2, size, size);

    var pixels = smallCtx.getImageData(0, 0, cols, rows).data;
    mask = new Float32Array(cols * rows);
    for (var i = 0; i < cols * rows; i++) {
      mask[i] = pixels[i * 4 + 3] / 255; // alpha channel
    }
  }

  function draw() {
    ctx.clearRect(0, 0, width, height);
    if (!mask) return;

    // A band centered on the middle line grows up and down as progress goes 0 -> 1.
    var anchor = height / 2;
    var edge = Math.max(cellH * 2.6, 1);                     // softness of the band's edge
    var maxExtent = Math.max(anchor, height - anchor) + cellH + edge;
    var bandRadius = progress * (maxExtent + edge) - edge;   // starts hidden behind the line

    ctx.fillStyle = color;
    for (var row = 0; row < rows; row++) {
      var cy = cellH * (row + 0.5);
      var band = reduceMotion ? progress : 1 - smoothstep(bandRadius - edge, bandRadius + edge, Math.abs(cy - anchor));
      for (var col = 0; col < cols; col++) {
        var active = mask[row * cols + col] * band;
        var size = lerp(DOT_SIZE, MAX_DOT_SIZE, active);
        var cx = cellW * (col + 0.5);
        ctx.globalAlpha = lerp(0.16, 1, active);
        ctx.fillRect(cx - size / 2, cy - size / 2, size, size);
      }
    }
    ctx.globalAlpha = 1;
  }

  function play() {
    if (frameId !== null) cancelAnimationFrame(frameId);
    if (reduceMotion) {
      progress = 1;
      draw();
      return;
    }
    var start = null;
    function frame(time) {
      if (start === null) start = time;
      var t = clamp01((time - start) / 1000 / GROW_SECONDS);
      progress = smootherstep(t);
      draw();
      frameId = t < 1 ? requestAnimationFrame(frame) : null; // stops when the icon is formed
    }
    frameId = requestAnimationFrame(frame);
  }

  new ResizeObserver(function () { if (image.complete) resize(); }).observe(canvas);
  canvas.addEventListener("click", play);
})();
