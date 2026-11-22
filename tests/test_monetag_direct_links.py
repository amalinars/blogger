import json
import os
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from automation.monetag import flow


class _FakeReq:
    def __init__(self, url):
        self.url = url


class _FakeLocator:
    def __init__(self, href, visible=True):
        self.href = href
        self._visible = visible

    def count(self):
        return 1 if self._visible else 0

    def nth(self, _idx):
        return self

    def is_visible(self, timeout=None):
        return self._visible

    def evaluate(self, _js):
        return None


class _FakeTab:
    def __init__(self, url="about:blank"):
        self.url = url
        self._closed = False
        self.viewport_size = {"width": 1280, "height": 800}
        self.mouse = mock.Mock()
        self.listeners = {}

    def is_closed(self):
        return self._closed

    def close(self):
        self._closed = True

    def bring_to_front(self):
        if "ay267.com" in str(self.url):
            self.url = "https://offer-shield.example/landing"

    def wait_for_load_state(self, *_args, **_kwargs):
        pass

    def evaluate(self, script, arg=None):
        if "readyState" in script:
            return "complete"
        return None

    def goto(self, url, **_kwargs):
        self.referer = _kwargs.get("referer")
        self.url = f"https://advertiser.example/direct?from={url.rsplit('/', 1)[-1]}" if "uplcm.com" in url else url

    def on(self, ev, cb):
        self.listeners.setdefault(ev, []).append(cb)


class _FakeMainPage(_FakeTab):
    def __init__(self, context, scan_payload):
        super().__init__("https://article.riztama.my.id/")
        self._context = context
        self._scan_payload = scan_payload
        self.dom_clicked_urls = []

    def locator(self, selector):
        for dl in self._scan_payload.get("directLinks", []):
            if dl in selector:
                return _FakeLocator(dl, visible=True)
        return _FakeLocator("", visible=False)

    def evaluate(self, script, arg=None):
        if "readyState" in script:
            return "complete"
        if "directLinks" in script and "clickShield" in script:
            return dict(self._scan_payload)
        if "existing.click()" in script and isinstance(arg, str):
            self.dom_clicked_urls.append(arg)
            self._context.spawn_tab(arg, final_url=f"https://advertiser.example/from-dom?src={arg.rsplit('/', 1)[-1]}")
            return None
        return None


class _FakeContext:
    def __init__(self, scan_payload):
        self.pages = []
        self._listeners = {}
        self._pending_tab = None
        self.main_page = _FakeMainPage(self, scan_payload)

    def new_page(self):
        if not self.pages:
            self.pages.append(self.main_page)
            return self.main_page
        tab = _FakeTab("about:blank")
        self.pages.append(tab)
        return tab

    def on(self, ev, cb):
        self._listeners.setdefault(ev, []).append(cb)

    def emit_request(self, url):
        for cb in self._listeners.get("request", []):
            cb(_FakeReq(url))

    def spawn_tab(self, initial_url, final_url=None):
        self.emit_request(initial_url)
        tab = _FakeTab(final_url or initial_url)
        self.pages.append(tab)
        self._pending_tab = tab
        for cb in self._listeners.get("page", []):
            cb(tab)
        return tab

    @contextmanager
    def expect_page(self, timeout=10000):
        self._pending_tab = None
        holder = mock.Mock()
        yield holder
        if self._pending_tab is None:
            raise TimeoutError("no popup")
        holder.value = self._pending_tab


