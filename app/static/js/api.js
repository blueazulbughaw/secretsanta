// Tiny fetch wrapper. All requests same-origin with the auth cookie.
const api = {
  async call(method, path, body) {
    const opts = { method, headers: {}, credentials: "same-origin" };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const res = await fetch("/api" + path, opts);
    let data = {};
    try { data = await res.json(); } catch (_) {}
    if (!res.ok) {
      const err = new Error(data.error || "Something went wrong. Please try again.");
      err.status = res.status;
      throw err;
    }
    return data;
  },
  get:   (p)    => api.call("GET", p),
  post:  (p, b) => api.call("POST", p, b || {}),
  put:   (p, b) => api.call("PUT", p, b || {}),
  patch: (p, b) => api.call("PATCH", p, b || {}),
  del:   (p)    => api.call("DELETE", p),
  async postForm(path, formData) {
    const res = await fetch("/api" + path, { method: "POST", credentials: "same-origin", body: formData });
    let data = {};
    try { data = await res.json(); } catch (_) {}
    if (!res.ok) {
      const err = new Error(data.error || "Something went wrong. Please try again.");
      err.status = res.status;
      throw err;
    }
    return data;
  },
};
