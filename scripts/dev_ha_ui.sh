#!/usr/bin/env bash
# Starts a REAL Home Assistant (UI on :8125) with the notify_subscriptions integration.
# Fully automatic: onboarding, config entry, demo topics and a channel that shows every
# notification as a persistent notification in the HA UI (no phone needed).
#
#   scripts/dev_ha_ui.sh up                     — start HA, set everything up
#   scripts/dev_ha_ui.sh send <topic> [message] — call notify_subscriptions.send
#   scripts/dev_ha_ui.sh sub <topic> <off|all|picked>  — change the admin's subscription
#   scripts/dev_ha_ui.sh show                   — print the stored topics/channels/subscriptions
#   scripts/dev_ha_ui.sh restart                — restart HA only (checks the data survives)
#   scripts/dev_ha_ui.sh down                   — stop
#
# Port 8125 avoids a clash with ha-silpo (8123) and ha-poltava-poweroff (8124).
set -euo pipefail
cd "$(dirname "$0")/.."
VENV="${VENV:-$PWD/.venv-ha}/bin"
CFG="$PWD/ha_config"
PORT_HA="${PORT_HA:-8125}"
BASE="http://127.0.0.1:$PORT_HA"
USER_NAME=admin
USER_PASS=notify1234

_pids_on() { lsof -ti :"$1" 2>/dev/null || true; }
_wait_port_free() { for _ in $(seq 1 20); do [ -z "$(_pids_on "$1")" ] && return 0; sleep 1; done; return 1; }
_wait_ha() { for _ in $(seq 1 60); do curl -sf -o /dev/null "$BASE/" 2>/dev/null && return 0; sleep 3; done; return 1; }
_hass_pids() { pgrep -f "hass --config $CFG" || true; }
_token() { cat "$CFG/.ha_token"; }

_api() {
  # _api <service> <json>
  curl -sf -X POST "$BASE/api/services/notify_subscriptions/$1" \
    -H "Authorization: Bearer $(_token)" -H 'Content-Type: application/json' -d "$2"
}

_owner_id() {
  "$VENV/python" -c "
import json, sys
users = json.load(open('$CFG/.storage/auth'))['data']['users']
print(next(u['id'] for u in users if u.get('is_owner')))"
}

cmd_up() {
  cmd_down >/dev/null
  rm -rf "$CFG"; mkdir -p "$CFG/custom_components"
  ln -sfn "$PWD/custom_components/notify_subscriptions" "$CFG/custom_components/notify_subscriptions"
  cat > "$CFG/configuration.yaml" <<YAML
# no default_config: faster start, no bluetooth (crashes on macOS on shutdown)
homeassistant:
  name: Notify (dev)
  unit_system: metric
  time_zone: Europe/Kyiv
  country: UA
  language: uk
frontend:
http:
  server_port: $PORT_HA
api:
config:
mobile_app:
notify:
persistent_notification:
logger:
  default: warning
  logs:
    custom_components.notify_subscriptions: debug
YAML
  nohup "$VENV/hass" --config "$CFG" > "$CFG/ha.log" 2>&1 &
  echo "hass PID $! (waiting for $BASE ...)"
  _wait_ha || { echo "HA did not start"; tail -30 "$CFG/ha.log"; exit 1; }
  ACCESS=$("$VENV/python" scripts/ha_auth.py "$BASE" "$USER_NAME" "$USER_PASS" | tail -1)
  [ -z "$ACCESS" ] && { echo "auth failed"; exit 1; }
  echo "$ACCESS" > "$CFG/.ha_token"

  # config entry (one-step flow)
  FLOW=$(curl -sf -X POST "$BASE/api/config/config_entries/flow" -H "Authorization: Bearer $ACCESS" \
    -H 'Content-Type: application/json' -d '{"handler":"notify_subscriptions"}' | "$VENV/python" -c 'import json,sys;print(json.load(sys.stdin)["flow_id"])')
  curl -sf -X POST "$BASE/api/config/config_entries/flow/$FLOW" -H "Authorization: Bearer $ACCESS" \
    -H 'Content-Type: application/json' -d '{}' >/dev/null

  # demo topics, the same as on the real instance
  _api set_topic '{"id":"air_raid","name":"Повітряна тривога","icon":"mdi:bell-ring","default_mode":"all"}' >/dev/null
  _api set_topic '{"id":"power_change","name":"Світло зникло / зʼявилось","icon":"mdi:transmission-tower","default_mode":"all"}' >/dev/null
  _api set_topic '{"id":"power_warning","name":"Світло вимкнеться через 5 хв","icon":"mdi:timer-alert-outline","default_mode":"off"}' >/dev/null
  # a channel you can see without a phone: Settings -> Notifications in the HA UI
  _api set_channel "{\"id\":\"ui\",\"user_id\":\"$(_owner_id)\",\"name\":\"HA UI\",\"target\":\"notify.persistent_notification\"}" >/dev/null

  echo ""; echo "✅ READY. UI: $BASE  ($USER_NAME / $USER_PASS)"
  echo "   Try: scripts/dev_ha_ui.sh send air_raid 'Тривога!'  -> bell icon in the HA sidebar"
  cmd_show
}

cmd_send() {
  _api 'send?return_response' "{\"topic\":\"$1\",\"title\":\"$1\",\"message\":\"${2:-Test from dev_ha_ui.sh}\"}"; echo
}

cmd_sub() {
  _api set_subscription "{\"topic\":\"$1\",\"mode\":\"$2\"}" >/dev/null && echo "ok"; cmd_show
}

cmd_show() {
  "$VENV/python" -c "
import json, os
p = '$CFG/.storage/notify_subscriptions'
if not os.path.exists(p): print('  (nothing stored yet)'); raise SystemExit
print(json.dumps(json.load(open(p))['data'], ensure_ascii=False, indent=2))"
}

cmd_restart() {
  pkill -TERM -f "hass --config $CFG" 2>/dev/null || true
  for _ in $(seq 1 20); do [ -z "$(_hass_pids)" ] && break; sleep 1; done
  _wait_port_free "$PORT_HA" || true
  nohup "$VENV/hass" --config "$CFG" > "$CFG/ha.log" 2>&1 &
  echo "hass PID $! (waiting...)"
  _wait_ha || { echo "HA did not start"; tail -30 "$CFG/ha.log"; exit 1; }
  cmd_show
}

cmd_down() {
  pkill -TERM -f "hass --config $CFG" 2>/dev/null || true
  for _ in $(seq 1 15); do [ -z "$(_hass_pids)" ] && break; sleep 1; done
  pkill -9 -f "hass --config $CFG" 2>/dev/null || true
  _pids_on "$PORT_HA" | xargs kill -9 2>/dev/null || true
  echo "stopped"
}

case "${1:-up}" in
  up) cmd_up ;;
  send) cmd_send "${2:?topic}" "${3:-}" ;;
  sub) cmd_sub "${2:?topic}" "${3:?off|all|picked}" ;;
  show) cmd_show ;;
  restart) cmd_restart ;;
  down) cmd_down ;;
  *) echo "usage: $0 {up|send <topic> [message]|sub <topic> <mode>|show|restart|down}"; exit 1 ;;
esac
