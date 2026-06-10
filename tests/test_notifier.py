import bot.notifier as notifier_module
from bot.notifier import Notifier


class FakeResponse:
    status_code = 200
    text = "ok"


def test_webhook_payload_and_headers(monkeypatch):
    sent = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        sent.update({"url": url, "json": json, "headers": headers})
        return FakeResponse()

    monkeypatch.setattr(notifier_module.requests, "post", fake_post)

    notifier = Notifier(webhook_url="http://openclaw.local/webhooks/trading",
                        webhook_token="s3cret", webhook_enabled=True, exchange="paper")
    notifier.notify("Trade cerrado BTCUSDT", event="trade_closed",
                    data={"symbol": "BTCUSDT", "side": "long", "pnl": 34.5})

    assert sent["url"] == "http://openclaw.local/webhooks/trading"
    assert sent["headers"]["X-Webhook-Secret"] == "s3cret"
    payload = sent["json"]
    assert payload["event"] == "trade_closed"
    assert payload["symbol"] == "BTCUSDT"
    assert payload["pnl"] == 34.5
    assert payload["exchange"] == "paper"
    assert payload["strategy"]
    assert payload["timestamp"]
    assert payload["text"] == "Trade cerrado BTCUSDT"


def test_webhook_disabled_does_not_post(monkeypatch):
    called = []
    monkeypatch.setattr(notifier_module.requests, "post",
                        lambda *a, **k: called.append(1) or FakeResponse())
    Notifier(webhook_enabled=False).notify("hola", event="signal")
    assert not called
