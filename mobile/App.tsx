/**
 * CricketCanClubs for iPhone and Android (Expo / React Native), README "Phone apps (Expo)".
 *
 * The app shows the CricketCanClubs website (web, iPhone and Android stay in lockstep) with native extras:
 * bottom tabs (Home, Live, Score, Scorecards, Upload), camera / photo library for scorecard photos, pull down
 * to refresh (iPhone; on Android tap the open tab again), the Android back button through the pages, a
 * "No internet" screen with Try again, and WhatsApp / phone / email / other sites opening in their own apps.
 * The website hides its own bottom bar inside the app (it sees "CricketCanClubsApp" in the user agent).
 */
import { useCallback, useEffect, useMemo, useRef, useState, type ComponentType, type Ref } from "react";
import { BackHandler, Linking, Platform, Pressable, StyleSheet, Text, View } from "react-native";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { WebView } from "react-native-webview";
import type { WebViewNavigation } from "react-native-webview";
import type { ShouldStartLoadRequest, WebViewProgressEvent } from "react-native-webview/lib/WebViewTypes";

// react-native-webview 14's props type (iOS & Android & Windows props intersected) collapses to `never` with the
// current React / TypeScript types, so the component is used through this small typed wrapper. The props passed
// below are the ones listed in react-native-webview/lib/WebViewTypes.d.ts.
type WebViewHandle = { goBack: () => void; reload: () => void };
const AppWebView = WebView as unknown as ComponentType<Record<string, unknown> & { ref?: Ref<WebViewHandle> }>;

import { BASE_URL, TABS, USER_AGENT_NAME, isOwnPage, tabFor, type Tab } from "./src/config";

const GREEN = "#0A6E46";
const GREY = "#64748B";

function OfflineScreen({ onRetry }: { onRetry: () => void }) {
  return (
    <View style={styles.offline}>
      <Ionicons name="cloud-offline-outline" size={48} color={GREY} />
      <Text style={styles.offlineTitle}>No internet connection</Text>
      <Text style={styles.offlineText}>Check your Wi-Fi or mobile data, then try again.</Text>
      <Pressable style={styles.retry} onPress={onRetry} accessibilityRole="button">
        <Text style={styles.retryText}>Try again</Text>
      </Pressable>
    </View>
  );
}