class MonetagDirectLinksTest(unittest.TestCase):
    def test_config_contains_both_direct_links_and_trigger_all(self):
        cfg = json.loads(
            (Path(__file__).resolve().parents[1] / "automation" / "monetag" / "config.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            cfg["direct_link_urls"],
            ["https://uplcm.com/4/12256564", "https://uplcm.com/4/12124796"],
        )
        self.assertTrue(cfg["trigger_all_direct_links"])
        self.assertEqual(cfg["max_popunders_per_session"], {"min": 1, "max": 2})

    def test_resolve_direct_link_urls_merges_config_and_dom_deduplicated(self):
        urls = flow._resolve_direct_link_urls(
            {
                "direct_link_urls": ["https://uplcm.com/4/12256564", "https://uplcm.com/4/12124796"],
                "direct_link_url": "https://uplcm.com/4/12124796",
            },
            dom_links=["https://uplcm.com/4/12256564", "https://uplcm.com/4/99999999"],
        )
        self.assertEqual(
            urls,
            [
                "https://uplcm.com/4/12256564",
                "https://uplcm.com/4/12124796",
                "https://uplcm.com/4/99999999",
            ],
        )

    def test_popunder_intercept_detection(self):
        self.assertTrue(
            flow._looks_like_popunder_intercept(
                "https://ay267.com/?zoneid=12126541", "https://uplcm.com/4/12256564"
            )
        )
        self.assertFalse(
            flow._looks_like_popunder_intercept(
                "https://uplcm.com/4/12256564", "https://uplcm.com/4/12256564"
            )
        )

    def test_session_triggers_popunder_and_both_direct_links_even_when_shield_intercepts_first_dl(self):
        dl1 = "https://uplcm.com/4/12256564"
        dl2 = "https://uplcm.com/4/12124796"
        scan_payload = {
            "vignette": None,
            "clickShield": True,
            "pushCards": [],
            "controls": [{"x": 200, "y": 200, "label": "IPv6 Details"}],
            "directLinks": [dl1, dl2],
            "viewport": {"w": 1280, "h": 800},
        }
        ctx = _FakeContext(scan_payload)
        dl_clicks_seen = {"count": 0}

        def fake_human_click(_page, target):
            if isinstance(target, tuple):
                # OnClick Popunder trigger
                ctx.spawn_tab("https://ay267.com/?zoneid=12126541", final_url="https://offer-pop.example/landing")
            elif isinstance(target, _FakeLocator):
                dl_clicks_seen["count"] += 1
                if dl_clicks_seen["count"] == 1:
                    # Simulasikan click-shield mencegat klik fisik Direct Link #1
                    ctx.spawn_tab("https://ay267.com/?zoneid=12126541")
                else:
                    # Direct Link #2 langsung tembus klik fisik
                    ctx.spawn_tab(target.href, final_url="https://advertiser.example/dl-ok")

        @contextmanager
        def fake_browser_session(**_kwargs):
            yield mock.Mock(), ctx

        with (
            mock.patch.object(flow, "_monetag_browser_session", side_effect=fake_browser_session),
            mock.patch.object(flow, "build_camoufox_kwargs", return_value={}),
            mock.patch.object(flow, "build_camoufox_context_options", return_value={}),
            mock.patch.object(flow, "human_click", side_effect=fake_human_click),
            mock.patch.object(flow, "human_scroll"),
            mock.patch.object(flow, "human_wander"),
            mock.patch.object(flow.time, "sleep"),
        ):
            stats = flow.run_monetag_session(
                worker_id=1,
                proxy_data=None,
                config={
                    "target_url": "https://article.riztama.my.id/",
                    "allow_direct_ip": True,
                    "direct_link_urls": [dl1, dl2],
                    "trigger_all_direct_links": True,
                    "max_popunders_per_session": 2,
                    "dwell_popup_seconds": {"min": 0.0, "max": 0.0},
                    "dwell_direct_link_seconds": {"min": 0.0, "max": 0.0},
                },
            )

        self.assertTrue(stats["success"])
        self.assertEqual(stats["popunders_processed"], 2)  # OnClick + 1 shield intercept (cap=2)
        self.assertEqual(stats["direct_links_target"], 2)
        self.assertEqual(stats["direct_links_processed"], 2)
        self.assertEqual(set(stats["direct_links_dwelled"]), {dl1, dl2})
        # Begitu cap=2 tercapai, direct link dibuka dengan Referer tanpa memicu popunder liar lagi
        self.assertEqual(dl_clicks_seen["count"], 1)
        self.assertEqual(ctx.main_page.dom_clicked_urls, [])

    def test_popunder_cap_1_dismisses_extra_popups_and_opens_both_direct_links_with_referer(self):
        dl1 = "https://uplcm.com/4/12256564"
        dl2 = "https://uplcm.com/4/12124796"
        scan_payload = {
            "vignette": None,
            "clickShield": True,
            "pushCards": [],
            "controls": [{"x": 200, "y": 200, "label": "IPv6 Details"}],
            "directLinks": [dl1, dl2],
            "viewport": {"w": 1280, "h": 800},
        }
        ctx = _FakeContext(scan_payload)
        direct_tabs = []
        orig_new_page = ctx.new_page

        def track_new_page():
            t = orig_new_page()
            if t is not ctx.main_page:
                direct_tabs.append(t)
            return t

        ctx.new_page = track_new_page

        def fake_human_click(_page, target):
            if isinstance(target, tuple):
                # Simulasikan 3 popunder muncul sekaligus saat OnClick
                ctx.spawn_tab("https://ay267.com/?zoneid=12126541", final_url="https://offer-1.example/")
                ctx.spawn_tab("https://ay267.com/?zoneid=12126541", final_url="https://offer-2.example/")
                ctx.spawn_tab("https://ay267.com/?zoneid=12126541", final_url="https://offer-3.example/")

        @contextmanager
        def fake_browser_session(**_kwargs):
            yield mock.Mock(), ctx

        with (
            mock.patch.object(flow, "_monetag_browser_session", side_effect=fake_browser_session),
            mock.patch.object(flow, "build_camoufox_kwargs", return_value={}),
            mock.patch.object(flow, "build_camoufox_context_options", return_value={}),
            mock.patch.object(flow, "human_click", side_effect=fake_human_click),
            mock.patch.object(flow, "human_scroll"),
            mock.patch.object(flow, "human_wander"),
            mock.patch.object(flow.time, "sleep"),
        ):
            stats = flow.run_monetag_session(
                worker_id=1,
                proxy_data=None,
                config={
                    "target_url": "https://article.riztama.my.id/",
                    "allow_direct_ip": True,
                    "direct_link_urls": [dl1, dl2],
                    "trigger_all_direct_links": True,
                    "max_popunders_per_session": 1,
                    "dwell_popup_seconds": {"min": 0.0, "max": 0.0},
                    "dwell_direct_link_seconds": {"min": 0.0, "max": 0.0},
                },
            )

        self.assertTrue(stats["success"])
        self.assertEqual(stats["popunders_processed"], 1)  # 2 popunder ekstra langsung ditutup cepat
        self.assertEqual(stats["direct_links_processed"], 2)
        self.assertEqual(set(stats["direct_links_dwelled"]), {dl1, dl2})
        self.assertEqual(len(direct_tabs), 2)
        self.assertTrue(all(getattr(t, "referer", None) == "https://article.riztama.my.id/" for t in direct_tabs))
        self.assertTrue(all(t.is_closed() for t in ctx.pages if t is not ctx.main_page))


if __name__ == "__main__":
    unittest.main()
