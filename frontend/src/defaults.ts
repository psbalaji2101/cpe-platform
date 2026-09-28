export const roles = [
  ["nfs_logs", "NFS product logs", "TAR, TAR.GZ or ZIP archives"],
  ["pod_descriptions", "Pod descriptions", "Combined or individual .log files"],
  ["cluster_snapshot", "Cluster snapshot", "Nodes, pods, installed charts"],
  ["service_inventory", "Service mappings", "All-namespace service inventory"],
  [
    "kubernetes_pod_logs",
    "Kubernetes pod logs",
    "Current and previous container logs",
  ],
];
export const defaultConfig = {
  schema_version: 1,
  components: [],
  archive_path_mappings: [],
};