function TabBar({ current, onOpen }: { current: Tab | null; onOpen: (tab: Tab) => void }) {
  return (
    <View style={styles.tabBar} accessibilityRole="tablist">
      {TABS.map((tab) => {
        const selected = current?.path === tab.path;
        return (
          <Pressable
            key={tab.path}
            style={styles.tab}
            onPress={() => onOpen(tab)}
            accessibilityRole="tab"
            accessibilityState={{ selected }}
            accessibilityLabel={tab.label}
          >
            <Ionicons name={selected ? tab.icon : (`${tab.icon}-outline` as Tab["icon"])} size={23} color={selected ? GREEN : GREY} />
            <Text style={[styles.tabLabel, { color: selected ? GREEN : GREY }]} numberOfLines={1}>
              {tab.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

function Main() {
  const webView = useRef<WebViewHandle>(null);
  const [uri, setUri] = useState(TABS[0].url);
  const [currentUrl, setCurrentUrl] = useState(TABS[0].url);
  const [canGoBack, setCanGoBack] = useState(false);
  const [progress, setProgress] = useState(0);
  const [offline, setOffline] = useState(false);
  const current = useMemo(() => tabFor(currentUrl), [currentUrl]);

  // Android back button: go back a page inside the website first.
  useEffect(() => {
    const sub = BackHandler.addEventListener("hardwareBackPress", () => {
      if (canGoBack && webView.current) {
        webView.current.goBack();
        return true;
      }
      return false;
    });
    return () => sub.remove();
  }, [canGoBack]);

  // A link to one of our pages (e.g. tapped in WhatsApp) opens that page in the app.
  useEffect(() => {
    const open = (url: string | null | undefined) => {
      if (!url) return;
      const page = url.replace(/^cricketcanclubs:\/\//, `${BASE_URL}/`);
      if (isOwnPage(page)) setUri(page);
    };
    Linking.getInitialURL().then(open).catch(() => {});
    const sub = Linking.addEventListener("url", ({ url }) => open(url));
    return () => sub.remove();
  }, []);

  const openTab = useCallback(
    (tab: Tab) => {
      setOffline(false);
      if (current?.path === tab.path) {
        // Tapping the open tab again refreshes it (Android has no pull-to-refresh in the web view).
        webView.current?.reload();
        return;
      }
      // Changing `uri` to the same value wouldn't reload, so add a harmless marker when needed.
      setUri(tab.url === uri ? `${tab.url}${tab.url.includes("?") ? "&" : "?"}t=${Date.now()}` : tab.url);
    },
    [current, uri]
  );

  const onShouldStart = useCallback((request: ShouldStartLoadRequest) => {
    const url = request.url;
    if (/^(about|blob|data):/i.test(url) || isOwnPage(url)) return true;
    // WhatsApp, phone, email, maps and other websites open in their own apps.
    Linking.openURL(url).catch(() => {});
    return false;
  }, []);

  const onNavigation = useCallback((nav: WebViewNavigation) => {
    setCanGoBack(nav.canGoBack);
    if (nav.url) setCurrentUrl(nav.url);
  }, []);

  return (
    <SafeAreaView style={styles.screen} edges={["top", "left", "right"]}>
      <StatusBar style="dark" />
      <View style={styles.page}>
        <AppWebView
          ref={webView}
          source={{ uri }}
          applicationNameForUserAgent={USER_AGENT_NAME}
          onShouldStartLoadWithRequest={onShouldStart}
          onNavigationStateChange={onNavigation}
          onLoadProgress={({ nativeEvent }: WebViewProgressEvent) => setProgress(nativeEvent.progress)}
          onLoadEnd={() => setProgress(1)}
          onError={() => setOffline(true)}
          onContentProcessDidTerminate={() => webView.current?.reload()}
          onRenderProcessGone={() => webView.current?.reload()}
          javaScriptEnabled
          domStorageEnabled
          sharedCookiesEnabled
          thirdPartyCookiesEnabled
          allowsBackForwardNavigationGestures
          pullToRefreshEnabled
          allowsInlineMediaPlayback
          setSupportMultipleWindows={false}
          mediaCapturePermissionGrantType="grantIfSameHostElsePrompt"
          startInLoadingState
          style={styles.web}
        />
        {progress > 0 && progress < 1 ? <View style={[styles.progress, { width: `${Math.round(progress * 100)}%` }]} /> : null}
        {offline ? (
          <OfflineScreen
            onRetry={() => {
              setOffline(false);
              webView.current?.reload();
            }}
          />
        ) : null}
      </View>
      <SafeAreaView edges={["bottom"]} style={styles.tabSafe}>
        <TabBar current={current} onOpen={openTab} />
      </SafeAreaView>
    </SafeAreaView>
  );
}

export default function App() {
  return (
    <SafeAreaProvider>
      <Main />
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#FFFFFF" },
  page: { flex: 1 },
  web: { flex: 1, backgroundColor: "#F3F7FB" },
  progress: { position: "absolute", top: 0, left: 0, height: 3, backgroundColor: GREEN },
  tabSafe: { backgroundColor: "#FFFFFF" },
  tabBar: {
    flexDirection: "row",
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: "#CBD5E1",
    backgroundColor: "#FFFFFF",
    paddingTop: 6,
    paddingBottom: Platform.OS === "android" ? 8 : 2,
  },
  tab: { flex: 1, alignItems: "center", gap: 2, paddingVertical: 2 },
  tabLabel: { fontSize: 11, fontWeight: "600" },
  offline: {
    ...StyleSheet.absoluteFill,
    alignItems: "center",
    justifyContent: "center",
    padding: 32,
    gap: 10,
    backgroundColor: "#F3F7FB",
  },
  offlineTitle: { fontSize: 21, fontWeight: "800", color: "#102A43" },
  offlineText: { fontSize: 15, color: "#4B647D", textAlign: "center" },
  retry: { marginTop: 10, backgroundColor: GREEN, paddingHorizontal: 22, paddingVertical: 12, borderRadius: 12 },
  retryText: { color: "#FFFFFF", fontWeight: "700", fontSize: 15 },
});
