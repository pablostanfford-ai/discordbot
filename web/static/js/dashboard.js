/* Дашборд: список серверов пользователя */

async function loadGuilds() {
  const grid = document.getElementById("guilds-grid");
  grid.innerHTML = '<div class="muted" style="padding:20px"><span class="spinner"></span> Загрузка серверов…</div>';
  try {
    const guilds = await api("/api/users/guilds");
    if (!guilds.length) {
      grid.innerHTML = `<div class="card" style="grid-column:1/-1;text-align:center">
        <h2>😕 Серверов не найдено</h2>
        <p class="muted">Пригласите бота на свой сервер, чтобы управлять им отсюда.</p>
        <br><a class="btn" id="invite-btn" href="#" target="_blank">➕ Пригласить бота</a>
      </div>`;
    } else {
      grid.innerHTML = guilds.map(g => {
        const offline = g.bot_present === false;
        const icon = g.icon
          ? `<img src="${g.icon}" alt="">`
          : (g.name[0] || "?").toUpperCase();
        return `
        <div class="guild-card ${offline ? "offline" : ""}" ${offline ? "" : `onclick="location.href='/guild/${g.id}'"`}>
          <div class="guild-icon">${icon}</div>
          <div class="guild-meta">
            <h3>${g.name}</h3>
            <span>${g.member_count ? g.member_count.toLocaleString("ru") + " участников" : ""}</span>
            ${g.owner ? '<span class="pill owner">Владелец</span>' : ""}
            ${offline ? '<span class="pill nobot">Бот не добавлен</span>' : ""}
          </div>
        </div>`;
      }).join("");
    }
    const st = await api("/api/bot/status");
    const btn = document.getElementById("invite-btn");
    if (btn && st.invite_url) btn.href = st.invite_url;
    const statusEl = document.getElementById("bot-status");
    if (statusEl) {
      statusEl.innerHTML = st.demo
        ? `<span class="pill" style="background:rgba(254,231,92,.12);color:var(--yellow)">ДЕМО-РЕЖИМ</span>`
        : `<span class="pill owner">${st.online ? "Бот онлайн" : "Бот офлайн"}</span> · Гильдий: ${st.guilds}`;
    }
  } catch (e) {
    grid.innerHTML = `<div class="card" style="grid-column:1/-1;color:var(--red)">Ошибка: ${e.message}</div>`;
  }
}

document.addEventListener("DOMContentLoaded", loadGuilds);
