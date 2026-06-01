/**
 * djast GA4 analytics helper — hybrid declarative + auto-instrumentation.
 *
 * Requires gtag to be bootstrapped by shared/plugins/google-analytics.html.
 * Exposes window.djast with track(), trackOnce(), identify(), pageview().
 */
(function () {
    "use strict";

    var CONSENT_KEY = "djast_consent_v1";
    var DOWNLOAD_EXT =
        /\.(pdf|zip|csv|xlsx|json|txt|md|png|jpe?g|svg|webp|gif|mp4|mp3)(\?|$)/i;
    var SCROLL_MILESTONES = [25, 50, 75, 90, 100];
    var scrollFired = {};
    var youtubePlayers = {};

    function readMeta(name) {
        var el = document.querySelector('meta[name="' + name + '"]');
        return el ? el.getAttribute("content") : null;
    }

    function parseGaPage() {
        try {
            var raw = readMeta("djast:ga-page");
            return raw ? JSON.parse(raw) : {};
        } catch (e) {
            return {};
        }
    }

    function isDebug() {
        return readMeta("djast:ga-debug") === "true";
    }

    function gtagSafe() {
        return typeof window.gtag === "function";
    }

    function logDebug() {
        if (isDebug() && window.console) {
            console.debug.apply(console, ["[djast-analytics]"].concat(
                Array.prototype.slice.call(arguments)
            ));
        }
    }

    function defaultParams() {
        var page = parseGaPage();
        return {
            page_type: page.page_type || "unknown",
            page_section: page.page_section || "",
            url_name: page.url_name || "",
            user_authenticated: page.user_authenticated === true ||
                page.user_authenticated === "true",
        };
    }

    function mergeParams(extra) {
        var out = {};
        var base = defaultParams();
        var key;
        for (key in base) {
            if (Object.prototype.hasOwnProperty.call(base, key)) {
                out[key] = base[key];
            }
        }
        if (extra && typeof extra === "object") {
            for (key in extra) {
                if (Object.prototype.hasOwnProperty.call(extra, key)) {
                    out[key] = extra[key];
                }
            }
        }
        return out;
    }

    function parseDataParams(el) {
        var raw = el.getAttribute("data-ga-params");
        if (!raw) {
            return {};
        }
        try {
            return JSON.parse(raw);
        } catch (e) {
            logDebug("Invalid data-ga-params JSON", raw);
            return {};
        }
    }

    function hasSkip(el) {
        return el.closest("[data-ga-skip]") !== null;
    }

    function track(eventName, params) {
        if (!gtagSafe()) {
            logDebug("gtag unavailable, skipped:", eventName);
            return;
        }
        try {
            var payload = mergeParams(params || {});
            if (isDebug()) {
                payload.debug_mode = true;
            }
            window.gtag("event", eventName, payload);
            logDebug("event", eventName, payload);
        } catch (e) {
            logDebug("track error", e);
        }
    }

    function trackOnce(storageKey, eventName, params) {
        var key = "djast_seen_" + storageKey;
        try {
            if (sessionStorage.getItem(key)) {
                return;
            }
            sessionStorage.setItem(key, "1");
        } catch (e) {
            /* sessionStorage blocked */
        }
        track(eventName, params);
    }

    function identify(userId) {
        if (!gtagSafe() || userId == null || userId === "") {
            return;
        }
        try {
            window.gtag("set", { user_id: String(userId) });
            logDebug("identify", userId);
        } catch (e) {
            logDebug("identify error", e);
        }
    }

    function pageview(overrides) {
        var gaId = readMeta("djast:ga-id");
        if (!gtagSafe() || !gaId) {
            return;
        }
        try {
            var config = mergeParams(overrides || {});
            if (isDebug()) {
                config.debug_mode = true;
            }
            window.gtag("config", gaId, config);
            logDebug("pageview", config);
        } catch (e) {
            logDebug("pageview error", e);
        }
    }

    function setDefaults(params) {
        var meta = document.querySelector('meta[name="djast:ga-page"]');
        if (!meta) {
            return;
        }
        var current = parseGaPage();
        var merged = mergeParams(params);
        for (var k in merged) {
            if (Object.prototype.hasOwnProperty.call(merged, k)) {
                current[k] = merged[k];
            }
        }
        meta.setAttribute("content", JSON.stringify(current));
    }

    function hostnameOf(href) {
        try {
            return new URL(href, window.location.href).hostname;
        } catch (e) {
            return "";
        }
    }

    function handleDeclarativeClick(event) {
        var target = event.target.closest("[data-ga-event]");
        if (!target || hasSkip(target)) {
            return;
        }
        var eventName = target.getAttribute("data-ga-event");
        if (!eventName) {
            return;
        }
        var params = parseDataParams(target);
        if (target.getAttribute("data-ga-once") !== null) {
            var onceKey =
                target.getAttribute("data-ga-once-key") ||
                eventName + ":" + (target.id || target.href || "el");
            trackOnce(onceKey, eventName, params);
        } else {
            track(eventName, params);
        }
    }

    function handleDeclarativeSubmit(event) {
        var form = event.target;
        if (!form || form.tagName !== "FORM" || hasSkip(form)) {
            return;
        }
        if (form.getAttribute("data-ga-event")) {
            var eventName = form.getAttribute("data-ga-event");
            var params = parseDataParams(form);
            track(eventName, params);
            return;
        }
        if (form.hasAttribute("data-ga-skip-auto")) {
            return;
        }
        track("form_submit", {
            form_id: form.id || "",
            form_action: form.getAttribute("action") || "",
            form_method: (form.method || "get").toLowerCase(),
        });
    }

    function handleAutoClick(event) {
        var anchor = event.target.closest("a[href]");
        if (!anchor || hasSkip(anchor)) {
            return;
        }
        if (anchor.getAttribute("data-ga-event")) {
            return;
        }
        var href = anchor.getAttribute("href") || "";
        if (!href || href.charAt(0) === "#") {
            return;
        }

        if (href.indexOf("mailto:") === 0) {
            track("contact_click", {
                contact_type: "email",
                link_text: (anchor.textContent || "").trim().slice(0, 80),
            });
            return;
        }
        if (href.indexOf("tel:") === 0) {
            track("contact_click", {
                contact_type: "phone",
                link_text: (anchor.textContent || "").trim().slice(0, 80),
            });
            return;
        }

        if (DOWNLOAD_EXT.test(href)) {
            track("file_download", {
                link_url: href,
                link_text: (anchor.textContent || "").trim().slice(0, 80),
            });
            return;
        }

        var host = hostnameOf(href);
        if (
            host &&
            host !== window.location.hostname &&
            anchor.getAttribute("data-ga-skip-outbound") === null
        ) {
            track("outbound_click", {
                link_url: href,
                link_text: (anchor.textContent || "").trim().slice(0, 80),
                link_domain: host,
            });
        }
    }

    function shouldTrackScroll() {
        var body = document.body;
        if (!body) {
            return false;
        }
        if (body.getAttribute("data-ga-scroll") === "false") {
            return false;
        }
        if (body.getAttribute("data-ga-scroll") === "true") {
            return true;
        }
        var page = parseGaPage();
        var types = [
            "landing",
            "blog_post",
            "tool",
            "docs",
            "app",
        ];
        return types.indexOf(page.page_type) !== -1;
    }

    function onScroll() {
        if (!shouldTrackScroll()) {
            return;
        }
        var doc = document.documentElement;
        var scrollTop = doc.scrollTop || document.body.scrollTop;
        var scrollHeight = doc.scrollHeight - doc.clientHeight;
        if (scrollHeight <= 0) {
            return;
        }
        var pct = Math.round((scrollTop / scrollHeight) * 100);
        var i;
        for (i = 0; i < SCROLL_MILESTONES.length; i++) {
            var m = SCROLL_MILESTONES[i];
            if (pct >= m && !scrollFired[m]) {
                scrollFired[m] = true;
                track("scroll_depth", { percent_scrolled: m });
            }
        }
    }

    function initScroll() {
        if (!shouldTrackScroll()) {
            return;
        }
        var ticking = false;
        window.addEventListener(
            "scroll",
            function () {
                if (!ticking) {
                    ticking = true;
                    window.requestAnimationFrame(function () {
                        onScroll();
                        ticking = false;
                    });
                }
            },
            { passive: true }
        );
        onScroll();
    }

    function extractYoutubeId(src) {
        if (!src) {
            return "";
        }
        var m = src.match(/embed\/([^?&]+)/);
        return m ? m[1] : "";
    }

    function onYoutubeStateChange(event, videoId) {
        var state = event.data;
        if (state === window.YT.PlayerState.PLAYING) {
            track("video_play", { video_id: videoId });
        }
        if (state === window.YT.PlayerState.ENDED) {
            track("video_complete", { video_id: videoId });
        }
    }

    function initYoutube() {
        var iframes = document.querySelectorAll(
            'iframe[src*="youtube.com/embed"], iframe[src*="youtube-nocookie.com/embed"]'
        );
        if (!iframes.length) {
            return;
        }

        function bindPlayers() {
            iframes.forEach(function (iframe, index) {
                var videoId = extractYoutubeId(iframe.getAttribute("src"));
                if (!videoId || youtubePlayers[videoId]) {
                    return;
                }
                try {
                    var player = new window.YT.Player(iframe, {
                        events: {
                            onStateChange: function (ev) {
                                onYoutubeStateChange(ev, videoId);
                            },
                        },
                    });
                    youtubePlayers[videoId] = player;
                } catch (e) {
                    logDebug("YouTube player init failed", e);
                }
            });
        }

        if (window.YT && window.YT.Player) {
            bindPlayers();
            return;
        }

        var prev = window.onYouTubeIframeAPIReady;
        window.onYouTubeIframeAPIReady = function () {
            if (typeof prev === "function") {
                prev();
            }
            bindPlayers();
        };

        if (!document.getElementById("djast-youtube-api")) {
            var tag = document.createElement("script");
            tag.id = "djast-youtube-api";
            tag.src = "https://www.youtube.com/iframe_api";
            document.head.appendChild(tag);
        }
    }

    function initErrors() {
        window.addEventListener("error", function (ev) {
            track("js_error", {
                error_message: String(ev.message || "").slice(0, 150),
                error_source: String(ev.filename || "").slice(0, 150),
                error_line: ev.lineno || 0,
            });
        });
        window.addEventListener("unhandledrejection", function (ev) {
            var reason = ev.reason;
            track("promise_rejection", {
                error_message: String(
                    reason && reason.message ? reason.message : reason
                ).slice(0, 150),
            });
        });
    }

    function fire404IfNeeded() {
        if (
            document.body &&
            document.body.getAttribute("data-ga-404") === "true"
        ) {
            track("page_not_found", {
                requested_path: window.location.pathname,
            });
        }
    }

    function fireQuerystringEvents() {
        var params = new URLSearchParams(window.location.search);
        if (params.get("login") === "success") {
            trackOnce("auth_login", "login", { method: "site" });
            params.delete("login");
            cleanUrl(params);
        }
        if (params.get("signup") === "success") {
            trackOnce("auth_signup", "sign_up", { method: "site" });
            params.delete("signup");
            cleanUrl(params);
        }
    }

    function cleanUrl(params) {
        var qs = params.toString();
        var path = window.location.pathname + (qs ? "?" + qs : "");
        window.history.replaceState({}, "", path);
    }

    function initDelegated() {
        document.addEventListener("click", function (ev) {
            handleDeclarativeClick(ev);
            handleAutoClick(ev);
        });
        document.addEventListener("submit", handleDeclarativeSubmit, true);
    }

    window.djast = {
        track: track,
        trackOnce: trackOnce,
        identify: identify,
        pageview: pageview,
        setDefaults: setDefaults,
        CONSENT_KEY: CONSENT_KEY,
    };

    function init() {
        initDelegated();
        initScroll();
        initErrors();
        fire404IfNeeded();
        fireQuerystringEvents();
        initYoutube();
        logDebug("initialized", defaultParams());
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
