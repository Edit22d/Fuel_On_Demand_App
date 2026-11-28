/* A dependency-free schematic of Kampala for live tracking.
   Real coordinates are projected into an SVG viewBox, so riders, stations and
   deliveries line up geographically — no tile server, no API key. */
(function () {
  const NS = "http://www.w3.org/2000/svg";
  const BOUNDS = { minLat: 0.19, maxLat: 0.4, minLng: 32.4, maxLng: 32.7 };
  const W = 820;
  const H = 520;
  const CBD = { lat: 0.315, lng: 32.582 };
  const layers = new Map();
  const zooms = new WeakMap();

  function el(name, attrs) {
    const node = document.createElementNS(NS, name);
    for (const key in attrs) node.setAttribute(key, attrs[key]);
    return node;
  }

  function project(lat, lng) {
    const x = ((lng - BOUNDS.minLng) / (BOUNDS.maxLng - BOUNDS.minLng)) * W;
    const y = ((BOUNDS.maxLat - lat) / (BOUNDS.maxLat - BOUNDS.minLat)) * H;
    return [x, y];
  }

  function background(svg) {
    for (let x = 0; x <= W; x += 41) {
      svg.appendChild(el("line", { x1: x, y1: 0, x2: x, y2: H, class: "grid-line" }));
    }
    for (let y = 0; y <= H; y += 41) {
      svg.appendChild(el("line", { x1: 0, y1: y, x2: W, y2: y, class: "grid-line" }));
    }

    // Lake Victoria along the southern edge.
    svg.appendChild(el("path", {
      class: "lake",
      d: `M 0 ${H} L 0 432 C 120 415, 210 452, 300 436 C 390 420, 470 460, 560 447 C 640 436, 720 468, ${W} 452 L ${W} ${H} Z`,
    }));

    const [cx, cy] = project(CBD.lat, CBD.lng);
    [58, 118, 190].forEach((r, i) => {
      svg.appendChild(el("ellipse", { cx, cy, rx: r, ry: r * 0.86, class: i === 1 ? "ring major" : "ring" }));
    });

    // radial spokes: Entebbe Rd, Jinja Rd, Bombo Rd, Gayaza Rd, Masaka Rd, Port Bell Rd
    const spokes = [[-2.55, 0.18], [-0.15, 0.34], [-1.45, 0.27], [-1.05, 0.4], [2.5, 0.24], [1.25, 0.3]];
    spokes.forEach(([angle, spread]) => {
      const dx = Math.cos(angle) * W * spread;
      const dy = Math.sin(angle) * H * spread;
      svg.appendChild(el("line", { x1: cx, y1: cy, x2: cx + dx, y2: cy + dy, class: "spoke" }));
    });

    svg.appendChild(el("circle", { cx, cy, r: 26, class: "cbd" }));
    const label = el("text", { x: cx, y: cy + 3, class: "station-label", "text-anchor": "middle" });
    label.textContent = "CBD";
    svg.appendChild(label);
  }

  function tooltipFor(host) {
    let tip = host.querySelector(".map-tip");
    if (!tip) {
      tip = document.createElement("div");
      tip.className = "chart-tip map-tip";
      host.appendChild(tip);
    }
    return tip;
  }

  function bindTip(host, node, html) {
    const tip = tooltipFor(host);
    node.addEventListener("mouseenter", (event) => {
      const box = host.getBoundingClientRect();
      tip.innerHTML = html;
      tip.style.left = event.clientX - box.left + "px";
      tip.style.top = event.clientY - box.top - 12 + "px";
      tip.style.opacity = 1;
    });
    node.addEventListener("mousemove", (event) => {
      const box = host.getBoundingClientRect();
      tip.style.left = event.clientX - box.left + "px";
      tip.style.top = event.clientY - box.top - 12 + "px";
    });
    node.addEventListener("mouseleave", () => { tip.style.opacity = 0; });
  }

  function scaleOf(host) {
    const w = host.clientWidth || W;
    const h = host.clientHeight || H;
    return Math.max(w / W, h / H, 0.1);
  }

  /* Markers and labels live in viewBox units, so a wide card would render them
     oversized. Publish the current scale so CSS can divide it back out. */
  function publishScale(host, svg) {
    svg.style.setProperty("--map-k", scaleOf(host).toFixed(3));
  }

  function render(host, data) {
    host.innerHTML = "";
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "map-svg", role: "img", preserveAspectRatio: "xMidYMid slice" });
    background(svg);

    const routes = el("g", { class: "routes" });
    const orders = el("g", { class: "orders" });
    const stations = el("g", { class: "stations" });
    const riders = el("g", { class: "riders" });
    svg.append(routes, orders, stations, riders);

    const stationList = data.stations || [];
    stationList.forEach((station) => {
      const [x, y] = project(station.lat, station.lng);
      const group = el("g", { transform: `translate(${x} ${y})` });
      group.appendChild(el("rect", { x: -5, y: -5, width: 10, height: 10, class: "station", transform: "rotate(45)" }));
      group.appendChild(el("circle", { r: 9, fill: "transparent" }));
      const label = el("text", { y: 18, class: "station-label", "text-anchor": "middle" });
      label.textContent = station.short || station.name;
      group.appendChild(label);
      bindTip(host, group, `<b>${station.name}</b><br>${station.brand_label || ""} · ${station.address || ""}`);
      stations.appendChild(group);
    });

    (data.orders || []).forEach((order) => {
      if (order.lat == null || order.lng == null) return;
      const [x, y] = project(order.lat, order.lng);
      if (order.station_lat != null) {
        const [sx, sy] = project(order.station_lat, order.station_lng);
        routes.appendChild(el("line", { x1: sx, y1: sy, x2: x, y2: y, class: "route" }));
      }
      const group = el("g", { transform: `translate(${x} ${y})` });
      const ring = el("circle", { r: 5, class: "order-ring" });
      group.appendChild(ring);
      group.appendChild(el("circle", { r: 3.2, class: "order-dot" }));
      group.appendChild(el("circle", { r: 9, fill: "transparent" }));
      bindTip(host, group, `<b>${order.number}</b><br>${order.fuel} → ${order.address}<br>${order.status_label} · ETA ${order.eta} min`);
      orders.appendChild(group);
    });

    const markers = new Map();
    (data.riders || []).forEach((rider) => {
      if (rider.lat == null || rider.lng == null) return;
      const [x, y] = project(rider.lat, rider.lng);
      const group = el("g", { class: "marker", transform: `translate(${x} ${y})` });
      group.appendChild(el("circle", { r: 11, class: "rider-halo" }));
      group.appendChild(el("circle", { r: 6, class: rider.online ? "rider-dot" : "rider-dot idle" }));
      const initials = el("text", { y: 2.2, class: "rider-initials" });
      initials.textContent = rider.initials;
      group.appendChild(initials);
      bindTip(host, group, `<b>${rider.name}</b><br>${rider.plate || rider.vehicle}<br>${rider.order ? "On " + rider.order : rider.online ? "Available" : "Offline"}`);
      markers.set(rider.id, group);
      riders.appendChild(group);
    });

    host.appendChild(svg);
    publishScale(host, svg);
    layers.set(host, { svg, riders, orders, routes, markers });
    if (zooms.has(host)) applyZoom(host, zooms.get(host));
    return svg;
  }

  function update(host, data) {
    const layer = layers.get(host);
    if (!layer) return render(host, data);
    const seen = new Set();
    (data.riders || []).forEach((rider) => {
      if (rider.lat == null || rider.lng == null) return;
      seen.add(rider.id);
      const [x, y] = project(rider.lat, rider.lng);
      const existing = layer.markers.get(rider.id);
      if (existing) {
        existing.setAttribute("transform", `translate(${x} ${y})`);
        const dot = existing.querySelector(".rider-dot");
        dot.setAttribute("class", rider.online ? "rider-dot" : "rider-dot idle");
      } else {
        // A rider came online since the last poll — add them without a rebuild.
        const merged = {
          riders: (data.riders || []),
          orders: (data.orders || []),
          stations: (data.stations || []),
        };
        return render(host, merged);
      }
    });
    layer.markers.forEach((node, id) => {
      if (!seen.has(id)) { node.remove(); layer.markers.delete(id); }
    });
  }

  /* zoom — shrinks the viewBox around the city centre, no tiles needed */
  function applyZoom(host, zoom) {
    const layer = layers.get(host);
    if (!layer) return;
    const z = Math.min(Math.max(zoom, 1), 3.2);
    zooms.set(host, z);
    const w = W / z;
    const h = H / z;
    layer.svg.setAttribute("viewBox", `${(W - w) / 2} ${(H - h) / 2} ${w} ${h}`);
  }

  function zoomBy(host, factor) {
    applyZoom(host, (zooms.get(host) || 1) * factor);
  }

  function resetZoom(host) {
    applyZoom(host, 1);
  }

  window.FCMap = { render, update, project, zoomBy, resetZoom };

  let scaleTimer = null;
  window.addEventListener("resize", () => {
    clearTimeout(scaleTimer);
    scaleTimer = setTimeout(() => {
      layers.forEach((layer, host) => publishScale(host, layer.svg));
    }, 180);
  });
})();
