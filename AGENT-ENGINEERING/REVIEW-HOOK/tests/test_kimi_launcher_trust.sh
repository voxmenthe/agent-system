#!/usr/bin/env bash
set -euo pipefail

review_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
repo_root=$(cd "${review_root}/../.." && pwd)
launcher="${REVIEW_HOOK_LAUNCHER_SOURCE:-${repo_root}/SHELL/.bash_agents}"
# shellcheck source=../../../SHELL/.bash_agents
source "$launcher"

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

test_root=$(mktemp -d "${TMPDIR:-/tmp}/kimi-launcher-trust.XXXXXX")
trap 'rm -rf "$test_root"' EXIT INT TERM

canonical_config="${test_root}/canonical.toml"
selected_config="${test_root}/selected.toml"
cat >"$canonical_config" <<'TOML'
default_model = "test"

[thinking]
effort = "max" # launcher-selected

[models.test]
provider = "test"
model = "test"
max_context_size = 1024
TOML
_kimi_write_selected_config "$canonical_config" "$selected_config" high
python3 - "$selected_config" <<'PY'
import pathlib
import sys
import tomllib

config = tomllib.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
assert config["thinking"]["effort"] == "high"
PY
if _kimi_write_selected_config "$canonical_config" "$selected_config" invalid 2>/dev/null; then
  fail "unsupported Kimi thinking effort was accepted"
fi

managed_canonical="${test_root}/managed canonical"
managed_home="${test_root}/managed selected"
mkdir -p "${managed_canonical}/hooks" "$managed_home"
cp "$canonical_config" "${managed_canonical}/config.toml"
ln -s "$review_root" "${managed_canonical}/hooks/review-after-commit"
_kimi_prepare_selected_home_unlocked "$managed_home" "$managed_canonical" high
python3 - "$managed_home" high <<'PY'
import hashlib
import json
import pathlib
import sys
import tomllib

home = pathlib.Path(sys.argv[1])
expected_effort = sys.argv[2]
payload = home.joinpath("config.toml").read_bytes()
config = tomllib.loads(payload.decode("utf-8"))
receipt = json.loads(
    home.joinpath("review-after-commit.kimi-config-receipt.json").read_text(
        encoding="utf-8"
    )
)
assert config["thinking"]["effort"] == expected_effort
assert receipt["current_digest"] == "sha256:" + hashlib.sha256(payload).hexdigest()
PY
_kimi_prepare_selected_home_unlocked "$managed_home" "$managed_canonical" max
python3 - "$managed_home" max <<'PY'
import hashlib
import json
import pathlib
import sys
import tomllib

home = pathlib.Path(sys.argv[1])
expected_effort = sys.argv[2]
payload = home.joinpath("config.toml").read_bytes()
config = tomllib.loads(payload.decode("utf-8"))
receipt = json.loads(
    home.joinpath("review-after-commit.kimi-config-receipt.json").read_text(
        encoding="utf-8"
    )
)
assert config["thinking"]["effort"] == expected_effort
assert receipt["current_digest"] == "sha256:" + hashlib.sha256(payload).hexdigest()
PY

work_dir="${test_root}/workspace with spaces"
kimi_home="${test_root}/kimi home"
mkdir -p "$work_dir" "${kimi_home}/bin"

cat >"${kimi_home}/bin/kimi" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
trust_dir="${KIMI_CODE_HOME}/workspace-trust"
shopt -s nullglob
records=("${trust_dir}"/*)
[[ ${#records[@]} -eq 1 && -f "${records[0]}" && ! -L "${records[0]}" ]]
python3 - "${records[0]}" "$(pwd -P)" <<'PY'
import json
import pathlib
import sys

record = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
assert record["root"] == sys.argv[2]
assert isinstance(record["trustedAt"], int) and record["trustedAt"] > 0
PY
SH
chmod 700 "${kimi_home}/bin/kimi"

(
  cd "$work_dir"
  KIMI_CANONICAL_HOME="$kimi_home" _kimi_launch normal --prompt test >/dev/null
)

trust_file=$(find -P "${kimi_home}/workspace-trust" -type f -maxdepth 1 -print)
[[ -n "$trust_file" ]] || fail "Kimi wrapper did not create a folder-trust record"
[[ $(stat -f '%Lp' "$trust_file") == "600" ]] || fail "folder-trust record is not private"
[[ $(stat -f '%Lp' "${kimi_home}/workspace-trust") == "700" ]] || fail "folder-trust directory is not private"

first_record=$(<"$trust_file")
sleep 0.02
(
  cd "$work_dir"
  _kimi_trust_working_directory "$kimi_home"
)
[[ $(<"$trust_file") == "$first_record" ]] || fail "existing folder trust was rewritten"

printf '{broken' >"$trust_file"
if (
  cd "$work_dir"
  _kimi_trust_working_directory "$kimi_home"
) 2>/dev/null; then
  fail "malformed existing folder trust was overwritten"
fi
[[ $(<"$trust_file") == "{broken" ]] || fail "malformed existing folder trust changed"

printf 'Kimi launcher folder trust: ok\n'
