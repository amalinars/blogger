#!/usr/bin/env python3
"""Adsterra shortlink gate-flow QA suite.

Ad-render mode is retired. The supported entry points are the terminal flow
dashboard (tui.launch_shortlink_flow) and the modern PySide6 GUI
(gui.launch_adsterra_gui), both of which run proxy-rotating flow workers with
an independent browser + proxy verifier.
"""

from .qa import (
    SessionBudget,
    country_label,
    is_proxy_pool_exhausted,
    load_config,
)
from .report import (
    classify_ad_url,
    host_matches,
    summarize_ad_checks,
    write_run_summary,
    write_session_report,
)
from .flow_qa import flow_worker_thread_loop, run_flow_session
from .tui import TUIManager, launch_shortlink_flow

__all__ = [
    "SessionBudget",
    "country_label",
    "is_proxy_pool_exhausted",
    "load_config",
    "classify_ad_url",
    "host_matches",
    "summarize_ad_checks",
    "write_run_summary",
    "write_session_report",
    "run_flow_session",
    "flow_worker_thread_loop",
    "TUIManager",
    "launch_shortlink_flow",
]
