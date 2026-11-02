#!/usr/bin/env bash
set -e
args=()
for arg in "$@"; do
    case "$arg" in
        --target=x86_64-pc-windows-gnu) ;;
        -Wl,*.def) args+=("${arg#-Wl,}") ;;
        *) args+=("$arg") ;;
    esac
done
exec "${TM2020_ZIG:-/home/uwucode/Projects/EvilRLBot-Windows/build/zig/zig}" cc -target x86_64-windows-gnu "${args[@]}"
