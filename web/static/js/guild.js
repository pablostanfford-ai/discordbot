/* Страница сервера: вкладки Overview / Модерация / Приветствия / AutoMod / Уровни / Логирование / Участники / Журнал */

const GUILD_ID = location.pathname.split("/").pop();
let SETTINGS = null;
let CHANNELS = [];
let ROLES = [];

const TABS = ["overview", "general", "welcome", "automod", "leveling", "logging", "members", "modlog"];

function switchTab(name) {
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab-panel").forEach(p => p.classList.toggle("hidden", p.id !== "tab-" + name));
  history.replaceState(null, "", "#" + name);
  if (name === "members") loadMembers();
  if (name === "modlog") loadModlog();
}

async function init() {
  try {
    const ov = await api(`/api/guilds/${GUILD_ID}/overview`);
    SETTINGS = ov.settings;
    renderHeader(ov.guild);
    renderStats(ov.stats);
    [CHANNELS, ROLES] = await Promise.all([
      api(`/api/guilds/${GUILD_ID}/channels`),
      api(`/api/guilds/${GUILD_ID}/roles`),
    ]);
    renderGeneral();
    renderWelcome();
    renderAutomod();
    renderLeveling();
    renderLogging();
    const tab = (location.hash || "#overview").slice(1);
    switchTab(TABS.includes(tab) ? tab : "overview");
  } catch (e) {
    document.getElementById("content-area").innerHTML =
      `<div class="card" style="color:var(--red)">Ошибка загрузки: ${e.message}</div>`;
  }
}

function renderHeader(g) {
  const el = document.getElementById("guild-header");
  const icon = g.icon ? `<img src="${g.icon}" alt="">` : (g.name[0] || "?").toUpperCase();
  el.innerHTML = `
    <div class="guild-header">
      <div class="guild-icon">${icon}</div>
      <div><h1>${g.name}</h1><span class="muted">${(g.member_count || 0).toLocaleString("ru")} участников · ID: ${g.id}</span></div>
    </div>`;
}

function renderStats(s) {
  const up = s.uptime_seconds || 0;
  const h = Math.floor(up / 3600), m = Math.floor((up % 3600) / 60);
  document.getElementById("tab-overview").innerHTML = `
    <div class="stats-grid">
      <div class="stat green"><div class="value">${s.members.toLocaleString("ru")}</div><div class="label">Участников</div></div>
      <div class="stat blue"><div class="value">${s.channels}</div><div class="label">Каналов</div></div>
      <div class="stat yellow"><div class="value">${s.roles}</div><div class="label">Ролей</div></div>
      <div class="stat red"><div class="value">${s.commands_used}</div><div class="label">Команд использовано</div></div>
      <div class="stat"><div class="value">${h}ч ${m}м</div><div class="label">Аптайм бота</div></div>
      <div class="stat"><div class="value" style="font-size:18px;padding-top:6px">${s.bot_online ? "🟢 Онлайн" : "🔴 Офлайн"}</div><div class="label">Статус бота</div></div>
    </div>
    <div class="card"><h2>⚡ Быстрое управление</h2>
      <p class="muted" style="margin-bottom:14px">Все настройки применяются мгновенно — бот перечитывает их при каждом событии.</p>
      <button class="btn small" onclick="switchTab('automod')">🛡️ Настроить AutoMod</button>
      <button class="btn small secondary" onclick="switchTab('welcome')">👋 Приветствия</button>
      <button class="btn small secondary" onclick="switchTab('leveling')">📈 Уровни</button>
      <a class="btn small discord" id="ov-invite" href="#" target="_blank" style="margin-left:6px">➕ Пригласить</a>
    </div>`;
  api("/api/bot/status").then(st => {
    const a = document.getElementById("ov-invite");
    if (a && st.invite_url) a.href = st.invite_url;
  });
}

// ---------- Сохранение ----------
async function savePatch(patch, msg = "💾 Сохранено") {
  // локально мержим
  deepMergeInto(SETTINGS, patch);
  try {
    await api(`/api/guilds/${GUILD_ID}/settings`, { method: "PATCH", body: JSON.stringify({ patch }) });
    toast(msg);
  } catch (e) { toast("❌ " + e.message, true); }
}

function deepMergeInto(base, patch) {
  for (const k in patch) {
    if (patch[k] && typeof patch[k] === "object" && !Array.isArray(patch[k])) {
      base[k] = base[k] || {};
      deepMergeInto(base[k], patch[k]);
    } else base[k] = patch[k];
  }
}

