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
  const TOKEN = "%(token)s";

  async function call(method, path, body) {
    const options = {
      method,
      headers: {
        "X-Desk-Token": TOKEN,
        "X-Desk-Widget-Id": WIDGET_ID,
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
    self: {
      getManifest: () => call("GET", "/api/bridge/self/getManifest"),
    },
  };
})();
"""


def render_bridge_client(widget_id: str, token: str) -> str:
    return BRIDGE_CLIENT_TEMPLATE % {"widget_id": widget_id, "token": token}
