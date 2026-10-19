/* Общая часть: навбар, пользователь, toast-уведомления */

async function api(path, options = {}) {
  const resp = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    credentials: "same-origin",
    ...options,
  });
  if (resp.status === 401) {
    location.href = "/login";
    throw new Error("Не авторизован");
  }
  if (!resp.ok) {
    let msg = `Ошибка ${resp.status}`;
    try { msg = (await resp.json()).error || msg; } catch {}
    throw new Error(msg);
  }
  return resp.json();
}

function toast(text, isError = false) {
  let el = document.getElementById("toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "toast";
    document.body.appendChild(el);
  }
  el.textContent = text;
  el.className = isError ? "show error" : "show";
  clearTimeout(el._t);
  el._t = setTimeout(() => (el.className = ""), 3200);
}

function avatarHtml(user, size = 30) {
  if (user.avatar_url) {
    return `<img src="${user.avatar_url}" style="width:${size}px;height:${size}px;border-radius:50%;object-fit:cover" alt="">`;
  }
  const color = user.avatar_color ? "#" + user.avatar_color : undefined;
  const bg = color ? `background:linear-gradient(135deg,${color},#3d4a8f)` : "";
  return `<span class="avatar" style="width:${size}px;height:${size}px;font-size:${size * 0.42}px;${bg}">${(user.username || "?")[0].toUpperCase()}</span>`;
}

async function renderNavbar() {
  const el = document.getElementById("navbar");
  if (!el) return;
  let user = null;
  try { user = await api("/api/users/@me"); } catch {}
  el.innerHTML = `
    <nav class="navbar container">
      <a class="brand" href="/"><span class="logo">⚡</span> UniDash</a>
      <div class="nav-links">
        <a href="/">Главная</a>
        <a href="/dashboard">Панель</a>
        ${user ? `
          <div class="user-chip" onclick="logout()">
            ${avatarHtml(user)}
            <span>${user.username}</span>
          </div>` : `<a class="btn small discord" href="/api/auth/login">Войти через Discord</a>`}
      </div>
    </nav>`;
}

async function logout() {
  await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
  location.href = "/";
}

document.addEventListener("DOMContentLoaded", renderNavbar);
