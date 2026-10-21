/* Telegram HelpDesk Mini App — клиентская логика (vanilla JS) */
(() => {
  "use strict";

  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  if (tg) {
    tg.ready();
    tg.expand();
    try { tg.setHeaderColor("#17212b"); tg.setBackgroundColor("#0e1621"); } catch (e) {}
  }

  const $ = (sel) => document.querySelector(sel);
  const el = {
    login: $("#screen-login"), main: $("#screen-main"),
    connectBtn: $("#btn-connect"), seedBtn: $("#btn-seed"), loginError: $("#login-error"),
    back: $("#btn-back"), refresh: $("#btn-refresh"),
    title: $("#view-title"), sub: $("#view-sub"),
    stats: $("#stats-row"), search: $("#search"), tabs: $("#status-tabs"),
    list: $("#ticket-list"),
    viewList: $("#view-list"), viewChat: $("#view-chat"),
    chatInfo: $("#chat-info"), chatMsgs: $("#chat-messages"),
    replyForm: $("#reply-form"), replyText: $("#reply-text"),
    actions: document.querySelector(".chat-actions"),
  };

  const CATS = {
    login: "🔑 Вход", network: "🌐 Сеть", payment: "💳 Оплата", bug: "🐛 Баг", other: "📩 Другое",
  };
  const STATUS_LABEL = {
    open: "Новый", in_progress: "В работе", answered: "Отвечено", closed: "Закрыт",
  };

  let currentStatus = "all";
  let currentSearch = "";
  let currentTicketId = null;
  let pollTimer = null;

  // ---------- helpers ----------
  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function fmtTime(ts) {
    const d = new Date(ts * 1000), now = new Date();
    const sameDay = d.toDateString() === now.toDateString();
    const hm = d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
    return sameDay ? hm : d.toLocaleDateString("ru-RU", { day: "2-digit", month: "short" }) + " " + hm;
  }

  function toast(msg) {
    const t = document.createElement("div");
    t.className = "toast"; t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 2600);
    if (tg && tg.HapticFeedback) { try { tg.HapticFeedback.notificationOccurred("success"); } catch (e) {} }
  }

  async function api(path, opts = {}) {
    const res = await fetch(path, {
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      ...opts,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw Object.assign(new Error(data.error || res.statusText), { status: res.status });
    return data;
  }

  // ---------- auth ----------
  async function tryAuth() {
    // 1. уже есть сессия?
    try {
      const me = await api("/api/me");
      enterPanel(me);
      return;
    } catch (e) { /* нет сессии */ }

    // 2. initData из Telegram
    const initData = tg && tg.initData ? tg.initData : "";
    if (initData) {
      try {
        const r = await api("/api/auth", { method: "POST", body: JSON.stringify({ init_data: initData }) });
        enterPanel(r.user);
        return;
      } catch (e) {
        showError(e.message);
      }
    } else {
      // вне Telegram — dev-режим
      el.connectBtn.classList.remove("hidden");
      el.seedBtn.classList.remove("hidden");
      $("#login-hint").textContent =
        "Вы открыли панель не из Telegram. В продакшене доступ только через кнопку бота. " +
        "Для локальной разработки можно войти демо-оператором.";
    }
  }

  function showError(msg) {
    el.loginError.textContent = msg;
    el.loginError.classList.remove("hidden");
  }

  el.connectBtn.addEventListener("click", async () => {
    // dev-логин: фейковый admin-пользователь (сервер без WEBAPP_SECRET доверяет initData)
    const fake = "auth_date=" + Math.floor(Date.now() / 1000) +
      "&query_id=DEV&user=" + encodeURIComponent(JSON.stringify(
        { id: 111111111, first_name: "Dev", username: "dev_operator", full_name: "Dev Operator" }));
    try {
      const r = await api("/api/auth", { method: "POST", body: JSON.stringify({ init_data: fake }) });
      enterPanel(r.user);
    } catch (e) { showError(e.message); }
  });

  el.seedBtn.addEventListener("click", async () => {
    try {
      await api("/api/demo/seed", { method: "POST" });
      toast("Созданы демо-тикеты");
    } catch (e) { showError(e.message); }
  });

  // ---------- panel ----------
  function enterPanel(user) {
    el.login.classList.add("hidden");
    el.main.classList.remove("hidden");
    el.sub.textContent = user.full_name || user.username || "Оператор";
    loadTickets();
    startPolling();
    // deep-link ?ticket=<id> — открыть сразу чат
    const params = new URLSearchParams(location.search);
    const tid = params.get("ticket");
    if (tid) openTicket(tid);
  }

  async function loadTickets() {
    try {
      const q = new URLSearchParams({ status: currentStatus, search: currentSearch });
      const data = await api("/api/tickets?" + q.toString());
      renderStats(data.stats);
      renderList(data.tickets);
    } catch (e) {
      if (e.status === 401) { location.reload(); return; }
      el.list.innerHTML = `<div class="empty">Ошибка: ${esc(e.message)}</div>`;
    }
  }

  function renderStats(s) {
    const b = s.by_status || {};
    el.stats.innerHTML = `
      <div class="stat"><b>${s.total}</b><span>всего</span></div>
      <div class="stat"><b style="color:var(--blue)">${b.open || 0}</b><span>новые</span></div>
      <div class="stat"><b style="color:var(--yellow)">${b.in_progress || 0}</b><span>в работе</span></div>
      <div class="stat"><b style="color:var(--green)">${b.answered || 0}</b><span>отвечено</span></div>
      <div class="stat"><b>${s.unread_messages}</b><span>нечитанных</span></div>`;
  }

  function renderList(rows) {
    if (!rows.length) { el.list.innerHTML = '<div class="empty">Тикетов нет 🎉</div>'; return; }
    el.list.innerHTML = rows.map((t) => `
      <div class="ticket-card" data-id="${t.id}">
        <div class="tc-top">
          <span class="tc-num">#${t.number}</span>
          <span class="tc-user">${esc(t.user)}${t.username ? " <span class='dim'>@" + esc(t.username) + "</span>" : ""}</span>
          <span class="tc-time">${fmtTime(t.updated_at)}</span>
        </div>
        <div class="tc-last">${t.last_author === "agent" ? "<b>Вы:</b> " : ""}${esc(t.last_message)}</div>
        <div class="tc-bottom">
          <span class="badge ${t.status}">${STATUS_LABEL[t.status] || t.status}</span>
          <span class="cat-tag">${CATS[t.category] || esc(t.category)}</span>
          ${t.unread_agent ? `<span class="unread">${t.unread_agent}</span>` : ""}
        </div>
      </div>`).join("");
    el.list.querySelectorAll(".ticket-card").forEach((card) =>
      card.addEventListener("click", () => openTicket(card.dataset.id)));
  }

  // ---------- tabs / search / refresh ----------
  el.tabs.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".tab");
    if (!btn) return;
    el.tabs.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    currentStatus = btn.dataset.status;
    loadTickets();
  });

  let searchTimer = null;
  el.search.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => { currentSearch = el.search.value.trim(); loadTickets(); }, 350);
  });

  el.refresh.addEventListener("click", () => {
    if (currentTicketId) refreshChat(true); else loadTickets();
  });

  // ---------- чат ----------
  async function openTicket(id) {
    currentTicketId = id;
    el.viewList.classList.add("hidden");
    el.viewChat.classList.remove("hidden");
    el.back.classList.remove("hidden");
    el.title.textContent = "Тикет";
    refreshChat(false);
  }

  async function refreshChat(silent) {
    if (!currentTicketId) return;
    try {
      const { ticket } = await api(`/api/tickets/${currentTicketId}`);
      renderChat(ticket);
      if (!silent) loadTicketsSoon();
    } catch (e) {
      if (!silent) toast("Ошибка: " + e.message);
    }
  }

  function loadTicketsSoon() { /* список обновится по polling */ }

  function renderChat(t) {
    el.title.textContent = `#${t.number} · ${t.full_name}`;
    el.chatInfo.innerHTML = `
      <div class="row">
        <span>👤 ${esc(t.full_name)}${t.username ? " <span class='dim'>@" + esc(t.username) + "</span>" : ""}
              <span class="dim">(id ${t.user_id})</span></span>
        <span class="badge ${t.status}">${STATUS_LABEL[t.status] || t.status}</span>
      </div>
      <div class="row" style="margin-top:4px">
        <span class="dim">${CATS[t.category] || esc(t.category)} · создан ${fmtTime(t.created_at)}</span>
      </div>`;

    const prevLen = el.chatMsgs.scrollHeight + el.chatMsgs.scrollTop;
    el.chatMsgs.innerHTML = t.messages.map((m) => `
      <div class="msg ${m.author}">${esc(m.text)}<small>${fmtTime(m.ts)}</small></div>`).join("") +
      (t.status === "closed" ? '<div class="msg system">Тикет закрыт. Ответьте — он снова откроется.</div>' : "");
    el.chatMsgs.scrollTop = el.chatMsgs.scrollHeight;

    // скрыть неактуальные кнопки статусов
    el.actions.querySelectorAll("[data-set-status]").forEach((b) => {
      b.classList.toggle("hidden", b.dataset.setStatus === t.status);
    });
  }

  el.back.addEventListener("click", () => {
    currentTicketId = null;
    el.viewChat.classList.add("hidden");
    el.viewList.classList.remove("hidden");
    el.back.classList.add("hidden");
    el.title.textContent = "Тикеты";
    history.replaceState(null, "", location.pathname);
    loadTickets();
  });

  el.replyForm.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const text = el.replyText.value.trim();
    if (!text || !currentTicketId) return;
    el.replyText.value = "";
    try {
      const r = await api(`/api/tickets/${currentTicketId}/reply`, {
        method: "POST", body: JSON.stringify({ text }),
      });
      renderChat(r.ticket);
      toast(r.delivered ? "✅ Отправлено клиенту в Telegram" : "Сохранено (клиент недоступен)");
    } catch (e) {
      toast("Ошибка: " + e.message);
      el.replyText.value = text;
    }
  });

  el.actions.addEventListener("click", async (ev) => {
    const btn = ev.target.closest("[data-set-status]");
    if (!btn || !currentTicketId) return;
    try {
      const r = await api(`/api/tickets/${currentTicketId}/status`, {
        method: "POST", body: JSON.stringify({ status: btn.dataset.setStatus }),
      });
      renderChat(r.ticket);
      toast("Статус обновлён");
    } catch (e) { toast("Ошибка: " + e.message); }
  });

  // Ctrl+Enter отправить
  el.replyText.addEventListener("keydown", (ev) => {
    if ((ev.ctrlKey || ev.metaKey) && ev.key === "Enter") el.replyForm.requestSubmit();
  });

  // ---------- polling (раз в 5 секунд, только когда вкладка видима) ----------
  function startPolling() {
    clearInterval(pollTimer);
    pollTimer = setInterval(() => {
      if (document.hidden) return;
      if (currentTicketId) refreshChat(true); else loadTickets();
    }, 5000);
  }
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && !el.main.classList.contains("hidden")) {
      if (currentTicketId) refreshChat(true); else loadTickets();
    }
  });

  try {
    tg && tg.onEvent ? tg.onEvent("themeChanged", () => {}) : null;
  } catch (e) {}

  tryAuth();
})();
