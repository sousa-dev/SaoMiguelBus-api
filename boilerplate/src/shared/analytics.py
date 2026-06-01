"""Canonical GA4 event names and page types for djast analytics.

Use these constants in Python (context processors, views) to avoid typos.
Templates may inline the same string values for brevity.
"""

from __future__ import annotations

from typing import Final


class EVENT_NAMES:
    """GA4 event name constants (snake_case)."""

    # Recommended GA4 events
    BEGIN_CHECKOUT: Final[str] = "begin_checkout"
    PURCHASE: Final[str] = "purchase"
    LOGIN: Final[str] = "login"
    SIGN_UP: Final[str] = "sign_up"
    LOGOUT: Final[str] = "logout"
    SEARCH: Final[str] = "search"
    SELECT_CONTENT: Final[str] = "select_content"

    # Landing / navigation
    FEATURE_TAB_VIEW: Final[str] = "feature_tab_view"
    NAV_CTA_CLICK: Final[str] = "nav_cta_click"

    # Blog
    POST_VIEW: Final[str] = "post_view"
    POST_CARD_CLICK: Final[str] = "post_card_click"
    BLOG_CTA_CLICK: Final[str] = "blog_cta_click"
    CATEGORY_VIEW: Final[str] = "category_view"
    TAG_VIEW: Final[str] = "tag_view"
    AUTHOR_VIEW: Final[str] = "author_view"
    RELATED_POST_CLICK: Final[str] = "related_post_click"
    TRANSLATION_SWITCH: Final[str] = "translation_switch"
    PAGINATION_CLICK: Final[str] = "pagination_click"

    # Free tools
    TOOL_VIEW: Final[str] = "tool_view"
    TOOL_STARTED: Final[str] = "tool_started"
    TOOL_GENERATE: Final[str] = "tool_generate"
    TOOL_COPY_RESULT: Final[str] = "tool_copy_result"
    TOOL_CTA_CLICK: Final[str] = "tool_cta_click"
    TOOL_CARD_CLICK: Final[str] = "tool_card_click"

    # Docs
    DOCS_NAV: Final[str] = "docs_nav"
    DOCS_SEARCH: Final[str] = "docs_search"
    DOCS_TAB_SWITCH: Final[str] = "docs_tab_switch"

    # Auth
    OAUTH_START: Final[str] = "oauth_start"
    PASSWORD_RESET_REQUEST: Final[str] = "password_reset_request"

    # Payment
    CHECKOUT_CANCELLED: Final[str] = "checkout_cancelled"
    RETRY_PAYMENT: Final[str] = "retry_payment"

    # Auto-instrumentation
    OUTBOUND_CLICK: Final[str] = "outbound_click"
    CONTACT_CLICK: Final[str] = "contact_click"
    FILE_DOWNLOAD: Final[str] = "file_download"
    FORM_SUBMIT: Final[str] = "form_submit"
    VIDEO_PLAY: Final[str] = "video_play"
    VIDEO_PROGRESS: Final[str] = "video_progress"
    VIDEO_COMPLETE: Final[str] = "video_complete"
    SCROLL_DEPTH: Final[str] = "scroll_depth"
    JS_ERROR: Final[str] = "js_error"
    PROMISE_REJECTION: Final[str] = "promise_rejection"
    PAGE_NOT_FOUND: Final[str] = "page_not_found"


class PAGE_TYPES:
    """Page type dimension values for GA_PAGE."""

    LANDING: Final[str] = "landing"
    APP: Final[str] = "app"
    BLOG_POST: Final[str] = "blog_post"
    BLOG_LIST: Final[str] = "blog_list"
    BLOG_ARCHIVE: Final[str] = "blog_archive"
    TOOL: Final[str] = "tool"
    TOOL_INDEX: Final[str] = "tool_index"
    TOOL_ARCHIVE: Final[str] = "tool_archive"
    DOCS: Final[str] = "docs"
    LEGAL: Final[str] = "legal"
    AUTH: Final[str] = "auth"
    PAYMENT: Final[str] = "payment"
    UNKNOWN: Final[str] = "unknown"


# Max GA4 parameter name length
MAX_PARAM_NAME_LENGTH: Final[int] = 40

# All event names for validation tests
ALL_EVENT_NAMES: Final[tuple[str, ...]] = tuple(
    value
    for name, value in vars(EVENT_NAMES).items()
    if not name.startswith("_") and isinstance(value, str)
)
