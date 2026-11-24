// Broadcast only session changes. Questions and answers never enter browser storage.
(() => {
  const context = document.body.dataset.sessionContext;
  const channel = typeof BroadcastChannel === "function"
    ? new BroadcastChannel("secure-rag-session") : null;
  channel?.addEventListener("message", (event) => {
    if (event.data?.type === "session" && event.data.context !== context) {
      window.dispatchEvent(new Event("rag-session-change"));
    }
  });
  channel?.postMessage({type: "session", context});
  document.querySelector("[data-logout]")?.addEventListener("submit", () => {
    window.dispatchEvent(new Event("rag-session-change"));
    channel?.postMessage({type: "session", context: null});
  });
})();
