import React from "react";
import { Badge, Empty } from "./ui";

export function ProductInventory({ products }: { products: unknown[] }) {
  const records = products.filter(
    (p): p is Record<string, unknown> =>
      typeof p === "object" && p !== null && !Array.isArray(p),
  );
  const label = (v: unknown, fallback: string) =>
    typeof v === "string" || typeof v === "number" ? String(v) : fallback;
  return (
    <>
      <div className="section-title">
        <h2>Deployed products & versions</h2>
        <span className="subtle">Captured inventory</span>
      </div>
      <div className="panel product-inventory">
        {records.length ? (
          records.map((p, i) => (
            <div className="product-record" key={i}>
              <div>
                <strong>{label(p.name, "Unnamed component")}</strong>
                <small>{label(p.note, "Version from uploaded snapshot")}</small>
              </div>
              <Badge>{label(p.version, "Unknown")}</Badge>
            </div>
          ))
        ) : (
          <Empty
            title="Product versions not supplied"
            detail="Include product names and versions in the cluster snapshot. Container images are listed with the pods below."
          />
        )}
      </div>
    </>
  );
}

export function ContainerInventory({
  containers,
}: {
  containers: Record<string, any>[];
}) {
  return (
    <div className="container-inventory">
      {containers.map((c, i) => {
        const state = c.state || {};
        const reason = state.waiting?.reason || state.terminated?.reason;
        const label =
          reason ||
          (state.running ? (c.ready ? "Ready" : "Not ready") : "Unknown");
        return (
          <div className="container-record" key={i}>
            <strong>{String(c.name || "Unnamed container")}</strong>
            <small>{String(c.image || "Image version unknown")}</small>
            <small
              className={
                state.waiting || (state.terminated && reason !== "Completed")
                  ? "container-failure"
                  : ""
              }
            >
              {String(label)} · {Number(c.restartCount) || 0} restarts
            </small>
          </div>
        );
      })}
      {!containers.length && <small>Container status not captured</small>}
    </div>
  );
}
