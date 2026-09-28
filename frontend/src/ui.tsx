import React from "react";
import { FolderOpen } from "lucide-react";
export function Badge({ children }: { children: React.ReactNode }) {
  const s = String(children);
  return (
    <span
      className={
        "badge " +
        (/fail|error|reject|degrad/i.test(s)
          ? "danger"
          : /ready|healthy|approved|complete/i.test(s)
            ? "good"
            : "")
      }
    >
      {children}
    </span>
  );
}
export function Empty({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="empty">
      <FolderOpen size={32} />
      <h3>{title}</h3>
      <p>{detail}</p>
    </div>
  );
}
