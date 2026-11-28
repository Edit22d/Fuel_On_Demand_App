/* Console behaviour: navigation, search, toasts, live polling, charts, map. */
(function () {
  "use strict";

  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  const nf = new Intl.NumberFormat("en-UG");
  const money = (v) => "UGX " + nf.format(Math.round(v || 0));
  const compact = (v) => {
    const n = Number(v || 0);
    if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(2).replace(/\.00$/, "") + "M";
    if (Math.abs(n) >= 1e3) return (n / 1e3).toFixed(1).replace(/\.0$/, "") + "K";
    return nf.format(n);
  };
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const ago = (iso) => {
    if (!iso) return "—";
    const diff = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
    if (diff < 60) return "just now";
    if (diff < 3600) return Math.floor(diff / 60) + "m ago";
    if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
    return Math.floor(diff / 86400) + "d ago";
  };
  const tone = {
    delivered: "ok", cancelled: "bad", pending_payment: "muted", confirmed: "gold",
    assigned: "info", picked_up: "violet", arrived: "teal",
  };
  const chip = (status, label) => `<span class="chip ${tone[status] || "muted"}">${esc(label)}</span>`;
  const iconTone = {
    delivered: "tone-green", cancelled: "tone-rose", pending_payment: "tone-sky",
    confirmed: "tone-gold", assigned: "tone-blue", picked_up: "tone-violet", arrived: "tone-teal",
  };
  const orderIcon = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" '
    + 'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M5 3h14v18l-2.5-1.6L14 21l-2-1.6L10 21l-2.5-1.6L5 21z"/>'
    + '<path d="M9 8h6M9 12h6"/></svg>';

  /* ---------------------------------------------------------------- sidebar */
  const menuBtn = $("[data-menu]");
  if (menuBtn) {
    menuBtn.addEventListener("click", () => document.body.classList.toggle("nav-open"));
  }
  document.addEventListener("click", (event) => {
    if (document.body.classList.contains("nav-open")) {
      const sidebar = $(".sidebar");
      if (sidebar && !sidebar.contains(event.target) && !(menuBtn && menuBtn.contains(event.target))) {
        document.body.classList.remove("nav-open");
      }
    }
  });

  /* ---------------------------------------------------------------- fullscreen */
  $$("[data-fullscreen]").forEach((button) => {
    button.addEventListener("click", () => {
      if (document.fullscreenElement) {
        document.exitFullscreen();
      } else if (document.documentElement.requestFullscreen) {
        document.documentElement.requestFullscreen().catch(() => {});
      }
    });
  });

  /* ---------------------------------------------------------------- toasts */
  $$(".toast").forEach((toast) => {
    setTimeout(() => {
      toast.classList.add("out");
      setTimeout(() => toast.remove(), 260);
    }, 5200);
    toast.addEventListener("click", () => toast.remove());
  });

  /* ---------------------------------------------------------------- confirm */
  $$("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });

  /* ---------------------------------------------------------------- password */
  $$("[data-password-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const input = document.getElementById(button.dataset.passwordToggle);
      if (!input) return;
      const showing = input.type === "text";
      input.type = showing ? "password" : "text";
      button.setAttribute("aria-label", showing ? "Show password" : "Hide password");
      button.dataset.showing = showing ? "" : "1";
    });
  });

  /* ---------------------------------------------------------------- search */
  const searchInput = $("#global-search");
  const searchBox = $("#search-results");
  let searchTimer = null;

  function renderResults(items) {
    if (!searchBox) return;
    if (!items.length) {
      searchBox.innerHTML = '<div class="empty">No matches</div>';
      searchBox.classList.add("open");
      return;
    }
    searchBox.innerHTML = items.map((item) =>
      `<a class="result" href="${esc(item.url)}"><span class="result-type">${esc(item.type)}</span>
       <span class="result-label">${esc(item.label)}</span>
       <span class="result-hint">${esc(item.hint || "")}</span></a>`
    ).join("");
    searchBox.classList.add("open");
  }

  if (searchInput) {
    searchInput.addEventListener("input", () => {
      const term = searchInput.value.trim();
      clearTimeout(searchTimer);
      if (term.length < 2) {
        searchBox.classList.remove("open");
        return;
      }
      searchTimer = setTimeout(async () => {
        try {
          const response = await fetch("/console/api/search/?q=" + encodeURIComponent(term), {
            headers: { Accept: "application/json" },
          });
          if (!response.ok) return;
          const data = await response.json();
          renderResults(data.results || []);
        } catch (error) { /* offline: leave the last results */ }
      }, 220);
    });

    searchInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        const first = searchBox && searchBox.querySelector("a.result");
        if (first) window.location.href = first.getAttribute("href");
      }
      if (event.key === "Escape") {
        searchBox.classList.remove("open");
        searchInput.blur();
      }
    });

    document.addEventListener("click", (event) => {
      if (searchBox && !searchBox.contains(event.target) && event.target !== searchInput) {
        searchBox.classList.remove("open");
      }
    });

    document.addEventListener("keydown", (event) => {
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
      if ((event.key === "/" && !typing) || ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k")) {
        event.preventDefault();
        searchInput.focus();
      }
    });
  }

  /* ---------------------------------------------------------------- charts */
  const chartData = new Map();

  function drawChart(host) {
    const data = chartData.get(host);
    if (!data) return;
    const kind = host.dataset.chart;
    if (kind === "line") {
      window.FCCharts.line(host, data, {
        height: Number(host.dataset.height || 250),
        valueKey: host.dataset.valueKey || "revenue",
        color: host.dataset.color || "#F5C72E",
        secondary: host.dataset.secondary || null,
        fill: host.dataset.fill === "1",
      });
    } else if (kind === "donut") {
      const key = host.dataset.valueKey || "count";
      window.FCCharts.donut(host, data.map((d) => ({ value: d[key], color: d.color })), {});
      const totalNode = host.parentElement.querySelector("[data-donut-total]");
      if (totalNode) {
        const total = data.reduce((sum, d) => sum + Number(d[key] || 0), 0);
        totalNode.textContent = nf.format(total);
      }
    } else if (kind === "spark") {
      window.FCCharts.spark(host, data, { color: host.dataset.color || "#55C68B" });
    }
  }

  $$("[data-chart]").forEach((host) => {
    const source = document.getElementById(host.dataset.source);
    if (!source || !window.FCCharts) return;
    let data;
    try { data = JSON.parse(source.textContent); } catch (error) { return; }
    chartData.set(host, data);
    drawChart(host);
  });

  /* Line charts are drawn to the pixel size of their card, so redraw them once
     the window settles instead of scaling a stale viewBox. */
  let chartTimer = null;
  window.addEventListener("resize", () => {
    clearTimeout(chartTimer);
    chartTimer = setTimeout(() => {
      chartData.forEach((data, host) => {
        if (host.dataset.chart === "line") drawChart(host);
      });
    }, 180);
  });

  /* ---------------------------------------------------------------- map */
  const mapHost = $("[data-map]");
  const mapSeed = $("#map-seed");
  let mapData = null;
  if (mapSeed) {
    try { mapData = JSON.parse(mapSeed.textContent); } catch (error) { mapData = null; }
  }
  if (mapHost && mapData && window.FCMap) {
    window.FCMap.render(mapHost, mapData);
  }

  $$("[data-map-zoom]").forEach((button) => {
    button.addEventListener("click", () => {
      if (!mapHost || !window.FCMap) return;
      window.FCMap.zoomBy(mapHost, button.dataset.mapZoom === "in" ? 1.35 : 1 / 1.35);
    });
  });
  $$("[data-map-reset]").forEach((button) => {
    button.addEventListener("click", () => {
      if (mapHost && window.FCMap) window.FCMap.resetZoom(mapHost);
    });
  });

  /* ---------------------------------------------------------------- the clock */
  const clockNode = $("[data-clock]");
  if (clockNode) {
    const tick = () => {
      clockNode.textContent = new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
    };
    tick();
    setInterval(tick, 20000);
  }

  /* ---------------------------------------------------------------- pulse */
  const refreshMs = Number(document.body.dataset.refresh || 5000);
  const pulseOn = document.body.dataset.pulse !== "off";
  const updatedNode = $("[data-updated]");
  const feedNode = $("[data-live-feed]");
  const ordersNode = $("[data-live-orders]");
  let failures = 0;

  function renderFeed(feed) {
    if (!feedNode) return;
    feedNode.innerHTML = feed.map((row) =>
      `<div class="feed-item">
         <span class="avatar">${esc(row.initials)}</span>
         <div class="feed-main">
           <div class="feed-title">${esc(row.number)} · ${esc(row.customer)}</div>
           <div class="feed-sub">${esc(row.station)} · ${esc(row.fuel)}</div>
         </div>
         <div class="feed-meta">
           ${chip(row.status, row.status_label)}
           <div class="tiny dim">${money(row.total)}</div>
         </div>
       </div>`
    ).join("") || '<div class="empty">No orders yet today.</div>';
  }

  function renderOrders(orders) {
    if (!ordersNode) return;
    const empty = '<div class="empty">No deliveries in progress.</div>';

    // the dashboard rail uses the compact operation rows
    if (ordersNode.classList.contains("op-list")) {
      ordersNode.innerHTML = orders.map((order) =>
        `<a class="op-row" href="/console/orders/${order.id}/">
           <span class="op-icon ${iconTone[order.status] || "tone-gold"}">${orderIcon}</span>
           <div class="op-main">
             <div class="op-title">${esc(order.number)}</div>
             <div class="op-sub">${esc(order.customer)} · ${esc(order.fuel)}</div>
           </div>
           <div class="op-meta">
             ${chip(order.status, order.status_label)}
             <span class="op-time">${order.age_minutes}m</span>
           </div>
         </a>`
      ).join("") || empty;
      return;
    }

    // the live board keeps its roomier tiles
    ordersNode.innerHTML = orders.map((order) =>
      `<a class="tile" href="/console/orders/${order.id}/" style="margin-bottom:10px">
         <span class="avatar">${esc(order.customer_initials || "")}</span>
         <div class="tile-main">
           <div class="tile-title">${esc(order.number)}</div>
           <div class="tile-sub">${esc(order.fuel)} · ${esc(order.address)}</div>
         </div>
         <div class="stack" style="align-items:flex-end">
           ${chip(order.status, order.status_label)}
           <span class="tiny dim">${order.age_minutes}m · ${money(order.total)}</span>
         </div>
       </a>`
    ).join("") || empty;
  }

  function setText(name, value) {
    $$(`[data-pulse="${name}"]`).forEach((node) => { node.textContent = value; });
  }

  function setDelta(name, value) {
    $$(`[data-delta="${name}"]`).forEach((node) => {
      const text = (value > 0 ? "+" : "") + value + "%";
      const state = value > 0 ? "up" : value < 0 ? "down" : "flat";
      if (node.classList.contains("stat-delta")) {
        node.className = "stat-delta " + state;
        node.innerHTML = `<i></i>${esc(text)}`;
      } else {
        node.className = "delta " + state;
        node.textContent = text;
      }
    });
  }

  function applyPulse(data) {
    const k = data.kpis;
    setText("revenue", k.revenue.display);
    setText("orders", k.orders.display);
    setText("active", k.active.display);
    setText("delivery_time", k.delivery_time.display);
    setText("riders", k.riders.display);
    setText("success", k.success.display);
    setText("customers", k.customers.display);
    setText("delivered", k.delivered.display);
    setText("on_time", k.on_time.display);
    setText("tankers", k.tankers.display);
    setText("stations", k.stations.display);
    setText("refunds", k.refunds.display);
    setDelta("revenue", k.revenue.delta);
    setDelta("orders", k.orders.delta);
    setDelta("delivered", k.delivered.delta);
    setDelta("on_time", k.on_time.delta);
    setDelta("customers", k.customers.delta);
    setText("online-riders", data.riders.filter((r) => r.online).length);
    setText("active-orders", data.orders.length);
    setText("unassigned", (data.kpis.alerts && data.kpis.alerts.total) || 0);
    if (feedNode) renderFeed(data.feed);
    if (ordersNode) renderOrders(data.orders);
    if (mapHost && window.FCMap && mapData) {
      window.FCMap.update(mapHost, Object.assign({}, mapData, { riders: data.riders, orders: data.orders }));
    }
    if (updatedNode) updatedNode.textContent = new Date().toLocaleTimeString("en-GB");
  }

  async function poll() {
    if (!pulseOn || document.hidden) return;
    try {
      const response = await fetch("/console/api/pulse/", { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("pulse " + response.status);
      applyPulse(await response.json());
      failures = 0;
      document.body.classList.remove("offline");
    } catch (error) {
      failures += 1;
      if (failures >= 3) document.body.classList.add("offline");
    }
  }

  if (pulseOn) {
    setTimeout(poll, 1200);
    setInterval(poll, Math.max(3000, refreshMs));
  }

  /* ---------------------------------------------------------------- boot */
  if (updatedNode) updatedNode.textContent = new Date().toLocaleTimeString("en-GB");
  document.documentElement.classList.add("ready");
})();
