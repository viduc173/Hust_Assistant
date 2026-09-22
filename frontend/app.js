const chatWindow = document.getElementById("chat-window");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const sendBtn = document.getElementById("send-btn");
const themeToggle = document.getElementById("theme-toggle");
const threadList = document.getElementById("thread-list");
const newThreadBtn = document.getElementById("new-thread-btn");
const appShell = document.querySelector(".app-shell");
const sidebarToggle = document.getElementById("sidebar-toggle");
const sidebarOverlay = document.getElementById("sidebar-overlay");
const welcomeTemplate = document.getElementById("welcome-template");

// Neu backend chay tren port khac frontend, doi lai API_BASE cho phu hop.
const API_BASE = "";
const THREADS_KEY = "hust-rag-threads-v2";
const ACTIVE_KEY = "hust-rag-active-thread";
const LEGACY_KEY = "hust-rag-chat-v1"; // du lieu tu ban chua co nhieu thread

let threads = [];
let activeThreadId = null;

// ---------- Theme (per-viewer convenience, safe to fail silently) ----------
(function initTheme() {
  try {
    const saved = localStorage.getItem("hust-rag-theme");
    if (saved) document.documentElement.setAttribute("data-theme", saved);
  } catch (e) {}
})();

themeToggle.addEventListener("click", () => {
  const current = document.documentElement.getAttribute("data-theme");
  const isDark =
    current === "dark" ||
    (!current && window.matchMedia("(prefers-color-scheme: dark)").matches);
  const next = isDark ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  try {
    localStorage.setItem("hust-rag-theme", next);
  } catch (e) {}
});

// ---------- Sidebar (mobile off-canvas) ----------
function closeSidebarOnMobile() {
  appShell.classList.remove("sidebar-open");
}
sidebarToggle.addEventListener("click", () => appShell.classList.toggle("sidebar-open"));
sidebarOverlay.addEventListener("click", closeSidebarOnMobile);

// ---------- Markdown rendering ----------
function renderMarkdown(text) {
  if (window.marked && window.DOMPurify) {
    const html = marked.parse(text, { breaks: true });
    return DOMPurify.sanitize(html);
  }
  const escaped = text.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  return escaped.replace(/\n/g, "<br>");
}

function appendMessage(role, content, sources) {
  const wrapper = document.createElement("div");
  wrapper.className = `message ${role}`;

  const avatar = document.createElement("div");
  avatar.className = `avatar ${role === "user" ? "user-avatar" : "assistant-avatar"}`;
  avatar.textContent = role === "user" ? "🙋" : "🎓";
  wrapper.appendChild(avatar);

  const col = document.createElement("div");
  col.className = "bubble-col";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.innerHTML = renderMarkdown(content);
  col.appendChild(bubble);

  if (sources && sources.length > 0) {
    const src = document.createElement("div");
    src.className = "sources";
    const title = document.createElement("div");
    title.className = "sources-title";
    title.textContent = "Nguồn tham khảo";
    src.appendChild(title);
    sources.forEach((s) => {
      const link = document.createElement("a");
      link.href = s.url || "#";
      link.target = "_blank";
      link.rel = "noopener";
      link.textContent = s.title || s.url;
      src.appendChild(link);
    });
    col.appendChild(src);
  }

  wrapper.appendChild(col);
  chatWindow.appendChild(wrapper);
  chatWindow.scrollTop = chatWindow.scrollHeight;
  return wrapper;
}

