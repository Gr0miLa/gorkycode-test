const chat = document.querySelector("#chat");
const form = document.querySelector("#text-form");
const input = document.querySelector("#text-input");
const sendButton = document.querySelector("#send-button");
const recordButton = document.querySelector("#record-button");
const statusNode = document.querySelector("#status");
const speakToggle = document.querySelector("#speak-toggle");

const sessionId = getSessionId();
let recorder = null;
let stream = null;
let chunks = [];

function getSessionId() {
  let value = localStorage.getItem("assistant-session-id");
  if (!value) {
    value = createUuid();
    localStorage.setItem("assistant-session-id", value);
  }
  return value;
}

function createUuid() {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }
  if (globalThis.crypto?.getRandomValues) {
    const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0"));
    return [
      hex.slice(0, 4).join(""),
      hex.slice(4, 6).join(""),
      hex.slice(6, 8).join(""),
      hex.slice(8, 10).join(""),
      hex.slice(10, 16).join(""),
    ].join("-");
  }
  // Last-resort fallback for old browsers in an insecure local context.
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (char) => {
    const random = Math.floor(Math.random() * 16);
    const value = char === "x" ? random : (random & 0x3) | 0x8;
    return value.toString(16);
  });
}

function setBusy(busy, message = "Готов к работе") {
  input.disabled = busy;
  sendButton.disabled = busy;
  if (!recorder || recorder.state === "inactive") recordButton.disabled = busy;
  statusNode.textContent = message;
}

function addMessage(role, text, events = []) {
  const article = document.createElement("article");
  article.className = `message ${role}`;
  const p = document.createElement("p");
  p.textContent = text;
  article.appendChild(p);
  if (events.length) {
    const list = document.createElement("div");
    list.className = "events";
    for (const event of events) {
      const card = document.createElement("div");
      card.className = "event";
      const title = document.createElement("strong");
      title.textContent = event.title;
      const meta = document.createElement("small");
      meta.textContent = formatEvent(event);
      card.append(title, meta);
      list.appendChild(card);
    }
    article.appendChild(list);
  }
  chat.appendChild(article);
  chat.scrollTop = chat.scrollHeight;
}

function formatEvent(event) {
  const moment = event.starts_at || event.due_at;
  if (!moment && event.due_date) return `${event.type} · ${formatDateOnly(event.due_date)}`;
  if (!moment) return event.type;
  const date = new Date(moment);
  return `${event.type} · ${date.toLocaleString("ru-RU")}`;
}

function formatDateOnly(value) {
  return new Date(`${value}T00:00:00`).toLocaleDateString("ru-RU");
}

async function parseResponse(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "Не удалось обработать запрос");
  return data;
}

function showAssistantResult(data) {
  const events = data.created_event ? [data.created_event] : data.events;
  addMessage("assistant", data.reply, events || []);
  if (speakToggle.checked && "speechSynthesis" in window) {
    speechSynthesis.cancel();
    speechSynthesis.speak(new SpeechSynthesisUtterance(data.reply));
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  addMessage("user", text);
  input.value = "";
  setBusy(true, "Обрабатываю запрос…");
  try {
    const response = await fetch("/api/assistant/text", {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-Session-ID": sessionId},
      body: JSON.stringify({text}),
    });
    showAssistantResult(await parseResponse(response));
  } catch (error) {
    addMessage("assistant", `Ошибка: ${error.message}`);
  } finally {
    setBusy(false);
    input.focus();
  }
});

recordButton.addEventListener("click", async () => {
  if (recorder && recorder.state === "recording") {
    recorder.stop();
    return;
  }
  try {
    stream = await navigator.mediaDevices.getUserMedia({audio: true});
    chunks = [];
    recorder = new MediaRecorder(stream, {mimeType: "audio/webm;codecs=opus"});
    recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
    recorder.onstop = uploadRecording;
    recorder.start();
    recordButton.classList.add("recording");
    statusNode.textContent = "Идет запись… Нажмите ещё раз, чтобы остановить";
  } catch (error) {
    addMessage("assistant", "Не удалось получить доступ к микрофону.");
  }
});

async function uploadRecording() {
  recordButton.classList.remove("recording");
  stream?.getTracks().forEach((track) => track.stop());
  setBusy(true, "Распознаю запись…");
  try {
    const blob = new Blob(chunks, {type: "audio/webm"});
    const body = new FormData();
    body.append("audio", blob, "recording.webm");
    const response = await fetch("/api/assistant/audio", {
      method: "POST", headers: {"X-Session-ID": sessionId}, body,
    });
    const data = await parseResponse(response);
    addMessage("user", data.transcript || "Голосовое сообщение");
    showAssistantResult(data);
  } catch (error) {
    addMessage("assistant", `Ошибка: ${error.message}`);
  } finally {
    setBusy(false);
  }
}
