/**
 * Where the app finds the CricketCanClubs website, and the bottom tabs. README "Phone apps (Expo)".
 * Change BASE_URL (or set EXPO_PUBLIC_BASE_URL when starting / building) when the Azure address changes.
 */
import type { ComponentProps } from "react";
import type { Ionicons } from "@expo/vector-icons";

export const BASE_URL = (process.env.EXPO_PUBLIC_BASE_URL || "https://cricketcanclubs-web.azurewebsites.net").replace(/\/+$/, "");

/** Added to the browser's user agent: the website hides its own bottom bar and adapts its tour inside the app. */
export const USER_AGENT_NAME = "CricketCanClubsApp/1.0 (Expo)";

type IconName = ComponentProps<typeof Ionicons>["name"];

export type Tab = { label: string; path: string; icon: IconName; url: string };

const tab = (label: string, path: string, icon: IconName): Tab => ({ label, path, icon, url: BASE_URL + path });

export const TABS: Tab[] = [
  tab("Home", "/", "home"),
  tab("Live", "/live", "radio"),
  tab("Score", "/score", "create"),
  tab("Scorecards", "/scorecards", "list"),
  tab("Upload", "/scorecards/upload", "camera"),
];

const host = (url: string) => {
  const match = /^https?:\/\/([^/?#:]+)/i.exec(url);
  return match ? match[1].toLowerCase() : "";
};

/** Pages of our own website open inside the app; everything else opens outside. */
export function isOwnPage(url: string): boolean {
  return host(url) !== "" && host(url) === host(BASE_URL);
}

/** Which tab a page belongs to (longest matching path wins; the dashboard counts as Home). */
export function tabFor(url: string): Tab | null {
  if (!isOwnPage(url)) return null;
  const path = (url.replace(/^https?:\/\/[^/]+/i, "").split(/[?#]/)[0] || "/").replace(/\/+$/, "") || "/";
  const matches = TABS.filter((t) => (t.path === "/" ? path === "/" || path === "/dashboard" : path === t.path || path.startsWith(`${t.path}/`)));
  return matches.sort((a, b) => b.path.length - a.path.length)[0] || null;
}
