import type { AssetType } from "../../api/types";

export const TYPE_LABELS: Record<AssetType, string> = {
  email: "Email",
  linkedin_post: "LinkedIn post",
  x_post: "X post",
  blog_post: "Blog post",
  landing_page: "Landing page",
};

export function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}