function showTypingIndicator() {
  const wrapper = document.createElement("div");
  wrapper.className = "message assistant";
  wrapper.id = "typing-indicator";

  const avatar = document.createElement("div");
  avatar.className = "avatar assistant-avatar";
  avatar.textContent = "🎓";
  wrapper.appendChild(avatar);

  const col = document.createElement("div");
  col.className = "bubble-col";
  const bubble = document.createElement("div");
  bubble.className = "bubble typing-bubble";
  bubble.innerHTML = '<span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>';
  col.appendChild(bubble);
  wrapper.appendChild(col);

  chatWindow.appendChild(wrapper);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function removeTypingIndicator() {
  const el = document.getElementById("typing-indicator");
  if (el) el.remove();
}

function bindSuggestionChips() {
  chatWindow.querySelectorAll("#suggestions .chip").forEach((chip) => {
    chip.addEventListener("click", () => handleSend(chip.textContent));
  });
}

// ---------- Thread (multi-conversation) management ----------
function uid() {
  if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
  return `t_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function deriveTitle(text) {
  const clean = (text || "").replace(/\s+/g, " ").trim();
  if (!clean) return "Hội thoại mới";
  return clean.length > 42 ? clean.slice(0, 42) + "…" : clean;
}

function saveThreads() {
  try {
    localStorage.setItem(THREADS_KEY, JSON.stringify(threads));
    localStorage.setItem(ACTIVE_KEY, activeThreadId || "");
  } catch (e) {}
}

function migrateLegacyThread() {
  try {
    const raw = localStorage.getItem(LEGACY_KEY);
    localStorage.removeItem(LEGACY_KEY);
    if (!raw) return null;
    const log = JSON.parse(raw);
    if (!Array.isArray(log) || log.length === 0) return null;
    const firstUser = log.find((m) => m.role === "user");
    return {
      id: uid(),
      title: deriveTitle(firstUser ? firstUser.content : ""),
      messages: log,
      updatedAt: Date.now(),
    };
  } catch (e) {
    return null;
  }
}

function loadThreads() {
  try {
    const raw = localStorage.getItem(THREADS_KEY);
    threads = raw ? JSON.parse(raw) : [];
  } catch (e) {
    threads = [];
  }
  if (!Array.isArray(threads)) threads = [];

  if (threads.length === 0) {
    const migrated = migrateLegacyThread();
    if (migrated) threads.push(migrated);
  }

  try {
    activeThreadId = localStorage.getItem(ACTIVE_KEY);
  } catch (e) {
    activeThreadId = null;
  }
  if (!threads.some((t) => t.id === activeThreadId)) {
    activeThreadId = threads.length > 0 ? threads[0].id : null;
  }

  if (!activeThreadId) {
    const thread = { id: uid(), title: "Hội thoại mới", messages: [], updatedAt: Date.now() };
    threads.unshift(thread);
    activeThreadId = thread.id;
  }
  saveThreads();
}

function getActiveThread() {
  return threads.find((t) => t.id === activeThreadId) || null;
}

function renderChatWindow(thread) {
  chatWindow.innerHTML = "";
  if (!thread || thread.messages.length === 0) {
    chatWindow.appendChild(welcomeTemplate.content.cloneNode(true));
    bindSuggestionChips();
  } else {
    thread.messages.forEach((m) => appendMessage(m.role, m.content, m.sources));
  }
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function renderThreadList() {
  threadList.innerHTML = "";
  const sorted = [...threads].sort((a, b) => b.updatedAt - a.updatedAt);
  sorted.forEach((t) => {
    const item = document.createElement("div");
    item.className = `thread-item${t.id === activeThreadId ? " active" : ""}`;
    item.addEventListener("click", () => switchThread(t.id));

    const title = document.createElement("span");
    title.className = "thread-title";
    title.textContent = t.title || "Hội thoại mới";
    item.appendChild(title);

    const del = document.createElement("button");
    del.type = "button";
    del.className = "thread-delete";
    del.setAttribute("aria-label", "Xóa hội thoại");
    del.textContent = "✕";
    del.addEventListener("click", (e) => {
      e.stopPropagation();
      deleteThread(t.id);
    });
    item.appendChild(del);

    threadList.appendChild(item);
  });
}

function createThread() {
  const thread = { id: uid(), title: "Hội thoại mới", messages: [], updatedAt: Date.now() };
  threads.unshift(thread);
  activeThreadId = thread.id;
  saveThreads();
  renderThreadList();
  renderChatWindow(thread);
  closeSidebarOnMobile();
  chatInput.focus();
}

function switchThread(id) {
  if (id !== activeThreadId) {
    activeThreadId = id;
    saveThreads();
    renderThreadList();
    renderChatWindow(getActiveThread());
  }
  closeSidebarOnMobile();
}

function deleteThread(id) {
  const idx = threads.findIndex((t) => t.id === id);
  if (idx === -1) return;
  threads.splice(idx, 1);

  if (activeThreadId === id) {
    if (threads.length > 0) {
      activeThreadId = [...threads].sort((a, b) => b.updatedAt - a.updatedAt)[0].id;
    } else {
      const thread = { id: uid(), title: "Hội thoại mới", messages: [], updatedAt: Date.now() };
      threads.push(thread);
      activeThreadId = thread.id;
    }
  }
  saveThreads();
  renderThreadList();
  renderChatWindow(getActiveThread());
}

newThreadBtn.addEventListener("click", createThread);

// ---------- Gui tin nhan ----------
async function sendMessage(message, history) {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Lỗi server (${res.status})`);
  }

  return res.json();
}

async function handleSend(message) {
  if (!message.trim()) return;
  const thread = getActiveThread();
  if (!thread) return;

  const sugg = document.getElementById("suggestions");
  if (sugg) sugg.classList.add("hidden");

  appendMessage("user", message);
  const priorHistory = thread.messages.map((m) => ({ role: m.role, content: m.content }));
  thread.messages.push({ role: "user", content: message });
  if (thread.messages.filter((m) => m.role === "user").length === 1) {
    thread.title = deriveTitle(message);
  }
  thread.updatedAt = Date.now();
  saveThreads();
  renderThreadList();

  chatInput.value = "";
  autoResize();
  chatInput.disabled = true;
  sendBtn.disabled = true;
  showTypingIndicator();

  try {
    const data = await sendMessage(message, priorHistory);
    removeTypingIndicator();
    appendMessage("assistant", data.answer, data.sources);
    thread.messages.push({ role: "assistant", content: data.answer, sources: data.sources });
    thread.updatedAt = Date.now();
    saveThreads();
    renderThreadList();
  } catch (err) {
    removeTypingIndicator();
    appendMessage("assistant", `⚠️ Đã có lỗi xảy ra: ${err.message}`);
  } finally {
    chatInput.disabled = false;
    sendBtn.disabled = false;
    chatInput.focus();
  }
}

chatForm.addEventListener("submit", (e) => {
  e.preventDefault();
  handleSend(chatInput.value);
});

chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    handleSend(chatInput.value);
  }
});

function autoResize() {
  chatInput.style.height = "auto";
  chatInput.style.height = Math.min(chatInput.scrollHeight, 140) + "px";
}
chatInput.addEventListener("input", autoResize);

// ---------- Khoi tao ----------
loadThreads();
renderThreadList();
renderChatWindow(getActiveThread());
