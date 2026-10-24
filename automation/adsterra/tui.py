#!/usr/bin/env python3
"""Terminal dashboard for the Adsterra shortlink gate-flow QA suite."""

import argparse
import os
import signal
import sys
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from automation.adsterra.qa import (
    SessionBudget,
    country_label,
    load_config,
)
from automation.adsterra.report import utc_now_iso, write_run_summary
from core.proxy_manager import ProxyManager


def _label(value: Optional[bool]) -> str:
    if value is None:
        return "SKIP"
    return "PASS" if value else "FAIL"


def _label_style(value: Optional[bool]) -> str:
    if value is None:
        return "dim"
    return "bold green" if value else "bold red"


class TUIManager:
    def __init__(
        self,
        concurrency: int,
        proxy_manager: ProxyManager,
        config: Dict[str, Any],
        budget: SessionBudget,
    ):
        self.concurrency = concurrency
        self.pm = proxy_manager
        self.config = config
        self.budget = budget
        self.console = Console()
        self.lock = threading.RLock()
        self.is_stopping = False
        self.started_at = time.time()
        self.recent_logs: deque = deque(maxlen=10)

        self.workers: Dict[int, Dict[str, Any]] = {}
        for worker_id in range(1, concurrency + 1):
            self.workers[worker_id] = {
                "status": "Waiting",
                "status_style": "dim",
                "ip": "-",
                "country": "-",
                "url": "-",
                "score": 0,
                "verdict": "-",
                "verdict_style": "dim",
                "popunder": None,
                "social": None,
                "native": None,
                "native_viewport": None,
                "ad_network": None,
                "sessions_done": 0,
                "verifier": {
                    "verified": False,
                    "score": 0,
                    "is_safe": False,
                    "webdriver_hidden": None,
                    "webrtc_safe": None,
                    "webgl": "-",
                    "ads_allowed": None,
                    "adblock_detected": None,
                },
                "report_path": None,
                "screenshot": None,
            }

        self.add_log(
            "QA mode active: render verification only, no ad clicks, hard visit cap.",
            "cyan",
        )

    def add_log(self, message: str, style: str = "white") -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        with self.lock:
            self.recent_logs.append((timestamp, message, style))

    def on_event(self, event_type: str, data: Dict[str, Any]) -> None:
        worker_id = data.get("worker_id", 1)
        with self.lock:
            if event_type == "log_message":
                self.add_log(data.get("message", ""), data.get("style", "white"))
                return

            worker = self.workers.get(worker_id)
            if not worker:
                return

            if event_type == "status_update":
                status = data.get("status", "")
                worker["status"] = status
                if "error" in status.lower() or "fail" in status.lower():
                    worker["status_style"] = "bold red"
                elif "cooldown" in status.lower():
                    worker["status_style"] = "dim cyan"
                elif "inspect" in status.lower() or "loading" in status.lower():
                    worker["status_style"] = "bold yellow"
                else:
                    worker["status_style"] = "cyan"

            elif event_type == "proxy_assigned":
                worker["ip"] = data.get("ip", "-")
                worker["country"] = country_label(data.get("country"))
                worker["url"] = "-"
                worker["score"] = 0
                worker["verdict"] = "-"
                worker["verdict_style"] = "dim"
                worker["popunder"] = None
                worker["social"] = None
                worker["native"] = None
                worker["native_viewport"] = None
                worker["ad_network"] = None
                worker["report_path"] = None
                worker["screenshot"] = None
                worker["verifier"] = {
                    "verified": False,
                    "score": 0,
                    "is_safe": False,
                    "webdriver_hidden": None,
                    "webrtc_safe": None,
                    "webgl": "-",
                    "ads_allowed": None,
                    "adblock_detected": None,
                }

            elif event_type == "verifier_report":
                worker["verifier"] = {
                    "verified": True,
                    "score": data.get("score", 0),
                    "is_safe": bool(data.get("is_safe")),
                    "webdriver_hidden": data.get("webdriver_hidden"),
                    "webrtc_safe": data.get("webrtc_safe"),
                    "webgl": data.get("webgl", "-"),
                    "ads_allowed": data.get("ads_allowed"),
                    "adblock_detected": data.get("adblock_detected"),
                }
                self.add_log(
                    f"[W{worker_id}] Verifier {data.get('score', 0)}/100 "
                    f"({'safe' if data.get('is_safe') else 'issues found'})",
                    "green" if data.get("is_safe") else "yellow",
                )

            elif event_type == "session_started":
                worker["url"] = data.get("url", self.config.get("target_url", "-"))

            elif event_type == "popup_closed":
                popup_url = data.get("url") or "(blank)"
                self.add_log(
                    f"[W{worker_id}] Popup/new tab closed, main tab refocused: "
                    f"{popup_url[:70]}",
                    "yellow",
                )

            elif event_type == "ad_check":
                checks = data.get("checks") or {}
                worker["popunder"] = checks.get("popunder_script_seen")
                worker["social"] = checks.get("social_bar_script_seen")
                worker["native"] = checks.get("native_container_rendered")
                worker["native_viewport"] = checks.get("native_in_viewport")
                worker["ad_network"] = checks.get("ad_network_ok")
                worker["score"] = data.get("score", 0)
                worker["verdict"] = data.get("status", "-")
                worker["verdict_style"] = {
                    "PASS": "bold green",
                    "WARN": "bold yellow",
                    "FAIL": "bold red",
                }.get(worker["verdict"], "white")

            elif event_type == "screenshot_saved":
                worker["screenshot"] = data.get("path")

            elif event_type == "session_completed":
                status = data.get("status", "FAIL")
                worker["verdict"] = status
                worker["score"] = data.get("score", 0)
                worker["verdict_style"] = {
                    "PASS": "bold green",
                    "WARN": "bold yellow",
                    "FAIL": "bold red",
                }.get(status, "white")
                worker["report_path"] = data.get("report_path")
                worker["screenshot"] = data.get("screenshot") or worker.get("screenshot")
                worker["status"] = f"Done: {status}"
                worker["status_style"] = worker["verdict_style"]
                worker["sessions_done"] = worker.get("sessions_done", 0) + 1
                self.add_log(
                    f"[W{worker_id}] {status} score={data.get('score', 0)} "
                    f"report={Path(data.get('report_path') or '-').name}",
                    worker["verdict_style"],
                )

    def _render_progress(self) -> str:
        snapshot = self.budget.snapshot()
        return (
            f"{snapshot['completed']}/{snapshot['max_sessions']} "
            f"({snapshot['remaining']} left)"
        )

    def render(self) -> Group:
        with self.lock:
            uptime_seconds = int(time.time() - self.started_at)
            uptime = (
                f"{uptime_seconds // 3600:02d}:"
                f"{(uptime_seconds % 3600) // 60:02d}:"
                f"{uptime_seconds % 60:02d}"
            )
            snapshot = self.budget.snapshot()
            proxy_stats = self.pm.get_stats()

            # ── Header ──────────────────────────────────────────────────────
            header = Text()
            header.append("ADSTERRA QA  ", style="bold bright_cyan")
            header.append(
                f"up {uptime}  │  "
                f"{snapshot['completed']}/{snapshot['max_sessions']} sessions  │  "
                f"proxies: {proxy_stats.get('alive', 0)}a"
                f"/{proxy_stats.get('in_use', 0)}u"
                f"/{proxy_stats.get('total', 0)}t",
                style="white",
            )
            header.append(f"\ntarget: {self.config.get('target_url', '-')}", style="dim")
            header_panel = Panel(header, box=box.ROUNDED, border_style="cyan", padding=(0, 1))

            # ── Worker list ─────────────────────────────────────────────────
            worker_table = Table(box=box.SIMPLE_HEAD, expand=True, pad_edge=False)
            worker_table.add_column("W",   justify="center", style="bold cyan",  width=3)
            worker_table.add_column("IP",  justify="left",   min_width=15,       style="white")
            worker_table.add_column("Country", justify="left", min_width=8,     style="blue")
            worker_table.add_column("Status",  justify="left", min_width=18,    )
            worker_table.add_column("Score",   justify="center", width=6,       )
            worker_table.add_column("Verdict", justify="center", width=8,       )
            worker_table.add_column("Done",    justify="center", width=5, style="dim")

            for worker_id in range(1, self.concurrency + 1):
                w = self.workers[worker_id]
                worker_table.add_row(
                    f"W{worker_id}",
                    w["ip"],
                    w["country"],
                    Text(w["status"],  style=w.get("status_style", "white")),
                    str(w.get("score", 0)),
                    Text(w.get("verdict", "-"), style=w.get("verdict_style", "dim")),
                    str(w.get("sessions_done", 0)),
                )

            worker_panel = Panel(
                worker_table,
                title=f"[bold]Workers  ({self.concurrency})[/bold]",
                border_style="blue",
                box=box.ROUNDED,
                padding=(0, 1),
            )

            # ── Summary strip ───────────────────────────────────────────────
            summary = Text()
            summary.append("  Total: ", style="dim")
            summary.append(f"{snapshot['completed']} ", style="bold white")
            summary.append(" pass=", style="dim")
            summary.append(f"{snapshot['passed']}",  style="bold green")
            summary.append("  warn=", style="dim")
            summary.append(f"{snapshot['warned']}",  style="bold yellow")
            summary.append("  fail=", style="dim")
            summary.append(f"{snapshot['failed']}",  style="bold red")
            summary.append("  remaining=", style="dim")
            summary.append(f"{snapshot['remaining']}", style="cyan")

            # ── Activity log (last 8 lines) ─────────────────────────────────
            log_table = Table.grid(expand=True)
            log_table.add_column("", style="dim",  width=10)
            log_table.add_column("", style="white")
            recent = list(self.recent_logs)[-8:]
            if not recent:
                log_table.add_row("", "Waiting for activity...")
            else:
                for ts, msg, style in recent:
                    log_table.add_row(f"[{ts}]", Text(msg, style=style))
            log_panel = Panel(
                log_table,
                title="[bold]Log[/bold]",
                border_style="yellow",
                box=box.ROUNDED,
                padding=(0, 1),
            )

            footer = Text(
                "Ctrl+C = graceful stop. Sticky proxies never rotate between workers.",
                style="dim",
            )

            return Group(header_panel, worker_panel, summary, log_panel, footer)

    def public_state(self) -> Dict[str, Any]:
        with self.lock:
            result = {}
            for worker_id, worker in self.workers.items():
                result[str(worker_id)] = {
                    "status": worker.get("status"),
                    "ip": worker.get("ip"),
                    "country": worker.get("country"),
                    "url": worker.get("url"),
                    "score": worker.get("score"),
                    "verdict": worker.get("verdict"),
                    "checks": {
                        "popunder_script_seen": worker.get("popunder"),
                        "social_bar_script_seen": worker.get("social"),
                        "native_container_rendered": worker.get("native"),
                        "native_in_viewport": worker.get("native_viewport"),
                        "ad_network_seen": worker.get("ad_network"),
                    },
                    "verifier": worker.get("verifier"),
                    "report_path": worker.get("report_path"),
                    "screenshot": worker.get("screenshot"),
                }
            return result


