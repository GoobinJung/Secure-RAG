(() => {
  const form = document.getElementById("question-form");
  const workspace = document.getElementById("chat-workspace");
  const thread = document.getElementById("chat-thread");
  const messages = document.getElementById("chat-messages");
  const empty = document.getElementById("empty-chat");
  const question = document.getElementById("question");
  const mode = document.getElementById("defense");
  const send = document.getElementById("ask-button");
  const clear = document.getElementById("new-chat");
  const error = document.getElementById("form-error");
  const context = document.body.dataset.sessionContext;
  let active = true;
  let busy = false;
  let generation = 0;
  let controller = null;

  clear.hidden = false;
  function setBusy(value) {
    busy = value;
    form.setAttribute("aria-busy", String(value));
    send.disabled = value || !active;
    clear.disabled = value || !active;
    mode.disabled = value || !active;
    question.readOnly = value || !active;
    send.textContent = value ? "Sending…" : "Send ↑";
  }
  function invalidate() {
    active = false;
    generation += 1;
    controller?.abort();
    messages.replaceChildren();
    question.value = "";
    workspace.hidden = true;
    document.getElementById("session-notice").hidden = false;
    setBusy(false);
  }
  async function checkSession() {
    if (!active) return false;
    try {
      const response = await fetch(form.dataset.sessionUrl, {cache: "no-store", credentials: "same-origin"});
      const data = await response.json();
      if (!response.ok || data.context !== context) {
        invalidate();
        return false;
      }
      return true;
    } catch {
      // A network failure must not be treated as a verified current session.
      return false;
    }
  }
  function showError(text) {
    error.textContent = text;
    error.hidden = false;
  }
  function pendingMessage(text) {
    const exchange = document.createElement("article");
    exchange.className = "chat-exchange";
    const user = document.createElement("div");
    user.className = "user-message";
    const label = document.createElement("p");
    label.className = "message-label";
    label.textContent = "You";
    const body = document.createElement("div");
    body.className = "question-text";
    body.textContent = text;
    user.append(label, body);
    const assistant = document.createElement("div");
    assistant.className = "assistant-message thinking-message";
    assistant.setAttribute("role", "status");
    assistant.textContent = "Thinking…";
    exchange.append(user, assistant);
    messages.append(exchange);
    empty.hidden = true;
    thread.scrollTop = thread.scrollHeight;
    return exchange;
  }
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (busy || !active) return;
    const data = new FormData(form);
    const text = String(data.get("question") || "").trim();
    if (!text || text.length > 2000) {
      showError("Enter a question between 1 and 2,000 characters.");
      return;
    }
    data.set("question", text);
    error.hidden = true;
    setBusy(true);
    const ticket = ++generation;
    const pending = pendingMessage(text);
    controller = new AbortController();
    try {
      if (!await checkSession()) {
        if (active) showError("Cannot verify your session. Check the connection and try again.");
        pending.remove();
        return;
      }
      const response = await fetch(form.dataset.chatUrl, {
        method: "POST", body: data, credentials: "same-origin", signal: controller.signal,
      });
      const reply = await response.json();
      if (ticket !== generation || !active) return;
      if (reply.reset_chat || response.status === 401) {
        invalidate();
        return;
      }
      if (!await checkSession() || ticket !== generation || !active) {
        pending.remove();
        if (active) showError("Cannot verify your session. Check the connection and try again.");
        return;
      }
      if (!reply.html) {
        pending.remove();
        showError(reply.error || "The request failed. Please try again.");
        return;
      }
      if (reply.context !== context) {
        invalidate();
        return;
      }
      // Only the server-rendered fragment is parsed as HTML. Model text is escaped by Jinja.
      const template = document.createElement("template");
      template.innerHTML = reply.html;
      pending.replaceWith(template.content);
      if (reply.ok) question.value = "";
      thread.scrollTop = thread.scrollHeight;
    } catch (failure) {
      pending.remove();
      if (failure.name !== "AbortError" && active) {
        showError("Cannot complete the request. Check the server connection and try again.");
      }
    } finally {
      if (ticket === generation && active) {
        setBusy(false);
        empty.hidden = messages.childElementCount !== 0;
        question.focus();
      }
    }
  });
  clear.addEventListener("click", () => {
    if (busy || !active) return;
    messages.replaceChildren();
    question.value = "";
    error.hidden = true;
    empty.hidden = false;
    question.focus();
  });
  question.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing && event.keyCode !== 229) {
      event.preventDefault();
      if (!busy && active) form.requestSubmit();
    }
  });
  document.querySelectorAll("[data-question]").forEach((button) => {
    button.addEventListener("click", () => {
      if (!busy && active) {
        question.value = button.dataset.question;
        question.focus();
      }
    });
  });
  window.addEventListener("rag-session-change", invalidate);
  window.addEventListener("focus", () => { void checkSession(); });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) void checkSession();
  });
  window.addEventListener("pagehide", () => {
    generation += 1;
    controller?.abort();
    messages.replaceChildren();
    question.value = "";
    workspace.hidden = true;
  });
  window.addEventListener("pageshow", async () => {
    if (await checkSession()) {
      workspace.hidden = false;
      setBusy(false);
      empty.hidden = messages.childElementCount !== 0;
    }
  });
})();
