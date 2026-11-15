import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from automation.smartlink.actions import engage, tabs


class FakePage:
    def __init__(self, url="https://ghasima.ai.studio/", on_goto=None):
        self.url = url
        self.closed = False
        self.brought_to_front = 0
        self.goto_calls = []
        self._on_goto = on_goto

    def is_closed(self):
        return self.closed

    def bring_to_front(self):
        self.brought_to_front += 1

    def goto(self, url, **_kwargs):
        self.url = url
        self.goto_calls.append(url)
        if self._on_goto:
            self._on_goto(self, url)

    def close(self):
        self.closed = True


def _install_fake_clock(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(tabs.time, "time", lambda: clock[0])
    monkeypatch.setattr(tabs.time, "sleep", lambda s: clock.__setitem__(0, clock[0] + s))
    monkeypatch.setattr(engage.time, "sleep", lambda _s: None)
    return clock


class FakeContext:
    def __init__(self, main_page, spawned_on_wait=None, clock=None):
        self.pages = [main_page]
        self._spawned = list(spawned_on_wait or [])
        self.new_pages_created = []
        self._clock = clock

    def wait_for_event(self, event_name, timeout=1000.0):
        assert event_name == "page"
        if self._spawned:
            p = self._spawned.pop(0)
            self.pages.append(p)
            return p
        if self._clock is not None:
            self._clock[0] += max(0.1, timeout / 1000.0)
        raise TimeoutError("no page event")

    def new_page(self):
        p = FakePage("about:blank")
        self.pages.append(p)
        self.new_pages_created.append(p)
        return p


class FakeLocator:
    def __init__(self, count_val=1, href=None, child=None):
        self._count = count_val
        self._href = href
        self._child = child
        self.first = self

    def count(self):
        return self._count

    def nth(self, _idx):
        return self

    def locator(self, _selector):
        return self._child if self._child is not None else FakeLocator(0)

    def get_attribute(self, name):
        return self._href if name == "href" else None

    def bounding_box(self):
        return {"x": 10.0, "y": 50.0, "width": 200.0, "height": 40.0}


class FakeArticlePage(FakePage):
    def __init__(self, url, card_href):
        super().__init__(url=url)
        link = FakeLocator(1, href=card_href)
        self._cards = FakeLocator(1, child=link)

    def locator(self, selector):
        assert selector == "article"
        return self._cards


class FakeCardLink:
    def __init__(self, index):
        self.index = index
        self.first = self

    def count(self):
        return 1

    def locator(self, _selector):
        return self

    def get_attribute(self, name):
        return f"https://uplcm.com/4/{self.index}" if name == "href" else None

    def bounding_box(self):
        return {"x": 10.0, "y": 50.0, "width": 200.0, "height": 40.0}


class FakeCards:
    def __init__(self, n):
        self.n = n

    def count(self):
        return self.n

    def nth(self, idx):
        return FakeCardLink(idx)


class FakeMultiCardPage(FakePage):
    def __init__(self, url, n_cards):
        super().__init__(url=url)
        self._cards = FakeCards(n_cards)

    def locator(self, selector):
        assert selector == "article"
        return self._cards


def test_wait_and_handle_context_page_event(monkeypatch):
    clock = _install_fake_clock(monkeypatch)
    monkeypatch.setattr(tabs, "dwell_human", lambda *_a, **_kw: None)

    main_page = FakePage("https://ghasima.ai.studio/")
    popup = FakePage("https://uplcm.com/4/12211156")
    ctx = FakeContext(main_page, spawned_on_wait=[popup], clock=clock)

    handled = tabs.wait_and_handle_new_pages(
        ctx, main_page, baseline=1, worker_id=1, dwell_cfg={"min": 0.1, "max": 0.1},
        wait_seconds=1.0, fallback_url="https://uplcm.com/4/fallback",
    )

    assert handled == 1
    assert popup.closed is True
    assert ctx.new_pages_created == []


def test_wait_and_handle_short_sibling_grace(monkeypatch):
    clock = _install_fake_clock(monkeypatch)
    monkeypatch.setattr(tabs, "dwell_human", lambda *_a, **_kw: None)

    main_page = FakePage("https://ghasima.ai.studio/")
    popup = FakePage("https://uplcm.com/4/12211156")
    ctx = FakeContext(main_page, spawned_on_wait=[popup], clock=clock)
    start = clock[0]

    handled = tabs.wait_and_handle_new_pages(
        ctx, main_page, baseline=1, worker_id=1, dwell_cfg={"min": 0.1, "max": 0.1},
        wait_seconds=1.0, fallback_url=None, sibling_grace_seconds=1.5,
    )

    assert handled == 1
    assert popup.closed is True
    assert 1.5 <= clock[0] - start <= 4.0


def test_wait_and_handle_blank_tab_falls_back_to_direct_link(monkeypatch):
    clock = _install_fake_clock(monkeypatch)
    monkeypatch.setattr(tabs, "dwell_human", lambda *_a, **_kw: None)

    main_page = FakePage("https://ghasima.ai.studio/")
    blank = FakePage("about:blank")
    ctx = FakeContext(main_page, spawned_on_wait=[blank], clock=clock)
    target = "https://uplcm.com/4/12211156"

    handled = tabs.wait_and_handle_new_pages(
        ctx, main_page, baseline=1, worker_id=1, dwell_cfg={"min": 0.1, "max": 0.1},
        wait_seconds=1.0, fallback_url=target, sibling_grace_seconds=1.5,
    )

    assert blank.closed is True
    assert handled == 1
    assert len(ctx.new_pages_created) == 1
    assert ctx.new_pages_created[0].goto_calls == [target]


def test_wait_and_handle_fallback_opens_direct_link(monkeypatch):
    clock = _install_fake_clock(monkeypatch)
    monkeypatch.setattr(tabs, "dwell_human", lambda *_a, **_kw: None)

    main_page = FakePage("https://ghasima.ai.studio/")
    ctx = FakeContext(main_page, clock=clock)
    target = "https://uplcm.com/4/12211156"

    handled = tabs.wait_and_handle_new_pages(
        ctx, main_page, baseline=1, worker_id=1, dwell_cfg={"min": 0.1, "max": 0.1},
        wait_seconds=1.0, fallback_url=target,
    )

    assert handled == 1
    assert len(ctx.new_pages_created) == 1
    fb = ctx.new_pages_created[0]
    assert fb.goto_calls == [target]
    assert fb.closed is True


def test_engage_restores_hijacked_main_tab_and_opens_fallback(monkeypatch):
    clock = _install_fake_clock(monkeypatch)
    monkeypatch.setattr(engage, "ensure_visible", lambda _p, _loc: True)
    monkeypatch.setattr(tabs, "dwell_human", lambda *_a, **_kw: None)

    home = "https://ghasima.ai.studio/"
    direct = "https://uplcm.com/4/12211156"
    main_page = FakeArticlePage(home, direct)
    ctx = FakeContext(main_page, clock=clock)

    def hijack_click(page, _loc):
        page.url = "https://shopee.co.id/ad-tab-under"
        return (50.0, 60.0)

    monkeypatch.setattr(engage, "human_click", hijack_click)

    engage.engage_articles(
        ctx, main_page, worker_id=1,
        config={"click_attempts": 1, "tab_wait_seconds": 1.0, "dwell_seconds": {"min": 0.1, "max": 0.1}},
        target_url=home,
    )

    assert main_page.goto_calls == [home]
    assert main_page.url == home
    assert len(ctx.new_pages_created) == 1
    assert ctx.new_pages_created[0].goto_calls == [direct]
    assert ctx.new_pages_created[0].closed is True


def test_engage_clicks_each_card_once(monkeypatch):
    clock = _install_fake_clock(monkeypatch)
    monkeypatch.setattr(engage, "ensure_visible", lambda _p, _loc: True)
    monkeypatch.setattr(tabs, "dwell_human", lambda *_a, **_kw: None)

    home = "https://ghasima.ai.studio/"
    main_page = FakeMultiCardPage(home, n_cards=4)
    ctx = FakeContext(main_page, clock=clock)
    clicked = []

    def record_click(_page, loc):
        clicked.append(loc.index)
        return (50.0, 60.0)

    monkeypatch.setattr(engage, "human_click", record_click)

    engage.engage_articles(
        ctx, main_page, worker_id=1,
        config={"click_attempts": 4, "tab_wait_seconds": 1.0, "dwell_seconds": {"min": 0.1, "max": 0.1}},
        target_url=home,
    )

    assert sorted(clicked) == [0, 1, 2, 3]
    assert len(set(clicked)) == 4