function channelSelect(id, selected, includeNone = true) {
  const opts = includeNone ? `<option value="">— не выбран —</option>` : "";
  return `<select id="${id}">${opts}${CHANNELS.map(c =>
    `<option value="${c.id}" ${String(selected) === String(c.id) ? "selected" : ""}>#${c.name}</option>`).join("")}</select>`;
}

function roleMultiOptions(selectedIds) {
  return ROLES.map(r => `<option value="${r.id}" ${selectedIds.includes(String(r.id)) ? "selected" : ""}>${r.name}</option>`).join("");
}

// ---------- General ----------
function renderGeneral() {
  document.getElementById("tab-general").innerHTML = `
  <div class="card"><h2>⚙️ Основные</h2>
    <div class="form-row"><label>Префикс команд</label>
      <input type="text" id="g-prefix" value="${SETTINGS.prefix}" maxlength="5"></div>
    ${toggleRow("Модуль «Модерация»", "modules.moderation", "gm-mod")}
    ${toggleRow("Модуль «AutoMod»", "modules.automod", "gm-automod")}
    ${toggleRow("Модуль «Приветствия»", "modules.welcome", "gm-welcome")}
    ${toggleRow("Модуль «Уровни»", "modules.leveling", "gm-level")}
    ${toggleRow("Модуль «Логирование»", "modules.logging", "gm-log")}
    <button class="btn" onclick="saveGeneral()">Сохранить</button>
  </div>`;
  setToggle("gm-mod", SETTINGS.modules.moderation);
  setToggle("gm-automod", SETTINGS.modules.automod);
  setToggle("gm-welcome", SETTINGS.modules.welcome);
  setToggle("gm-level", SETTINGS.modules.leveling);
  setToggle("gm-log", SETTINGS.modules.logging);
}

function toggleRow(label, path, id) {
  return `<div class="form-row inline"><label>${label}</label>
    <label class="switch"><input type="checkbox" id="${id}"><span class="slider"></span></label></div>`;
}
function setToggle(id, val) { const el = document.getElementById(id); if (el) el.checked = !!val; }
function getToggle(id) { const el = document.getElementById(id); return el ? el.checked : false; }

function saveGeneral() {
  savePatch({
    prefix: document.getElementById("g-prefix").value || "!",
    modules: {
      moderation: getToggle("gm-mod"), automod: getToggle("gm-automod"),
      welcome: getToggle("gm-welcome"), leveling: getToggle("gm-level"), logging: getToggle("gm-log"),
    },
  });
}

// ---------- Welcome ----------
function renderWelcome() {
  const w = SETTINGS.welcome;
  document.getElementById("tab-welcome").innerHTML = `
  <div class="card"><h2>👋 Приветствия</h2>
    ${toggleRow("Включить приветствия/провожания", "", "w-enabled")}
    <div class="form-row"><label>Канал приветствий</label>${channelSelect("w-channel", w.channel_id)}</div>
    <div class="form-row"><label>Текст приветствия <span class="muted">({user}, {mention}, {guild_name}, {server_count})</span></label>
      <textarea id="w-msg">${escapeHtml(w.message)}</textarea></div>
    <div class="form-row"><label>Текст прощания</label>
      <textarea id="w-leave">${escapeHtml(w.leave_message)}</textarea></div>
    <div class="form-row"><label>Цвет embed</label>
      <input type="text" id="w-color" value="${w.embed_color}" placeholder="#5865F2"></div>
    <div class="form-row"><label>Автороли при входе (Ctrl+клик — несколько)</label>
      <select id="w-roles" multiple size="5">${roleMultiOptions((w.autorole_ids || []).map(String))}</select></div>
    <button class="btn" onclick="saveWelcome()">Сохранить</button>
  </div>`;
  setToggle("w-enabled", w.enabled);
}

function saveWelcome() {
  const sel = document.getElementById("w-roles");
  savePatch({ welcome: {
    enabled: getToggle("w-enabled"),
    channel_id: document.getElementById("w-channel").value || null,
    message: document.getElementById("w-msg").value,
    leave_message: document.getElementById("w-leave").value,
    embed_color: document.getElementById("w-color").value || "#5865F2",
    autorole_ids: Array.from(sel.selectedOptions).map(o => o.value),
  }});
}