class FlowTUIManager:
    def __init__(
        self,
        config: Dict[str, Any],
        run_index: int = 1,
        total_runs: int = 1,
    ):
        self.config = config
        self.console = Console()
        self.lock = threading.RLock()
        self.started_at = time.time()
        self.run_index = run_index
        self.total_runs = total_runs
        self.target_url = str(config.get("target_url") or "-")
        self.status = "Starting browser..."
        self.status_style = "cyan"
        self.steps = {
            1: {"state": "pending", "label": "Continue", "waited": None},
            2: {"state": "pending", "label": "Continue", "waited": None},
            3: {"state": "pending", "label": "Open order page", "waited": None},
        }
        self.ad: Dict[str, Any] = {}
        self.destination_url: Optional[str] = None
        self.final_url: Optional[str] = None
        self.redirect_mode: Optional[str] = None
        self.verdict: Optional[str] = None
        self.score: Optional[int] = None
        self.report_path: Optional[str] = None
        self.warnings: list[str] = []
        self.issues: list[str] = []
        self.off_target_navigations: list[str] = []
        self.popups = 0
        self.recent_logs: deque = deque(maxlen=10)
        self.add_log(
            "Flow mode: ads enabled. Step 3 scrolls to the native ad and "
            "checks viewport visibility.",
            "cyan",
        )

    def add_log(self, message: str, style: str = "white") -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        with self.lock:
            self.recent_logs.append((timestamp, message, style))

    def on_event(self, event_type: str, data: Dict[str, Any]) -> None:
        with self.lock:
            if event_type == "log_message":
                self.add_log(data.get("message", ""), data.get("style", "white"))
                return

            if event_type == "flow_started":
                self.target_url = data.get("target_url", self.target_url)
                self.status = "Opening target..."
                self.status_style = "cyan"
                return

            if event_type == "step_waiting":
                index = int(data.get("index", 0))
                step = self.steps.get(index)
                if step:
                    step["state"] = "waiting"
                self.status = f"Step {index}: waiting for countdown..."
                self.status_style = "bold yellow"
                return

            if event_type == "step_completed":
                index = int(data.get("index", 0))
                step = self.steps.get(index)
                if step:
                    step["state"] = "done"
                    step["label"] = data.get("label", step["label"])
                    step["waited"] = data.get("waited_seconds")
                self.status = f"Step {index} clicked"
                self.status_style = "bold green"
                self.add_log(
                    f"Step {index} clicked ({data.get('label', '-')})",
                    "green",
                )
                return

            if event_type == "destination_visible":
                self.destination_url = data.get("destination_url")
                self.status = "Step 3 done; checking ad viewport..."
                self.status_style = "bold magenta"
                return

            if event_type == "ad_check":
                self.ad = data.get("ad") or {}
                self.status = "Ad checked; starting final redirect..."
                self.status_style = "bold magenta"
                return

            if event_type == "redirect_started":
                self.status = "Final redirect in progress..."
                self.status_style = "bold cyan"
                return

            if event_type == "redirect_reached":
                self.final_url = data.get("final_url")
                self.status = "Destination reached"
                self.status_style = "bold green"
                return

            if event_type == "popup_closed":
                self.popups += 1
                self.add_log(
                    f"Popup/new tab closed: {str(data.get('url') or '(blank)')[:70]}",
                    "yellow",
                )
                return

            if event_type == "flow_completed":
                self.verdict = data.get("status")
                self.score = data.get("score")
                self.final_url = data.get("final_url") or self.final_url
                self.destination_url = (
                    data.get("destination_url") or self.destination_url
                )
                self.redirect_mode = data.get("redirect_mode")
                self.report_path = data.get("report_path")
                self.warnings = data.get("warnings") or []
                self.issues = data.get("issues") or []
                self.ad = data.get("ad") or self.ad
                self.off_target_navigations = (
                    data.get("off_target_navigations") or []
                )
                self.status = f"{self.verdict} score={self.score}"
                self.status_style = (
                    "bold green" if self.verdict == "PASS" else "bold red"
                )
                self.add_log(
                    f"{self.verdict} score={self.score} "
                    f"redirect={self.redirect_mode} final={self.final_url}",
                    self.status_style,
                )

    def _step_style(self, state: str) -> str:
        return {
            "pending": "dim",
            "waiting": "bold yellow",
            "done": "bold green",
        }.get(state, "white")

    def _step_label(self, state: str) -> str:
        return {
            "pending": "PENDING",
            "waiting": "WAITING",
            "done": "DONE",
        }.get(state, state.upper())

    def render(self) -> Group:
        with self.lock:
            elapsed_seconds = int(time.time() - self.started_at)
            elapsed = (
                f"{elapsed_seconds // 3600:02d}:"
                f"{(elapsed_seconds % 3600) // 60:02d}:"
                f"{elapsed_seconds % 60:02d}"
            )
            header = Text()
            header.append("SHORTLINK FLOW QA", style="bold bright_cyan")
            header.append(
                f"  /  run {self.run_index}/{self.total_runs}\n",
                style="bold white",
            )
            header.append(
                f"Target: {self.target_url}  |  Elapsed: {elapsed}  |  "
                f"Ads: ENABLED\n",
                style="dim",
            )
            header.append("Status: ", style="bold white")
            header.append(self.status, style=self.status_style)
            header_panel = Panel(header, style="cyan", box=box.ROUNDED)

            step_table = Table(box=box.SIMPLE_HEAVY, expand=True)
            step_table.add_column("Step", justify="center", style="bold cyan", width=6)
            step_table.add_column("Button", justify="left", min_width=18)
            step_table.add_column("State", justify="center", min_width=10)
            step_table.add_column("Waited", justify="center", min_width=8)
            for index in (1, 2, 3):
                step = self.steps[index]
                waited = step.get("waited")
                step_table.add_row(
                    f"{index:02d}",
                    str(step.get("label") or "-"),
                    Text(
                        self._step_label(str(step.get("state"))),
                        style=self._step_style(str(step.get("state"))),
                    ),
                    f"{waited:.2f}s" if isinstance(waited, (int, float)) else "-",
                )
            step_panel = Panel(
                step_table,
                title="[bold white]Gate steps[/bold white]",
                border_style="magenta",
                box=box.ROUNDED,
            )

            ad = self.ad or {}
            section_ratio = float(ad.get("section_visible_ratio") or 0)
            native_ratio = float(ad.get("native_visible_ratio") or 0)
            ad_section_ok = (
                (bool(ad.get("section_in_viewport")) and section_ratio >= 0.5)
                if ad
                else None
            )
            native_ok = (
                (bool(ad.get("native_rendered")) and native_ratio >= 0.5)
                if ad
                else None
            )
            ad_table = Table(box=box.SIMPLE_HEAVY, expand=True)
            ad_table.add_column("Check", style="bold white", min_width=24)
            ad_table.add_column("Result", justify="left")
            ad_table.add_row(
                "Section in viewport",
                Text(_label(ad_section_ok), style=_label_style(ad_section_ok)),
            )
            ad_table.add_row(
                "Section visible",
                f"{section_ratio:.0%}" if ad else "-",
            )
            ad_table.add_row(
                "Native ad rendered",
                Text(
                    _label(ad.get("native_rendered")),
                    style=_label_style(ad.get("native_rendered")),
                ),
            )
            ad_table.add_row(
                "Native ad in viewport",
                Text(_label(native_ok), style=_label_style(native_ok)),
            )
            ad_table.add_row(
                "Native visible",
                f"{native_ratio:.0%}" if ad else "-",
            )
            ad_table.add_row(
                "Ad requests seen",
                str(ad.get("ad_resources", "-")),
            )
            ad_table.add_row(
                "Popups closed",
                str(self.popups),
            )
            ad_table.add_row(
                "Scroll position",
                (
                    f"{ad.get('scroll_y', '-')}/{ad.get('scroll_height', '-')} "
                    f"(viewport {ad.get('viewport_height', '-')})"
                    if ad
                    else "-"
                ),
            )
            ad_panel = Panel(
                ad_table,
                title="[bold white]Step 3 native ad viewability[/bold white]",
                border_style="yellow",
                box=box.ROUNDED,
            )

            destination_table = Table(box=box.SIMPLE_HEAVY, expand=True)
            destination_table.add_column("Field", style="bold white", min_width=16)
            destination_table.add_column("Value", style="white")
            destination_table.add_row(
                "Final link",
                self.destination_url or "-",
            )
            destination_table.add_row(
                "Final URL",
                self.final_url or "-",
            )
            destination_table.add_row(
                "Redirect mode",
                self.redirect_mode or "-",
            )
            destination_table.add_row(
                "Report",
                self.report_path or "-",
            )
            destination_panel = Panel(
                destination_table,
                title="[bold white]Destination[/bold white]",
                border_style="blue",
                box=box.ROUNDED,
            )

            log_table = Table.grid(expand=True)
            log_table.add_column("Time", style="dim", width=10)
            log_table.add_column("Message", style="white")
            if not self.recent_logs:
                log_table.add_row("", "Waiting for activity...")
            else:
                for timestamp, message, style in self.recent_logs:
                    log_table.add_row(f"[{timestamp}]", Text(message, style=style))
            log_panel = Panel(
                log_table,
                title="[bold white]Activity log[/bold white]",
                border_style="yellow",
                box=box.ROUNDED,
            )

            verdict_panel = None
            if self.verdict:
                verdict = Text()
                verdict.append(
                    f"{self.verdict}  score={self.score}",
                    style=self.status_style,
                )
                verdict_panel = Panel(
                    verdict,
                    title="[bold white]Result[/bold white]",
                    border_style="green"
                    if self.verdict == "PASS"
                    else "red",
                    box=box.ROUNDED,
                )

            footer = Text(
                "Ads are allowed. Step 3 scrolls to the native ad and verifies "
                "it is visible before the final redirect.",
                style="dim",
            )

            parts = [
                header_panel,
                step_panel,
                ad_panel,
                destination_panel,
                log_panel,
            ]
            if verdict_panel is not None:
                parts.append(verdict_panel)
            parts.append(footer)
            return Group(*parts)


