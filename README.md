# Notify Subscriptions for Home Assistant

Every Home Assistant user decides **which** notifications they get and **on which of their devices**.
Automations stop listing phones: they send to a *topic*, and the integration delivers it to everyone
subscribed to that topic.

```yaml
action: notify_subscriptions.send
data:
  topic: power_change
  title: "⚠️ Power"
  message: "The power is off"
```

## Concepts

| | What it is | Who manages it |
|---|---|---|
| **Channel** | Where a notification can be delivered for a user. Companion app phones and computers are found automatically; any other notify service or entity (Telegram, e-mail, …) can be added and bound to a user. | automatic / admin |
| **Topic** | What a notification is about: `air_raid`, `power_change`, `washer_done`, … Each topic has a default for users who never changed it (`all` or `off`). | admin |
| **Subscription** | A user's choice per topic: `off`, `all` (every device of mine, including new ones) or `picked` (only selected devices). | each user |

The owner of a Companion app device is taken from its registration, so nothing has to match by name.

## Installation

1. HACS → three dots → **Custom repositories** → add `https://github.com/OLDIN/ha-notify-subscriptions` (Integration).
2. Install **Notify Subscriptions** and restart Home Assistant.
3. **Settings → Devices & services → Add integration → Notify Subscriptions**.

## Setup

Create topics (admin only), for example in **Developer tools → Actions**:

```yaml
action: notify_subscriptions.set_topic
data:
  id: air_raid
  name: Air raid alert
  icon: mdi:bell-ring
  default_mode: all          # users who never changed it get it on all their devices
  data:                      # optional, sent with every notification of the topic
    push:
      interruption-level: time-sensitive
```

Add a channel that is not a Companion app (admin only):

```yaml
action: notify_subscriptions.set_channel
data:
  id: telegram_andrii
  user_id: 0123456789abcdef0123456789abcdef   # Settings → People → Users
  name: Telegram
  target: notify.telegram_andrii               # notify service or notify entity
```

## Actions

| Action | Who | What it does |
|---|---|---|
| `notify_subscriptions.send` | automations | Sends `title`/`message`/`data` to every subscriber of `topic`. Returns which channels got it and which failed; one failing channel never blocks the others. |
| `notify_subscriptions.set_subscription` | the calling user | `mode`: `off`, `all`, `picked`, or `toggle` with `channel` to flip one device. Changes only the caller's subscription. |
| `notify_subscriptions.test` | the calling user | Sends a test of the topic to the caller's own subscribed channels. |
| `notify_subscriptions.set_topic` / `remove_topic` | admin | Manage topics. Removing a topic removes its subscriptions. |
| `notify_subscriptions.set_channel` / `remove_channel` | admin | Manage non-Companion channels. |
| `notify_subscriptions.import_legacy` | admin | Imports an `input_text` list of `u:<user_id>` / `d:<device_tracker>` tokens as subscriptions to a topic. Users that are not listed are set to `off`. |

A dashboard card for users to manage their own subscriptions is planned.

## Development

```bash
scripts/setup_dev_env.sh            # once: .venv-ha with Home Assistant + test dependencies (Python 3.13)
.venv-ha/bin/pytest                 # tests against a real Home Assistant core
scripts/dev_ha_ui.sh up             # real HA on http://127.0.0.1:8125 (admin / notify1234) with demo topics
scripts/dev_ha_ui.sh send air_raid "Test"   # shows up as a persistent notification in the HA UI
scripts/dev_ha_ui.sh down
```

`pre-commit install` runs ruff, mypy and pytest before each commit. CI runs the same checks plus
`hassfest` and HACS validation.

Releases: see [docs/VERSION_MANAGEMENT.md](docs/VERSION_MANAGEMENT.md) (`python scripts/bump_version.py patch --pr`,
the Release workflow tags and publishes after the merge).

## License

MIT
