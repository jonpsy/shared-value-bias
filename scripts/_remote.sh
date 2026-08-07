# sourced by move_to_cloud.sh / pull_from_cloud.sh -- caches the SSH target
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE_CACHE="$REPO_ROOT/.remote"

load_remote() {
  if [ -f "$REMOTE_CACHE" ]; then
    # shellcheck disable=SC1090
    source "$REMOTE_CACHE"
    echo "  cached target: ${SSH_HOST}:${REMOTE_DIR}"
    read -r -p "  use it? [Y/n] " yn
    [[ "$yn" == "n" || "$yn" == "N" ]] || return 0
  fi
  read -r -p "SSH host (e.g. root@sshXX.jarvislabs.net): " SSH_HOST
  read -r -p "Remote dir [/home/shared-value-bias/]: " REMOTE_DIR
  REMOTE_DIR="${REMOTE_DIR:-/home/shared-value-bias/}"
  case "$REMOTE_DIR" in
    /workspace*)
      echo "  WARNING: JarvisLabs does not persist outside /home across pause/resume."
      read -r -p "  Continue anyway? [y/N] " c
      [[ "$c" == "y" || "$c" == "Y" ]] || exit 1 ;;
  esac
  printf 'SSH_HOST=%q\nREMOTE_DIR=%q\n' "$SSH_HOST" "$REMOTE_DIR" > "$REMOTE_CACHE"
}