def launch_shortlink_flow(
    target_url: Optional[str] = None,
    headless: Optional[bool] = None,
    runs: int = 1,
    screenshot: Optional[bool] = None,
    report_dir: Optional[str] = None,
) -> int:
    from automation.adsterra.flow_qa import run_flow_session

    config = load_config()
    if target_url:
        config["target_url"] = target_url
    if report_dir:
        config["report_dir"] = report_dir

    total_runs = max(1, min(int(runs or 1), 3))
    failures = 0
    for run_index in range(1, total_runs + 1):
        tui = FlowTUIManager(config, run_index, total_runs)
        holder: Dict[str, Any] = {}

        def worker() -> None:
            try:
                holder["result"] = run_flow_session(
                    config,
                    headless=True if headless is None else bool(headless),
                    url=target_url,
                    screenshot=bool(screenshot),
                    event_callback=tui.on_event,
                )
            except Exception as error:
                holder["error"] = error

        thread = threading.Thread(
            target=worker,
            daemon=True,
            name=f"ShortlinkFlow-{run_index}",
        )
        thread.start()

        with Live(
            tui.render(),
            console=tui.console,
            refresh_per_second=4,
            screen=True,
        ) as live:
            interrupted = False
            while thread.is_alive():
                live.update(tui.render())
                try:
                    time.sleep(0.2)
                except KeyboardInterrupt:
                    if interrupted:
                        raise
                    interrupted = True
                    tui.add_log(
                        "Ctrl+C received; waiting for the current flow to finish.",
                        "bold red",
                    )
            thread.join(timeout=5.0)
            live.update(tui.render())
            time.sleep(0.8)

        result = holder.get("result")
        error = holder.get("error")
        if result is None:
            tui.console.print(
                f"\n[bold red]Flow {run_index}/{total_runs} failed:[/bold red] "
                f"{error}"
            )
            failures += 1
            continue

        tui.console.print(
            f"\n[bold]Flow {run_index}/{total_runs}:[/bold] "
            f"[{'green' if result['status'] == 'PASS' else 'red'}]"
            f"{result['status']} score={result['score']}[/]  "
            f"redirect={result.get('redirect_mode')}  "
            f"final={result.get('final_url')}"
        )
        ad = result.get("ad") or {}
        if ad:
            tui.console.print(
                f"  Ad section={ad.get('section_visible_ratio', 0):.0%}  "
                f"native={'rendered' if ad.get('native_rendered') else 'empty'}  "
                f"in_viewport={ad.get('native_in_viewport')}  "
                f"requests={ad.get('ad_resources', 0)}  "
                f"popups={len(result.get('popups') or [])}"
            )
        for warning in result.get("warnings") or []:
            tui.console.print(f"  [yellow]warning:[/yellow] {warning}")
        for issue in result.get("issues") or []:
            tui.console.print(f"  [red]issue:[/red] {issue}")
        if result.get("report_path"):
            tui.console.print(f"  report: {result['report_path']}")
        if result["status"] != "PASS":
            failures += 1

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Shortlink gate-flow automation by default. "
            "Use --mode gui for the graphical worker dashboard."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        choices=("flow", "gui"),
        default="flow",
        help="flow = terminal gate-run dashboard; gui = modern desktop dashboard",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=100,
        help="Flow runs, capped at 3 (only used in flow mode)",
    )
    parser.add_argument("--workers", "-w", type=int, default=2)
    parser.add_argument("--url", type=str, default=None, help="Page to inspect")
    parser.add_argument(
        "--max-sessions", type=int, default=200, help="Hard cap for this run (max 50)"
    )
    parser.add_argument(
        "--max-per-proxy",
        type=int,
        default=None,
        help="Visits allowed per proxy (max 3)",
    )
    parser.add_argument("--headless", action="store_true", default=None)
    parser.add_argument(
        "--no-headless", action="store_false", dest="headless"
    )
    parser.add_argument("--report-dir", type=str, default=None)
    parser.add_argument("--wait-after-load", type=float, default=None)
    parser.add_argument("--ad-wait", type=float, default=None)
    parser.add_argument("--no-screenshot", action="store_false", dest="screenshot")
    parser.add_argument(
        "--screenshot",
        action="store_true",
        dest="screenshot",
        help="Save step screenshots in flow mode",
    )
    parser.add_argument("--no-verifier", action="store_false", dest="run_verifier")
    parser.set_defaults(screenshot=None, run_verifier=None)
    args = parser.parse_args()

    if args.mode == "gui":
        from automation.adsterra.gui import launch_adsterra_gui

        raise SystemExit(launch_adsterra_gui())

    if args.mode == "flow":
        raise SystemExit(
            launch_shortlink_flow(
                target_url=args.url,
                headless=args.headless,
                runs=args.runs,
                screenshot=args.screenshot,
                report_dir=args.report_dir,
            )
        )
