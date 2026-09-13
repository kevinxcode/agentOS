#!/usr/bin/env bash
# Run the checked-in production Compose contract against one explicit protected env.
set -euo pipefail
if (($# < 3)); then
  echo 'Usage: agentos-compose.sh agentos-project /absolute/.env COMPOSE_ARGUMENT...' >&2
  exit 2
fi
# shellcheck source=scripts/operations_common.sh
source "$(dirname "${BASH_SOURCE[0]}")/operations_common.sh"
configure_target "$1" "$2"
shift 2
exec "${compose[@]}" "$@"
