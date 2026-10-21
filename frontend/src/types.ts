export interface User {
  id: number;
  username: string;
  role: "admin" | "operator" | "viewer";
  is_active: boolean;
  created_at: string;
}
export interface Target {
  id: number;
  tenant: string;
  controller_id: string;
  name: string;
  description: string;
  enabled: boolean;
  deleted_at: string | null;
  connection_status: string;
  attributes: Record<string, string>;
  last_seen_at: string | null;
  polling_interval_seconds: number | null;
  boot_confirmation: string;
  running_firmware: string | null;
  last_installed_version: string | null;
  deployment: Deployment | null;
}
export interface Firmware {
  id: number;
  name: string;
  version: string;
  compatible: string;
  vendor: string;
  description: string;
  filename: string;
  size: number;
  sha256: string;
  sha1: string;
  md5: string;
  available: boolean;
  signature_status: string;
  created_at: string;
}
export interface Module {
  id: number;
  name: string;
  version: string;
  type: string;
  vendor: string;
  description: string;
  artifact_id: number;
}
export interface Distribution {
  id: number;
  name: string;
  version: string;
  description: string;
  module_id: number;
}
export interface Snapshot {
  distribution_name: string;
  distribution_version: string;
  module_name: string;
  module_version: string;
  filename: string;
  size: number;
  compatible: string;
  sha256: string;
}
export interface Deployment {
  id: number;
  target_id: number;
  distribution_id: number;
  internal_status: string;
  active: boolean;
  mode: string;
  snapshot: Snapshot;
  progress: number | null;
  boot_confirmation: string;
  error_message: string | null;
  attempt_count: number;
  retry_of: number | null;
  created_at: string;
  completed_at: string | null;
}
export interface DeploymentEvent {
  id: number;
  kind: string;
  message: string;
  raw: Record<string, unknown>;
  progress: number | null;
  device_time: string | null;
  received_at: string;
}
export interface Audit {
  id: number;
  actor: string;
  operation: string;
  resource_type: string;
  resource_id: string | null;
  timestamp: string;
  details: Record<string, unknown>;
}
export interface Summary {
  total_targets: number;
  online_targets: number;
  offline_targets: number;
  never_connected: number;
  firmware_versions: number;
  active_deployments: number;
  successful_installations: number;
  failed_installations: number;
  pending_deployments: number;
  states: Record<string, number>;
}
export interface Settings {
  app_name: string;
  app_env: string;
  public_base_url: string;
  polling_interval_seconds: number;
  offline_threshold_seconds: number;
  max_upload_size_mb: number;
  session_hours: number;
}
