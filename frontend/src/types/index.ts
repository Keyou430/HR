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
