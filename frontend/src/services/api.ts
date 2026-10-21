let csrfToken = "";
export function setCsrf(value: string) {
  csrfToken = value;
}
export async function api<T>(
  path: string,
  method = "GET",
  data?: unknown,
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    credentials: "same-origin",
    headers: {
      ...(data !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(method !== "GET" ? { "X-CSRF-Token": csrfToken } : {}),
    },
    body: data === undefined ? undefined : JSON.stringify(data),
  });
  if (!response.ok) {
    if (response.status === 401 && path !== "/auth/login")
      window.dispatchEvent(new Event("session-expired"));
    const result = await response.json().catch(() => ({}));
    throw new Error(result.detail || `Request failed (${response.status})`);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
export function uploadFirmware(
  form: FormData,
  progress: (percent: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", "/api/firmware/upload");
    request.setRequestHeader("X-CSRF-Token", csrfToken);
    request.upload.onprogress = (event) => {
      if (event.lengthComputable)
        progress(Math.round((event.loaded / event.total) * 100));
    };
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) resolve();
      else {
        let message = `Upload failed (${request.status})`;
        try {
          message = JSON.parse(request.responseText).detail || message;
        } catch {}
        reject(new Error(message));
      }
    };
    request.onerror = () =>
      reject(
        new Error(
          "Connection lost during upload. Check the firmware list before retrying.",
        ),
      );
    request.send(form);
  });
}
export function requestKey() {
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (n) =>
    n.toString(16).padStart(2, "0"),
  ).join("");
}