// ---------- AutoMod ----------
function renderAutomod() {
  const a = SETTINGS.automod;
  document.getElementById("tab-automod").innerHTML = `
  <div class="card"><h2>🛡️ AutoMod</h2>
    ${toggleRow("Включить AutoMod", "", "am-enabled")}
    <div class="form-row"><label>Максимум упоминаний в сообщении</label>
      <input type="number" id="am-mentions" value="${a.max_mentions}" min="1"></div>
    <div class="form-row"><label>Максимум ссылок</label>
      <input type="number" id="am-links" value="${a.max_links}" min="1"></div>
    <div class="form-row"><label>Наказание</label>
      <select id="am-action">
        ${["delete", "timeout", "kick", "warn"].map(v => `<option value="${v}" ${a.action === v ? "selected" : ""}>${{ delete: "Удаление сообщения", timeout: "Тайм-аут", kick: "Кик", warn: "Варн" }[v]}</option>`).join("")}
      </select></div>
    <div class="form-row"><label>Длительность тайм-аута (мин)</label>
      <input type="number" id="am-timeout" value="${a.timeout_minutes}" min="1" max="40320"></div>
    <div class="form-row"><label>Игнорируемые каналы</label>
      <select id="am-ignore" multiple size="4">${CHANNELS.map(c => `<option value="${c.id}" ${(a.ignore_channels || []).map(String).includes(String(c.id)) ? "selected" : ""}>#${c.name}</option>`).join("")}</select></div>
    <div class="form-row"><label>Запрещённые слова</label>
      <div style="display:flex;gap:8px"><input type="text" id="am-word-input" placeholder="новое слово…">
      <button class="btn small" onclick="addWord()">Добавить</button></div>
      <div class="chips" id="am-words"></div></div>
    <button class="btn" onclick="saveAutomod()">Сохранить</button>
  </div>`;
  setToggle("am-enabled", a.enabled);
  window._words = [...(a.banned_words || [])];
  renderWords();
}

function renderWords() {
  document.getElementById("am-words").innerHTML = window._words.map((w, i) =>
    `<span class="chip">${escapeHtml(w)}<button onclick="window._words.splice(${i},1);renderWords()">✕</button></span>`).join("") || '<span class="muted">пусто</span>';
}
function addWord() {
  const inp = document.getElementById("am-word-input");
  const v = inp.value.trim().toLowerCase();
  if (v && !window._words.includes(v)) { window._words.push(v); renderWords(); }
  inp.value = "";
}
function saveAutomod() {
  savePatch({ automod: {
    enabled: getToggle("am-enabled"),
    max_mentions: parseInt(document.getElementById("am-mentions").value) || 5,
    max_links: parseInt(document.getElementById("am-links").value) || 3,
    action: document.getElementById("am-action").value,
    timeout_minutes: parseInt(document.getElementById("am-timeout").value) || 10,
    banned_words: window._words,
    ignore_channels: Array.from(document.getElementById("am-ignore").selectedOptions).map(o => o.value),
  }});
}

// ---------- Leveling ----------
function renderLeveling() {
  const l = SETTINGS.leveling;
  document.getElementById("tab-leveling").innerHTML = `
  <div class="card"><h2>📈 Уровни и XP</h2>
    ${toggleRow("Включить систему уровней", "", "lv-enabled")}
    <div class="form-row"><label>XP за сообщение</label>
      <input type="number" id="lv-xp" value="${l.xp_per_message}" min="1"></div>
    <div class="form-row"><label>Пауза между начислениями (сек)</label>
      <input type="number" id="lv-cd" value="${l.cooldown_seconds}" min="0"></div>
    <div class="form-row"><label>Канал объявлений о повышении</label>${channelSelect("lv-ch", l.announce_channel_id)}</div>
    <div class="form-row"><label>Роль-награды (уровень → роль)</label>
      <div id="lv-rewards">${(l.role_rewards || []).map(r => rewardRow(r.level, r.role_id)).join("")}</div>
      <button class="btn small secondary" onclick="addReward()">+ Добавить награду</button></div>
    <button class="btn" onclick="saveLeveling()">Сохранить</button>
  </div>`;
  setToggle("lv-enabled", l.enabled);
}

function rewardRow(level, roleId) {
  return `<div class="lv-reward" style="display:flex;gap:8px;margin-bottom:8px">
    <input type="number" class="lv-lvl" value="${level}" min="1" style="width:90px" placeholder="Ур.">
    <select class="lv-role">${ROLES.map(r => `<option value="${r.id}" ${String(r.id) === String(roleId) ? "selected" : ""}>${r.name}</option>`).join("")}</select>
    <button class="btn small danger" onclick="this.parentElement.remove()">✕</button></div>`;
}
function addReward() {
  document.getElementById("lv-rewards").insertAdjacentHTML("beforeend", rewardRow(5, ROLES[0]?.id));
}
function saveLeveling() {
  const rewards = Array.from(document.querySelectorAll(".lv-reward")).map(el => ({
    level: parseInt(el.querySelector(".lv-lvl").value) || 1,
    role_id: el.querySelector(".lv-role").value,
  }));
  savePatch({ leveling: {
    enabled: getToggle("lv-enabled"),
    xp_per_message: parseInt(document.getElementById("lv-xp").value) || 5,
    cooldown_seconds: parseInt(document.getElementById("lv-cd").value) || 60,
    announce_channel_id: document.getElementById("lv-ch").value || null,
    role_rewards: rewards,
  }});
}

// ---------- Logging ----------
function renderLogging() {
  const lg = SETTINGS.logging;
  const evs = lg.events || [];
  document.getElementById("tab-logging").innerHTML = `
  <div class="card"><h2>📝 Логирование</h2>
    ${toggleRow("Включить логирование", "", "lg-enabled")}
    <div class="form-row"><label>Канал логов</label>${channelSelect("lg-ch", lg.channel_id)}</div>
    <div class="form-row"><label>События</label>
      ${evCheckbox("Редактирование сообщений", "message_edit", evs)}
      ${evCheckbox("Удаление сообщений", "message_delete", evs)}
      ${evCheckbox("Вход участника", "member_join", evs)}
      ${evCheckbox("Выход участника", "member_leave", evs)}
    </div>
    <button class="btn" onclick="saveLogging()">Сохранить</button>
  </div>`;
  setToggle("lg-enabled", lg.enabled);
}
function evCheckbox(label, val, checked) {
  return `<label style="display:flex;gap:8px;align-items:center;color:var(--text);font-weight:500;margin:4px 0">
    <input type="checkbox" class="lg-ev" value="${val}" ${checked.includes(val) ? "checked" : ""}> ${label}</label>`;
}
function saveLogging() {
  savePatch({ logging: {
    enabled: getToggle("lg-enabled"),
    channel_id: document.getElementById("lg-ch").value || null,
    events: Array.from(document.querySelectorAll(".lg-ev:checked")).map(c => c.value),
  }});
}

// ---------- Members ----------
async function loadMembers() {
  const el = document.getElementById("tab-members");
  el.innerHTML = `<div class="card"><h2>👥 Участники</h2><input type="text" id="m-search" placeholder="Поиск по имени…" oninput="debounceSearch()" style="margin-bottom:14px">
    <div id="m-table"><span class="spinner"></span></div></div>`;
  fetchMembers();
}
let _searchT;
function debounceSearch() { clearTimeout(_searchT); _searchT = setTimeout(fetchMembers, 350); }

async function fetchMembers() {
  const q = encodeURIComponent(document.getElementById("m-search")?.value || "");
  const ms = await api(`/api/guilds/${GUILD_ID}/members?limit=30&q=${q}`);
  document.getElementById("m-table").innerHTML = `<table>
    <tr><th>Участник</th><th>ID</th><th>Уровень</th><th>XP</th><th>Роли</th><th>Присоединился</th></tr>
    ${ms.map(m => `<tr>
      <td><div class="member-cell">${avatarHtml(m, 26)}<b>${escapeHtml(m.username)}</b>${m.bot ? ' <span class="pill owner">BOT</span>' : ""}</div></td>
      <td class="muted">${m.id}</td>
      <td>L${m.level}</td><td>${m.xp.toLocaleString("ru")}</td>
      <td>${(m.roles || []).slice(0, 3).map(r => `<span class="role-tag">${escapeHtml(r)}</span>`).join("")}</td>
      <td class="muted">${m.joined_at ? new Date(m.joined_at * 1000).toLocaleDateString("ru") : "—"}</td>
    </tr>`).join("")}</table>`;
}

// ---------- Modlog ----------
async function loadModlog() {
  const el = document.getElementById("tab-modlog");
  el.innerHTML = `<div class="card"><h2>🗂️ Журнал действий</h2><div id="ml-table"><span class="spinner"></span></div></div>`;
  const rows = await api(`/api/guilds/${GUILD_ID}/modlog?limit=50`);
  document.getElementById("ml-table").innerHTML = rows.length ? `<table>
    <tr><th>#</th><th>Действие</th><th>Цель</th><th>Модератор</th><th>Причина</th><th>Когда</th></tr>
    ${rows.map(a => `<tr>
      <td class="muted">${a.id}</td>
      <td><span class="action-badge action-${a.action}">${a.action}</span></td>
      <td>${escapeHtml(a.target_tag || a.target_id)}</td>
      <td>${escapeHtml(a.moderator_tag)}</td>
      <td class="muted">${escapeHtml(a.reason || "—")}</td>
      <td class="muted">${new Date(a.created_at * 1000).toLocaleString("ru")}</td>
    </tr>`).join("")}</table>` : '<p class="muted">Пока пусто. Действия модерации и AutoMod появятся здесь.</p>';
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".tab-btn").forEach(b => b.addEventListener("click", () => switchTab(b.dataset.tab)));
  init();
});
