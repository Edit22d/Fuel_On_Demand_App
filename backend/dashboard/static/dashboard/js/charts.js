/* Dependency-free charts for the console: area line, donut, sparkline.
   Everything renders as inline SVG so the console works with no CDN access. */
(function () {
  const NS = "http://www.w3.org/2000/svg";

  function el(name, attrs) {
    const node = document.createElementNS(NS, name);
    for (const key in attrs) node.setAttribute(key, attrs[key]);
    return node;
  }

  const nf = new Intl.NumberFormat("en-UG");
  const money = (value) => "UGX " + nf.format(Math.round(value || 0));

  function niceScale(values) {
    const max = Math.max.apply(null, values.concat([1]));
    const step = max / 4;
    return Math.max(step, 1) * 4;
  }

  function smoothPath(points) {
    let path = `M ${points[0][0]} ${points[0][1]}`;
    for (let i = 0; i < points.length - 1; i++) {
      const p0 = points[i - 1] || points[i];
      const p1 = points[i];
      const p2 = points[i + 1];
      const p3 = points[i + 2] || p2;
      const c1x = p1[0] + (p2[0] - p0[0]) / 6;
      const c1y = p1[1] + (p2[1] - p0[1]) / 6;
      const c2x = p2[0] - (p3[0] - p1[0]) / 6;
      const c2y = p2[1] - (p3[1] - p1[1]) / 6;
      path += ` C ${c1x} ${c1y}, ${c2x} ${c2y}, ${p2[0]} ${p2[1]}`;
    }
    return path;
  }

  /* ------------------------------------------------------------------ line */
  /* One gold revenue area plus an optional secondary line (orders), each on its
     own scale, with dots, a hover guideline and a combined tooltip. */
  function line(host, series, options) {
    const opts = Object.assign(
      { height: 250, valueKey: "revenue", secondary: null, color: "#F5C72E", secondaryColor: "#5AD7D0", labelKey: "label", fill: false },
      options
    );
    host.innerHTML = "";
    host.style.position = "relative";
    if (!series || !series.length) return null;

    /* Match the drawing surface to the card it lives in, so the curves keep
       their true shape instead of being letterboxed into a fixed 760px box. */
    const room = host.clientWidth || 0;
    const tall = host.clientHeight || 0;
    const width = Math.max(Math.round(room) || 760, 320);
    const height = opts.fill && tall ? Math.max(Math.round(tall), 180) : opts.height;
    const pad = { top: 16, right: 10, bottom: 26, left: 44 };
    const innerW = width - pad.left - pad.right;
    const innerH = height - pad.top - pad.bottom;

    const primary = series.map((d) => Number(d[opts.valueKey]) || 0);
    const primaryMax = niceScale(primary);
    const secondaryValues = opts.secondary ? series.map((d) => Number(d[opts.secondary]) || 0) : null;
    const secondaryMax = secondaryValues ? niceScale(secondaryValues) : 1;

    const stepX = series.length > 1 ? innerW / (series.length - 1) : innerW;
    const x = (i) => pad.left + i * stepX;
    const yFor = (value, max) => pad.top + innerH - (value / max) * innerH;
    const yPrimary = (v) => yFor(v, primaryMax);
    const ySecondary = (v) => yFor(v, secondaryMax);

    const svg = el("svg", { viewBox: `0 0 ${width} ${height}`, class: "chart-svg", role: "img" });

    const defs = el("defs", {});
    const gradId = "fc-area-" + (line.count = (line.count || 0) + 1);
    const grad = el("linearGradient", { id: gradId, x1: "0", x2: "0", y1: "0", y2: "1" });
    grad.appendChild(el("stop", { offset: "0%", "stop-color": opts.color, "stop-opacity": "0.32" }));
    grad.appendChild(el("stop", { offset: "70%", "stop-color": opts.color, "stop-opacity": "0.05" }));
    grad.appendChild(el("stop", { offset: "100%", "stop-color": opts.color, "stop-opacity": "0" }));
    defs.appendChild(grad);
    svg.appendChild(defs);

    // horizontal guides + value labels
    for (let g = 0; g <= 4; g++) {
      const value = (primaryMax / 4) * g;
      const yy = yPrimary(value);
      svg.appendChild(el("line", {
        x1: pad.left, x2: width - pad.right, y1: yy, y2: yy,
        stroke: "#1a2027", "stroke-width": 1, "stroke-dasharray": g === 0 ? "" : "3 6",
      }));
      const label = el("text", { x: pad.left - 9, y: yy + 3, "text-anchor": "end" });
      label.textContent = value >= 1000 ? Math.round(value / 1000) + "k" : String(Math.round(value));
      svg.appendChild(label);
    }

    // hover guideline sits under the series so it never hides the line
    const guide = el("line", { x1: 0, x2: 0, y1: pad.top, y2: pad.top + innerH, stroke: "rgba(245,199,46,0.35)", "stroke-width": 1, "stroke-dasharray": "3 4", opacity: 0 });
    svg.appendChild(guide);

    const points = primary.map((value, i) => [x(i), yPrimary(value)]);

    if (secondaryValues) {
      const secondaryPoints = secondaryValues.map((value, i) => [x(i), ySecondary(value)]);
      const secondaryPath = smoothPath(secondaryPoints);
      svg.appendChild(el("path", {
        d: `${secondaryPath} L ${secondaryPoints[secondaryPoints.length - 1][0]} ${pad.top + innerH} L ${secondaryPoints[0][0]} ${pad.top + innerH} Z`,
        fill: opts.secondaryColor,
        "fill-opacity": "0.07",
      }));
      svg.appendChild(el("path", { d: secondaryPath, fill: "none", stroke: opts.secondaryColor, "stroke-width": 1.9, "stroke-linecap": "round", opacity: 0.85 }));
      secondaryPoints.forEach(([px, py]) => {
        svg.appendChild(el("circle", { cx: px, cy: py, r: 2.4, fill: "#0b0e11", stroke: opts.secondaryColor, "stroke-width": 1.6 }));
      });
    }

    const path = smoothPath(points);
    svg.appendChild(el("path", {
      d: `${path} L ${points[points.length - 1][0]} ${pad.top + innerH} L ${points[0][0]} ${pad.top + innerH} Z`,
      fill: `url(#${gradId})`,
    }));
    svg.appendChild(el("path", { d: path, fill: "none", stroke: opts.color, "stroke-width": 2.6, "stroke-linecap": "round" }));
    points.forEach(([px, py]) => {
      svg.appendChild(el("circle", { cx: px, cy: py, r: 3, fill: "#0b0e11", stroke: opts.color, "stroke-width": 2 }));
    });

    // x labels (never let them collide)
    series.forEach((d, i) => {
      if (series.length > 8 && i % 2 !== 0 && i !== series.length - 1) return;
      const label = el("text", { x: x(i), y: height - 7, "text-anchor": "middle" });
      label.textContent = d[opts.labelKey];
      svg.appendChild(label);
    });

    // hover targets
    const tip = document.createElement("div");
    tip.className = "chart-tip";
    host.appendChild(tip);

    series.forEach((d, i) => {
      const gx = x(i);
      const focus = el("circle", { cx: gx, cy: yPrimary(primary[i]), r: 5, fill: opts.color, "fill-opacity": "0.18", stroke: opts.color, "stroke-width": 1.6, opacity: 0 });
      const hit = el("rect", { x: gx - stepX / 2, y: pad.top, width: stepX, height: innerH, fill: "transparent" });
      hit.addEventListener("mouseenter", () => {
        focus.setAttribute("opacity", 1);
        guide.setAttribute("x1", gx);
        guide.setAttribute("x2", gx);
        guide.setAttribute("opacity", 1);
        const rows = [`<span class="tip-day">${d[opts.labelKey]}</span>`,
          `<span class="tip-row"><i style="background:${opts.color}"></i>${money(d[opts.valueKey])}</span>`];
        if (opts.secondary != null) {
          rows.push(`<span class="tip-row"><i style="background:${opts.secondaryColor}"></i>${Number(d[opts.secondary]) || 0} orders</span>`);
        }
        tip.innerHTML = rows.join("");
        tip.style.left = (gx / width) * 100 + "%";
        tip.style.top = (yPrimary(primary[i]) / height) * 100 + "%";
        tip.style.opacity = 1;
      });
      hit.addEventListener("mouseleave", () => {
        focus.setAttribute("opacity", 0);
        guide.setAttribute("opacity", 0);
        tip.style.opacity = 0;
      });
      svg.appendChild(hit);
      svg.appendChild(focus);
    });

    host.insertBefore(svg, tip);
    return svg;
  }

  /* ------------------------------------------------------------------ donut */
  function donut(host, slices, options) {
    const opts = Object.assign({ size: 148, thickness: 13, total: null }, options);
    host.innerHTML = "";
    const total = opts.total != null ? opts.total : slices.reduce((sum, s) => sum + Number(s.value || 0), 0);
    const radius = (opts.size - opts.thickness) / 2;
    const c = 2 * Math.PI * radius;
    const svg = el("svg", { viewBox: `0 0 ${opts.size} ${opts.size}` });
    let offset = 0;

    svg.appendChild(el("circle", { cx: opts.size / 2, cy: opts.size / 2, r: radius, fill: "none", stroke: "#161c22", "stroke-width": opts.thickness }));
    slices.forEach((slice) => {
      const value = Number(slice.value || 0);
      if (!total || !value) return;
      const len = (value / total) * c;
      const ring = el("circle", {
        cx: opts.size / 2, cy: opts.size / 2, r: radius, fill: "none",
        stroke: slice.color || "#F5C72E", "stroke-width": opts.thickness,
        "stroke-dasharray": `${Math.max(len - 3, 0)} ${c - Math.max(len - 3, 0)}`,
        "stroke-dashoffset": -offset, "stroke-linecap": "round",
      });
      svg.appendChild(ring);
      offset += len;
    });
    host.appendChild(svg);
    return svg;
  }

  /* ------------------------------------------------------------------ spark */
  function spark(host, values, options) {
    const opts = Object.assign({ color: "#55C68B", width: 74, height: 26 }, options);
    host.innerHTML = "";
    if (!values.length) return;
    const max = Math.max.apply(null, values.concat([1]));
    const min = Math.min.apply(null, values);
    const span = max - min || 1;
    const step = opts.width / Math.max(values.length - 1, 1);
    const points = values.map((v, i) => `${(i * step).toFixed(1)},${(opts.height - 3 - ((v - min) / span) * (opts.height - 6)).toFixed(1)}`);
    const svg = el("svg", { viewBox: `0 0 ${opts.width} ${opts.height}`, preserveAspectRatio: "none" });
    svg.appendChild(el("polyline", { points: points.join(" "), fill: "none", stroke: opts.color, "stroke-width": 1.8, "stroke-linecap": "round", "stroke-linejoin": "round", opacity: 0.9 }));
    const last = points[points.length - 1].split(",");
    svg.appendChild(el("circle", { cx: last[0], cy: last[1], r: 2, fill: opts.color }));
    host.appendChild(svg);
    return svg;
  }

  window.FCCharts = { line, donut, spark, money };
})();
