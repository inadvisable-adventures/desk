"""The Desk Bridge API's client library, injected into every ChromiumWidget
page (see desk.shell.chromium_widget and plans/desk-bridge-api.md).

Deliberately plain JavaScript, not TypeScript/a build step: this is
built-in, always-shipped Desk infrastructure every "html" widget gets
unconditionally, not a Desk user's own custom widget code -- the same
reasoning already applied to the Console/Editor widgets being native-Qt
rather than Chromium (see design-docs/architecture.md's Key Design
Decisions). CLAUDE.md's "always use TypeScript in strict mode" for browser
code is about code a Desk user writes for their own kind:"html" widget.
"""

BRIDGE_CLIENT_TEMPLATE = """
(function () {
  const WIDGET_ID = "%(widget_id)s";
  const INSTANCE_ID = "%(instance_id)s";
  const TOKEN = "%(token)s";

  async function call(method, path, body) {
    const options = {
      method,
      headers: {
        "X-Desk-Token": TOKEN,
        "X-Desk-Widget-Id": WIDGET_ID,
        "X-Desk-Instance-Id": INSTANCE_ID,
      },
    };
    if (body !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    const response = await fetch(path, options);
    if (!response.ok) {
      const text = await response.text();
      throw new Error(`Desk Bridge ${path} failed (${response.status}): ${text}`);
    }
    return response.json();
  }

  // events.onMessage (TODO 6f9c51b): a long-poll loop, started lazily by
  // the first onMessage call and left running for the page's lifetime --
  // there's no offMessage in this first cut, since the whole page (and
  // its in-flight fetch) is torn down when the widget closes, so there's
  // nothing to leak in the common case.
  const eventListeners = [];
  let polling = false;

  async function pollEvents() {
    if (polling) return;
    polling = true;
    while (eventListeners.length > 0) {
      let event = null;
      try {
        ({ event } = await call("GET", "/api/bridge/events/poll?timeout=25"));
      } catch (e) {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        continue;
      }
      if (event) {
        for (const listener of eventListeners) {
          listener(event.name, event.payload, event.sender_instance_id);
        }
      }
    }
    polling = false;
  }

  window.desk = {
    workspace: {
      getState: () => call("GET", "/api/bridge/workspace/getState"),
    },
    fs: {
      readFile: (path) =>
        call("GET", `/api/bridge/fs/readFile?path=${encodeURIComponent(path)}`),
      writeFile: (path, contents) =>
        call("POST", "/api/bridge/fs/writeFile", { path, contents }),
    },
    widgets: {
      list: () => call("GET", "/api/bridge/widgets/list"),
      open: (widgetId, opts) =>
        call("POST", "/api/bridge/widgets/open", { widget_id: widgetId, ...(opts || {}) }),
      close: (instanceId) =>
        call("POST", "/api/bridge/widgets/close", { instance_id: instanceId }),
    },
    events: {
      subscribe: (names) => call("POST", "/api/bridge/events/subscribe", { names }),
      unsubscribe: (names) => call("POST", "/api/bridge/events/unsubscribe", { names }),
      publish: (name, payload) => call("POST", "/api/bridge/events/publish", { name, payload }),
      onMessage: (callback) => {
        eventListeners.push(callback);
        pollEvents();
      },
    },
    self: {
      getManifest: () => call("GET", "/api/bridge/self/getManifest"),
      getLocalStorage: () => call("GET", "/api/bridge/self/getLocalStorage"),
      setLocalStorage: (data) => call("POST", "/api/bridge/self/setLocalStorage", { data }),
    },
  };
})();
"""


def render_bridge_client(widget_id: str, instance_id: str, token: str) -> str:
    return BRIDGE_CLIENT_TEMPLATE % {"widget_id": widget_id, "instance_id": instance_id, "token": token}
