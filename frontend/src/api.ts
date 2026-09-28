export let csrf = "";
export function setCsrf(value: string) {
  csrf = value;
}
export async function api(path: string, options: RequestInit = {}) {
  const response = await fetch("/api" + path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrf,
      ...options.headers,
    },
  });
  const data = await response
    .json()
    .catch(() => ({ detail: "Unexpected server response" }));
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail),
    );
  return data;
}
export const post = (path: string, body: unknown = {}) =>
  api(path, { method: "POST", body: JSON.stringify(body) });
export async function upload(
  caseId: string,
  file: File,
  roles: string[],
  progress: (percent: number) => void,
) {
  const key = `cpe-upload:${caseId}:${file.name}:${file.size}:${file.lastModified}`;
  let session;
  const saved = localStorage.getItem(key);
  if (saved) {
    const existing = await api(`/cases/${caseId}/uploads`);
    session = existing.find(
      (u: any) => u.id === saved && u.status === "Uploading" && !u.deleted,
    );
  }
  if (!session) {
    session = await post(`/cases/${caseId}/uploads`, {
      name: file.name,
      size: file.size,
      roles,
    });
    localStorage.setItem(key, session.id);
  }
  const chunk = session.chunk_bytes || 8 * 1024 * 1024;
  for (let offset = session.offset; offset < file.size;) {
    const response = await fetch(
      `/api/uploads/${session.id}/chunk?offset=${offset}`,
      {
        method: "PUT",
        headers: { "X-CSRF-Token": csrf },
        body: file.slice(offset, offset + chunk),
      },
    );
    if (!response.ok)
      throw new Error("Upload interrupted. Select the same file to resume.");
    const data = await response.json();
    offset = data.offset;
    progress(Math.round((offset / file.size) * 100));
  }
  await post(`/uploads/${session.id}/complete`);
  localStorage.removeItem(key);
}
