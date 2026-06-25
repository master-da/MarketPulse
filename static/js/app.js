/* MarketPulse terminal — vanilla JS client (no external libs). */
(() => {
  "use strict";

  const $ = (sel) => document.querySelector(sel);

  // ---------------- API helper ----------------
  const API = {
    async get(url) {
      const r = await fetch(url, { headers: { Accept: "application/json" } });
      if (!r.ok) throw new Error(`${r.status}`);
      return r.json();
    },
    async post(url, body) {
      const r = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          "X-CSRFToken": window.CSRF_TOKEN || "",
        },
        body: JSON.stringify(body || {}),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.detail || `Request failed (${r.status})`);
      return data;
    },
  };
  const rows = (d) => (Array.isArray(d) ? d : d.results || []);

  // ---------------- formatting ----------------
  const money = (v) =>
    "$" + Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const compact = (v) => {
    v = Number(v);
    if (Math.abs(v) >= 1e9) return "$" + (v / 1e9).toFixed(2) + "B";
    if (Math.abs(v) >= 1e6) return "$" + (v / 1e6).toFixed(2) + "M";
    if (Math.abs(v) >= 1e3) return "$" + (v / 1e3).toFixed(1) + "K";
    return money(v);
  };
  const pct = (v) => (v >= 0 ? "+" : "") + Number(v).toFixed(2) + "%";
  const signed = (v) => (v >= 0 ? "+" : "") + money(v);
  const cls = (v) => (v >= 0 ? "up" : "down");
  const time = (iso) => new Date(iso).toLocaleTimeString("en-US", { hour12: false });

  // ---------------- state ----------------
  const state = {
    instruments: {},   // symbol -> data
    order: [],         // symbol order
    selected: null,
    historyTicks: [],
  };

  // ---------------- canvas chart ----------------
  const canvas = $("#price-chart");
  function drawChart(ticks) {
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = Math.max(1, rect.width * dpr);
    canvas.height = Math.max(1, rect.height * dpr);
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const W = rect.width, H = rect.height;
    ctx.clearRect(0, 0, W, H);
    if (!ticks || ticks.length < 2) return;

    const prices = ticks.map((t) => parseFloat(t.price));
    let min = Math.min(...prices), max = Math.max(...prices);
    const pad = (max - min) * 0.15 || max * 0.02 || 1;
    min -= pad; max += pad;
    const up = prices[prices.length - 1] >= prices[0];
    const line = up ? "#1fd18a" : "#ff5d6c";

    const padL = 10, padR = 70, padT = 14, padB = 24;
    const plotW = W - padL - padR, plotH = H - padT - padB;
    const X = (i) => padL + (plotW * i) / (prices.length - 1);
    const Y = (p) => padT + plotH * (1 - (p - min) / (max - min || 1));

    // grid + y labels
    ctx.font = "11px monospace";
    ctx.textBaseline = "middle";
    for (let g = 0; g <= 4; g++) {
      const yy = padT + (plotH * g) / 4;
      const val = max - ((max - min) * g) / 4;
      ctx.strokeStyle = "rgba(31,43,61,.6)";
      ctx.beginPath(); ctx.moveTo(padL, yy); ctx.lineTo(padL + plotW, yy); ctx.stroke();
      ctx.fillStyle = "#7d8aa0";
      ctx.textAlign = "left";
      ctx.fillText(val.toFixed(2), padL + plotW + 8, yy);
    }

    // area fill
    const grad = ctx.createLinearGradient(0, padT, 0, padT + plotH);
    grad.addColorStop(0, up ? "rgba(31,209,138,.28)" : "rgba(255,93,108,.28)");
    grad.addColorStop(1, "rgba(0,0,0,0)");
    ctx.beginPath();
    ctx.moveTo(X(0), Y(prices[0]));
    prices.forEach((p, i) => ctx.lineTo(X(i), Y(p)));
    ctx.lineTo(X(prices.length - 1), padT + plotH);
    ctx.lineTo(X(0), padT + plotH);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    // price line
    ctx.beginPath();
    ctx.moveTo(X(0), Y(prices[0]));
    prices.forEach((p, i) => ctx.lineTo(X(i), Y(p)));
    ctx.lineWidth = 2;
    ctx.strokeStyle = line;
    ctx.stroke();

    // last point marker + label
    const lastX = X(prices.length - 1), lastY = Y(prices[prices.length - 1]);
    ctx.beginPath(); ctx.arc(lastX, lastY, 3.5, 0, Math.PI * 2);
    ctx.fillStyle = line; ctx.fill();
    ctx.fillStyle = line; ctx.textAlign = "left";
    ctx.fillText(prices[prices.length - 1].toFixed(2), Math.min(lastX + 8, padL + plotW + 8), lastY);

    // time axis
    ctx.fillStyle = "#7d8aa0"; ctx.textBaseline = "alphabetic";
    ctx.textAlign = "left";
    ctx.fillText(time(ticks[0].timestamp), padL, H - 6);
    ctx.textAlign = "right";
    ctx.fillText(time(ticks[ticks.length - 1].timestamp), padL + plotW, H - 6);
  }

  // ---------------- renderers ----------------
  function renderTicker() {
    const el = $("#ticker");
    el.innerHTML = state.order
      .map((sym) => {
        const i = state.instruments[sym];
        return `<span class="tick-item" data-sym="${sym}">
          <span class="sym">${sym}</span>
          <span class="px">${Number(i.last_price).toFixed(2)}</span>
          <span class="chg ${cls(i.change_pct)}">${pct(i.change_pct)}</span>
        </span>`;
      })
      .join("");
  }

  function renderWatchlist() {
    const el = $("#watchlist");
    $("#watchlist-count").textContent = `(${state.order.length})`;
    el.innerHTML = state.order
      .map((sym) => {
        const i = state.instruments[sym];
        const active = sym === state.selected ? " active" : "";
        return `<div class="wl-item${active}" data-sym="${sym}">
          <span class="wl-sym">${sym}</span>
          <span class="wl-px">${Number(i.last_price).toFixed(2)}</span>
          <span class="wl-name">${i.name}</span>
          <span class="wl-chg ${cls(i.change_pct)}">${pct(i.change_pct)}</span>
        </div>`;
      })
      .join("");
  }

  function renderSelectedHeader() {
    const i = state.instruments[state.selected];
    if (!i) return;
    $("#sel-symbol").textContent = i.symbol;
    $("#sel-name").textContent = i.name;
    $("#sel-price").textContent = money(i.last_price);
    const chg = $("#sel-change");
    chg.textContent = `${signed(i.change)} (${pct(i.change_pct)})`;
    chg.className = "chg " + cls(i.change_pct);
    $("#sel-high").textContent = Number(i.day_high).toFixed(2);
    $("#sel-low").textContent = Number(i.day_low).toFixed(2);
    $("#sel-vol").textContent = (i.volatility * 100).toFixed(2) + "%";
  }

  function renderPortfolio(p) {
    $("#pf-equity").textContent = money(p.equity);
    const ret = $("#pf-return");
    ret.textContent = pct(p.total_return_pct);
    ret.className = "chg " + cls(p.total_return_pct);
    $("#pf-cash").textContent = compact(p.cash_balance);
    $("#pf-holdings").textContent = compact(p.holdings_value);
    const u = $("#pf-unrealized"); u.textContent = signed(p.unrealized_pnl); u.className = "chg " + cls(p.unrealized_pnl);
    const r = $("#pf-realized"); r.textContent = signed(p.realized_pnl); r.className = "chg " + cls(p.realized_pnl);

    const el = $("#holdings");
    if (!p.holdings.length) { el.innerHTML = `<p class="empty">No positions.</p>`; return; }
    el.innerHTML = `<table><thead><tr>
        <th>Sym</th><th>Qty</th><th>Avg</th><th>Last</th><th>P&L</th>
      </tr></thead><tbody>${p.holdings
        .map((h) => `<tr>
          <td>${h.symbol}</td>
          <td>${h.quantity}</td>
          <td>${Number(h.avg_cost).toFixed(2)}</td>
          <td>${Number(h.last_price).toFixed(2)}</td>
          <td class="${cls(h.unrealized_pnl)}">${signed(h.unrealized_pnl)}<br>
            <small>${pct(h.unrealized_pnl_pct)}</small></td>
        </tr>`).join("")}</tbody></table>`;
  }

  function renderOrders(list) {
    const el = $("#orders");
    if (!list.length) { el.innerHTML = `<p class="empty">No orders yet.</p>`; return; }
    el.innerHTML = `<table><thead><tr>
        <th>Sym</th><th>Side</th><th>Qty</th><th>Type</th><th>Status</th><th></th>
      </tr></thead><tbody>${list.slice(0, 20)
        .map((o) => `<tr>
          <td>${o.symbol}</td>
          <td><span class="pill ${o.side.toLowerCase()}">${o.side}</span></td>
          <td>${o.quantity}</td>
          <td>${o.order_type === "LIMIT" ? "LMT " + Number(o.limit_price).toFixed(2) : "MKT"}</td>
          <td>${o.status}</td>
          <td>${o.status === "OPEN" ? `<span class="x-cancel" data-cancel="${o.id}">✕</span>` : ""}</td>
        </tr>`).join("")}</tbody></table>`;
  }

  function renderTrades(list) {
    const el = $("#trades");
    if (!list.length) { el.innerHTML = `<p class="empty">No trades yet.</p>`; return; }
    el.innerHTML = `<table><thead><tr>
        <th>Time</th><th>Sym</th><th>Side</th><th>Qty</th><th>Price</th>
      </tr></thead><tbody>${list.slice(0, 25)
        .map((t) => `<tr>
          <td>${time(t.timestamp)}</td>
          <td>${t.symbol}</td>
          <td><span class="pill ${t.side.toLowerCase()}">${t.side}</span></td>
          <td>${t.quantity}</td>
          <td>${Number(t.price).toFixed(2)}</td>
        </tr>`).join("")}</tbody></table>`;
  }

  function renderLeaderboard(list, me) {
    const el = $("#leaderboard");
    el.innerHTML = `<table><thead><tr>
        <th>#</th><th>Trader</th><th>Equity</th><th>Return</th>
      </tr></thead><tbody>${list
        .map((r) => `<tr>
          <td>${r.rank}</td>
          <td>${r.username}${r.username === me ? ' <span class="pill you">YOU</span>' : (r.is_bot ? ' <small class="muted">bot</small>' : "")}</td>
          <td>${compact(r.equity)}</td>
          <td class="${cls(r.return_pct)}">${pct(r.return_pct)}</td>
        </tr>`).join("")}</tbody></table>`;
  }

  // ---------------- engine status ----------------
  function renderEngine(s) {
    const dot = $("#engine-indicator"), label = $("#engine-label");
    if (s.running) {
      dot.className = "engine-dot live";
      label.textContent = `live · tick ${s.tick_count} · ${s.tick_interval}s`;
    } else {
      dot.className = "engine-dot down";
      label.textContent = "engine idle";
    }
  }

  // ---------------- selection ----------------
  let me = null;
  function selectSymbol(sym) {
    if (!state.instruments[sym]) return;
    state.selected = sym;
    $("#ot-symbol").value = sym;
    renderWatchlist();
    renderSelectedHeader();
    updateEstimate();
    loadHistory();
  }

  async function loadHistory() {
    if (!state.selected) return;
    try {
      const d = await API.get(`/api/instruments/${state.selected}/history/?limit=120`);
      state.historyTicks = d.ticks;
      drawChart(d.ticks);
    } catch (e) { /* ignore transient */ }
  }

  // ---------------- order ticket ----------------
  let side = "BUY", otype = "MARKET";
  function bindTicket() {
    document.querySelectorAll("#side-seg .seg-btn").forEach((b) =>
      b.addEventListener("click", () => {
        side = b.dataset.side;
        document.querySelectorAll("#side-seg .seg-btn").forEach((x) => x.classList.toggle("active", x === b));
        const submit = $("#ot-submit");
        submit.textContent = side === "BUY" ? "Buy" : "Sell";
        submit.className = "btn btn-block " + (side === "BUY" ? "btn-buy" : "btn-sell");
      })
    );
    document.querySelectorAll("#type-seg .seg-btn").forEach((b) =>
      b.addEventListener("click", () => {
        otype = b.dataset.type;
        document.querySelectorAll("#type-seg .seg-btn").forEach((x) => x.classList.toggle("active", x === b));
        $("#limit-row").hidden = otype !== "LIMIT";
        updateEstimate();
      })
    );
    $("#ot-symbol").addEventListener("input", (e) => {
      const sym = e.target.value.trim().toUpperCase();
      if (state.instruments[sym]) selectSymbol(sym);
      updateEstimate();
    });
    $("#ot-qty").addEventListener("input", updateEstimate);
    $("#ot-limit").addEventListener("input", updateEstimate);
    $("#order-form").addEventListener("submit", submitOrder);
  }

  function updateEstimate() {
    const sym = $("#ot-symbol").value.trim().toUpperCase();
    const qty = parseFloat($("#ot-qty").value) || 0;
    const inst = state.instruments[sym];
    let price = inst ? Number(inst.last_price) : 0;
    if (otype === "LIMIT") price = parseFloat($("#ot-limit").value) || price;
    $("#ot-est").textContent = price ? money(price * qty) : "—";
  }

  async function submitOrder(e) {
    e.preventDefault();
    const msg = $("#ot-msg");
    const payload = {
      symbol: $("#ot-symbol").value.trim().toUpperCase(),
      side,
      order_type: otype,
      quantity: parseInt($("#ot-qty").value, 10),
    };
    if (otype === "LIMIT") payload.limit_price = parseFloat($("#ot-limit").value);
    try {
      const o = await API.post("/api/orders/", payload);
      msg.className = "ot-msg ok";
      msg.textContent =
        o.status === "FILLED"
          ? `Filled ${o.quantity} ${o.symbol} @ ${Number(o.avg_fill_price).toFixed(2)}`
          : `Order ${o.status.toLowerCase()} · ${o.side} ${o.quantity} ${o.symbol}`;
      refreshAccount();
    } catch (err) {
      msg.className = "ot-msg err";
      msg.textContent = err.message;
    }
    setTimeout(() => { msg.textContent = ""; }, 4000);
  }

  async function cancelOrder(id) {
    try { await API.post(`/api/orders/${id}/cancel/`, {}); refreshAccount(); }
    catch (e) { /* ignore */ }
  }

  // ---------------- refresh cycles ----------------
  async function refreshMarket() {
    try {
      const data = await API.get("/api/instruments/");
      const list = rows(data);
      const seenOrder = [];
      list.forEach((i) => { state.instruments[i.symbol] = i; seenOrder.push(i.symbol); });
      state.order = seenOrder;
      if (!state.selected && state.order.length) selectSymbol(state.order[0]);
      renderTicker();
      renderWatchlist();
      renderSelectedHeader();
      updateEstimate();
    } catch (e) { /* ignore */ }
  }

  async function refreshAccount() {
    const [pf, orders, trades, lb] = await Promise.allSettled([
      API.get("/api/portfolio/"),
      API.get("/api/orders/"),
      API.get("/api/trades/"),
      API.get("/api/leaderboard/"),
    ]);
    if (pf.status === "fulfilled") { me = pf.value.username; renderPortfolio(pf.value); }
    if (orders.status === "fulfilled") renderOrders(rows(orders.value));
    if (trades.status === "fulfilled") renderTrades(rows(trades.value));
    if (lb.status === "fulfilled") renderLeaderboard(lb.value.leaderboard, me);
  }

  async function refreshStatus() {
    try { renderEngine(await API.get("/api/market/status/")); } catch (e) { /* ignore */ }
  }

  async function tick() {
    await refreshMarket();
    await loadHistory();
    refreshStatus();
  }

  // ---------------- event delegation ----------------
  function bindDelegates() {
    document.addEventListener("click", (e) => {
      const t = e.target.closest("[data-sym]");
      if (t) { selectSymbol(t.dataset.sym); return; }
      const c = e.target.closest("[data-cancel]");
      if (c) cancelOrder(c.dataset.cancel);
    });
    window.addEventListener("resize", () => drawChart(state.historyTicks));
  }

  // ---------------- boot ----------------
  async function boot() {
    bindTicket();
    bindDelegates();
    await refreshMarket();
    await loadHistory();
    await refreshAccount();
    await refreshStatus();
    setInterval(tick, 1500);
    setInterval(refreshAccount, 2000);
  }

  boot();
})();
