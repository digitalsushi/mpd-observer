#!/usr/bin/env bash
set -euo pipefail

settings_path="${MPD_OBSERVER_SETTINGS:-$HOME/.mpd-observer/SETTINGS.yaml}"
if [[ ! -f "$settings_path" ]]; then
  settings_path="SETTINGS.yaml"
fi

deploy_host=""
deploy_username=""
deploy_identity=""
deploy_dir=""
while IFS='=' read -r key value; do
  case "$key" in
    host) deploy_host="$value" ;;
    username) deploy_username="$value" ;;
    identity_file) deploy_identity="$value" ;;
    directory) deploy_dir="$value" ;;
  esac
done < <(PYTHONPATH=src python3 - "$settings_path" <<'PY'
import sys
from pathlib import Path
from mpd_observer.settings import load_settings
d = load_settings(Path(sys.argv[1])).deployment
for key, value in (("host", d.host), ("username", d.username),
                   ("identity_file", d.identity_file), ("directory", d.directory)):
    print(f"{key}={value}")
PY
)

deploy_host="${MPD_OBSERVER_DEPLOY_HOST:-$deploy_host}"
deploy_username="${MPD_OBSERVER_DEPLOY_USERNAME:-$deploy_username}"
deploy_identity="${MPD_OBSERVER_DEPLOY_IDENTITY:-$deploy_identity}"
deploy_dir="${MPD_OBSERVER_DEPLOY_DIR:-$deploy_dir}"
if [[ -z "$deploy_host" || -z "$deploy_username" ]]; then
  echo "Deployment host and username must be set in $settings_path" >&2
  exit 1
fi
deploy_target="$deploy_username@$deploy_host"
ssh_command="ssh -i $deploy_identity -o BatchMode=yes -o ConnectTimeout=10"

if [[ ! -f "$deploy_identity" ]]; then
  echo "SSH identity not found: $deploy_identity" >&2
  exit 1
fi
if [[ "$deploy_dir" == /* || "$deploy_dir" == *..* ]]; then
  echo "Deployment directory must be a safe path relative to the remote home" >&2
  exit 1
fi

echo "Deploying code to $deploy_target:\$HOME/$deploy_dir"
echo "Preserving remote SETTINGS.yaml, .cache, and the currently installed environment."

$ssh_command "$deploy_target" "mkdir -p \"\$HOME/$deploy_dir\" \"\$HOME/.mpd-observer\"; if [[ ! -f \"\$HOME/.mpd-observer/SETTINGS.yaml\" && -f \"\$HOME/$deploy_dir/SETTINGS.yaml\" ]]; then cp \"\$HOME/$deploy_dir/SETTINGS.yaml\" \"\$HOME/.mpd-observer/SETTINGS.yaml\"; fi"

# Root project files are explicit so site settings and runtime data never get
# overwritten. --delete applies only within source-controlled code directories.
rsync -a -e "$ssh_command" \
  README.md SETTINGS.yaml setup.py setup.cfg .editorconfig \
  "$deploy_target:$deploy_dir/"
rsync -a --delete -e "$ssh_command" src/ "$deploy_target:$deploy_dir/src/"
rsync -a --delete -e "$ssh_command" tests/ "$deploy_target:$deploy_dir/tests/"
rsync -a --delete -e "$ssh_command" docs/ "$deploy_target:$deploy_dir/docs/"

$ssh_command "$deploy_target" "DEPLOY_DIR=\"\$HOME/$deploy_dir\" bash -s" <<'REMOTE'
set -euo pipefail
cd "$DEPLOY_DIR"

settings_path="$HOME/.mpd-observer/SETTINGS.yaml"
if [[ ! -f "$settings_path" ]]; then
  echo "Refusing to deploy without $settings_path" >&2
  exit 1
fi

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup=""
if [[ -d .venv ]]; then
  backup=".venv.previous.$stamp"
  mv .venv "$backup"
fi

restore_environment() {
  status=$?
  if [[ $status -ne 0 ]]; then
    if [[ -d .venv ]]; then
      mv .venv ".venv.failed.$stamp"
    fi
    if [[ -n "$backup" && -d "$backup" ]]; then
      mv "$backup" .venv
    fi
    echo "Deployment failed; the previous environment was restored." >&2
  fi
  exit "$status"
}
trap restore_environment EXIT

python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -c 'from mpd_observer.settings import default_settings_path, load_settings; path=default_settings_path(); load_settings(path); print(f"{path}: valid")'

trap - EXIT
echo "Deployment verified. Application was not started."
if [[ -n "$backup" ]]; then
  echo "Previous environment retained at: $DEPLOY_DIR/$backup"
fi
REMOTE
