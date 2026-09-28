import React from "react";

export function StorageEvidenceHelp({ run }: { run: Record<string, any> }) {
  if (
    !run.coverage?.gaps?.some((g: string) =>
      g.includes("backing PV/NFS export not verified"),
    )
  )
    return null;
  const mappings = (run.config?.archive_path_mappings || []).filter(
    (m: any) =>
      typeof m.namespace === "string" &&
      typeof m.pvc_claim === "string" &&
      /^[a-z0-9][a-z0-9.-]*$/.test(m.namespace) &&
      /^[a-z0-9][a-z0-9.-]*$/.test(m.pvc_claim),
  );
  const unique = [
    ...new Map<string, any>(
      mappings.map((m: any) => [`${m.namespace}/${m.pvc_claim}`, m]),
    ).values(),
  ];
  return (
    <div className="storage-evidence-help">
      <strong>Product-log analysis can continue</strong>
      <p>
        The pod description and archive mapping locate the product logs. This
        warning only means the backing storage has not been independently
        verified; it does not establish a storage failure.
      </p>
      <p>
        To verify it, collect the PVC and its bound PV from the same capture
        window, then upload both under <b>Cluster snapshot</b> in Intake. Rerun
        the investigation after adding the evidence. If the cluster has changed,
        a new capture cannot prove the historical mapping.
      </p>
      {unique.map((m: any) => (
        <div key={`${m.namespace}/${m.pvc_claim}`}>
          <p>
            For{" "}
            <b>
              {m.namespace}/{m.pvc_claim}
            </b>
            :
          </p>
          <pre>{`kubectl get pvc ${m.pvc_claim} -n ${m.namespace} -o yaml > pvc.yaml\nkubectl get pv PV_NAME -o yaml > pv.yaml`}</pre>
          <p>
            Replace <code>PV_NAME</code> with <code>spec.volumeName</code> from{" "}
            <code>pvc.yaml</code>. Include the affected pod's JSON/YAML snapshot
            too, so its volume references can be checked against the PVC.
            CSI-backed storage may require driver-specific evidence instead of
            an NFS export.
          </p>
        </div>
      ))}
    </div>
  );
}
