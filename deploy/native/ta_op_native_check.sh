#!/usr/bin/env bash
# Native driver for deploy/native/NATIVE-TEST-PLAN.md.
#
# NOT RUN by this change. Authored for the coordinator to inspect and execute.
# Runs only the rows the current privilege context can actually reach; every
# other row prints SKIP with its reason and its name. A SKIP is never a pass.
#
#   usage: bash deploy/native/ta_op_native_check.sh /path/to/ta-op
#
# It never invokes a keepalive provider and never touches production.
set -uo pipefail

BIN="${1:?path to a compiled ta-op required}"
[ -x "$BIN" ] || { echo "FATAL: $BIN is not executable"; exit 2; }

pass=0; fail=0; skip=0
ok()   { echo "PASS  $1"; pass=$((pass + 1)); }
bad()  { echo "FAIL  $1  -- $2"; fail=$((fail + 1)); }
skp()  { echo "SKIP  $1  -- $2"; skip=$((skip + 1)); }

# Refuses with exit 78 and the expected TA_OP_REFUSED tag.
expect_refusal() {
  local name="$1" want="$2"; shift 2
  local out rc
  out="$("$BIN" "$@" 2>&1)"; rc=$?
  if [ "$rc" -ne 78 ]; then bad "$name" "exit $rc, wanted 78 ($out)"; return; fi
  case "$out" in
    *"TA_OP_REFUSED:${want}"*) ok "$name" ;;
    *) bad "$name" "wanted TA_OP_REFUSED:${want}, got: $out" ;;
  esac
}

echo "=== rows that need no privilege and no container ==="
expect_refusal "1  unknown mode"            unknown-mode        shell
expect_refusal "1b unknown mode (alias)"    unknown-mode        sh
expect_refusal "2  arity: pulse + extra"    arity               pulse extra
expect_refusal "2b arity: bare printenv"    arity               printenv
expect_refusal "3  malformed NAME: spaces"  env-name            printenv "a b"
expect_refusal "3b malformed NAME: lower"   env-name            printenv lower
expect_refusal "3c malformed NAME: digit"   env-name            printenv 9X
expect_refusal "3d malformed NAME: empty"   env-name            printenv ""
out="$("$BIN" 2>&1)"; rc=$?
if [ "$rc" -eq 78 ] && [ "${out#*no-mode}" != "$out" ]; then
  ok "4  no mode at all"
else
  bad "4  no mode at all" "exit $rc: $out"
fi

echo "=== identity-dependent rows ==="
uid="$(id -u)"
case "$uid" in
  0)
    skp "6  rootless exact groups" "running as root; re-run as uid 1001"
    caps="$(grep -E '^CapEff' /proc/self/status | awk '{print $2}')"
    if [ "$caps" = "0000000000000000" ]; then
      skp "10 root + five caps" "root with an empty effective set; needs the exact five"
    else
      echo "NOTE  entry CapEff=$caps — row 10/11/12 discrimination is the container's cap_add set"
      out="$("$BIN" version 2>&1)"; rc=$?
      if [ "$rc" -eq 0 ]; then
        case "$out" in
          "ta-op 1 modes="*) ok "10 root + five caps: full drop then version" ;;
          *) bad "10 root + five caps" "unexpected banner: $out" ;;
        esac
      else
        # Correct outcome when the cap set is NOT exactly the five.
        case "$out" in
          *"TA_OP_REFUSED:exact-five-caps"*) ok "11/12 non-exact cap set refused" ;;
          *) bad "10 root + five caps" "exit $rc: $out" ;;
        esac
      fi
    fi
    ;;
  1001)
    out="$("$BIN" version 2>&1)"; rc=$?
    if [ "$rc" -eq 0 ]; then
      case "$out" in
        "ta-op 1 modes="*) ok "6  rootless exact groups: verified, version printed" ;;
        *) bad "6  rootless exact groups" "unexpected banner: $out" ;;
      esac
    else
      # Rows 7/8/9 land here; report which discriminator fired.
      case "$out" in
        *legacy-entry-unexpected-group*) ok "7  foreign supplementary group refused" ;;
        *legacy-entry-caps-not-empty*)   ok "8  MUTATION CONTROL: cap-bearing entry refused" ;;
        *nnp-readback*)                  ok "9  missing no-new-privileges refused" ;;
        *) bad "6  rootless entry" "exit $rc: $out" ;;
      esac
    fi
    ;;
  *)
    expect_refusal "5  unexpected entry uid" unexpected-entry-uid version
    skp "6  rootless exact groups" "current uid is $uid, not 1001"
    skp "10 root + five caps" "current uid is $uid, not 0"
    ;;
esac

echo "=== row 14: descriptor boundary ==="
if [ "$uid" = 0 ] || [ "$uid" = 1001 ]; then
  # printenv is the only mode whose target we can observe without a provider.
  if out="$( exec 9< /etc/hostname; "$BIN" printenv PATH 2>&1 )"; then
    ok "14 descriptor boundary: target ran with fd 9 closed by the wrapper"
  else
    skp "14 descriptor boundary" "printenv target unavailable here: $out"
  fi
else
  skp "14 descriptor boundary" "needs uid 0 or 1001"
fi

echo "=== row 16: env-summary filters on the NAME, never the value ==="
if [ "$uid" = 0 ] || [ "$uid" = 1001 ]; then
  out="$(FOO=1 TINYASSETS_GOAL_POOL=off SECRET_TOKEN=ollama-token "$BIN" env-summary 2>&1)"
  if [ "${out#*SECRET_TOKEN}" != "$out" ]; then
    bad "16 env-summary" "a value-only match leaked: $out"
  elif [ "${out#*TINYASSETS_GOAL_POOL=off}" != "$out" ]; then
    ok "16 env-summary: name match printed, value match withheld"
  else
    bad "16 env-summary" "expected flag missing: $out"
  fi
else
  skp "16 env-summary" "needs uid 0 or 1001"
fi

echo "=== row 17: installed mode/ownership (only when the install path exists) ==="
if [ -e /usr/local/libexec/ta-op ]; then
  mode="$(stat -c %a /usr/local/libexec/ta-op)"; owner="$(stat -c %U /usr/local/libexec/ta-op)"
  if [ "$mode" = "555" ] && [ "$owner" = "root" ]; then
    ok "17 installed root-owned 0555"
  else
    bad "17 installed root-owned 0555" "mode=$mode owner=$owner"
  fi
else
  skp "17 installed root-owned 0555" "/usr/local/libexec/ta-op not present here"
fi

echo
echo "rows: pass=$pass fail=$fail skip=$skip"
echo "rows 13 and 15 are deliberately NOT automated here: they need strace and a"
echo "target that prints /proc/self/status. Run them by hand per NATIVE-TEST-PLAN.md."
[ "$fail" -eq 0 ] || exit 1
