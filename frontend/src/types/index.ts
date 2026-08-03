export interface EmbedUrls {
  feishu: string | null;
  dingtalk: string | null;
}

export interface PortalCatalogItem {
  code: string;
  title: string;
  description: string;
  status: string | null;
}

export interface PortalCatalog {
  items: PortalCatalogItem[];
  total: number;
}

export interface PortalBootstrapResponse {
  embed_urls: EmbedUrls;
  capabilities: PortalCatalog;
  skills: PortalCatalog;
}

// ── Auth types (Phase 2) ──────────────────────────────────────────

export interface LoginRequest {
  username: string;
  password: string;
}

export interface UserInfo {
  id: number;
  username: string;
  display_name: string;
  email: string | null;
  default_org_id: string | null;
  default_dept_id: string | null;
  roles: string[];
  permissions: string[];
  must_change_password: boolean;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: UserInfo;
  must_change_password: boolean;
}

export interface RefreshResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface ChangePasswordRequest {
  current_password: string;
  new_password: string;
}

export interface RegisterRequest {
  username: string;
  password: string;
  display_name?: string;
  email?: string;
}

// ── Permission types (Phase 3) ─────────────────────────────────────

/** Permission codes matching backend authorization/permissions.py */
export type PermissionCode =
  | "user:view" | "user:create" | "user:update" | "user:disable" | "user:assign_role"
  | "org:view" | "org:update"
  | "dept:view" | "dept:update"
  | "system:config"
  | "audit:view"
  | "task:view" | "task:create" | "task:update" | "task:delete"
  | "calendar:view" | "calendar:create" | "calendar:update" | "calendar:delete"
  | "kb:view" | "kb:create" | "kb:update" | "kb:delete" | "kb:import" | "kb:chat" | "kb:chat_sensitive"
  | "search:view"
  | "notice:view" | "notice:create" | "notice:update" | "notice:delete";

/** Role codes matching backend authorization/permissions.py */
export type RoleCode =
  | "super_admin"
  | "org_admin"
  | "dept_leader"
  | "dept_staff"
  | "external";
