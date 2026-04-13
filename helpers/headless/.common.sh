#!/bin/bash
# Common functions shared by all CondaTainer helper scripts.
# Source this at the top of every helper script:
#   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
#   source "$SCRIPT_DIR/.common.sh"

# ============= Colors =============
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
# ================= Message helpers =================
print_msg()  { echo -e "[MSG] $*"; }
print_info() { echo -e "[${CYAN}INFO${NC}] $*"; }
print_warn() { echo -e "[${YELLOW}WARN${NC}] $*"; }
print_error(){ echo -e "[${RED}ERR${NC}] $*" >&2; }
print_pass(){ echo -e "[${GREEN}PASS${NC}] $*"; }
trap 'echo; exit 130' INT # Add a newline on Ctrl+C and exit with code 130
# ============= Directories =============
# Follow XDG Base Directory spec for config and state locations
CONDATAINER_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/condatainer"
HELPER_DEFAULTS_DIR="$CONDATAINER_CONFIG_DIR/helper"
HELPER_STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/condatainer/helper"
_ORIGINAL_CWD=$(readlink -f .) # Capture user's pwd before any cd

# Check condatainer is available
if ! command -v condatainer &> /dev/null; then
    print_error "CondaTainer is not installed or not in PATH."
    print_info "Please go to https://github.com/Justype/condatainer to install CondaTainer."
    exit 1
fi

# Read log directory and scheduler timeout from condatainer config
LOG_DIR=$(condatainer config get logs_dir -q --local 2>/dev/null)
LOG_DIR="${LOG_DIR:-$HOME/logs}"
SCHEDULER_TIMEOUT=$(condatainer config get scheduler_timeout -q --local 2>/dev/null)
SCHEDULER_TIMEOUT="${SCHEDULER_TIMEOUT:-5}"

mkdir -p "$CONDATAINER_CONFIG_DIR" "$HELPER_DEFAULTS_DIR" "$HELPER_STATE_DIR" "$LOG_DIR"

# Ensure SCRATCH is set up
if [ -z "$SCRATCH" ]; then
    print_info "SCRATCH environment variable is not set. Falling back to HOME directory."
    SCRATCH="$HOME"
fi

# Known package versions — auto-updated by helpers/auto.py
POSIT_R_VERSIONS="4.5.3 4.5.2 4.5.1 4.5.0 4.4.3 4.4.2 4.4.1 4.4.0 4.3.3 4.3.2 4.3.1 4.3.0 4.2.3 4.2.2 4.2.1 4.2.0 4.1.3 4.1.2 4.1.1 4.1.0 4.0.5 4.0.4 4.0.3 4.0.2 4.0.1 4.0.0"
CONDA_PYTHON_VERSIONS="3.14.4 3.14.3 3.14.2 3.14.1 3.14.0 3.13.13 3.13.12 3.13.11 3.13.10 3.13.9 3.13.8 3.13.7 3.13.5 3.13.3 3.13.2 3.13.1 3.13.0 3.12.13 3.12.12 3.12.11 3.12.10 3.12.9 3.12.8 3.12.7 3.12.6 3.12.5 3.12.4 3.12.3 3.12.2 3.12.1 3.12.0 3.11.15 3.11.14 3.11.13 3.11.12 3.11.11 3.11.10 3.11.9 3.11.8 3.11.7 3.11.6 3.11.5 3.11.4 3.11.3 3.11.2 3.11.1 3.11.0 3.10.20 3.10.19 3.10.18 3.10.17 3.10.16 3.10.15 3.10.14 3.10.13 3.10.12 3.10.11 3.10.10 3.10.9 3.10.8 3.10.7 3.10.6 3.10.5 3.10.4 3.10.2 3.10.1 3.10.0 3.9.23 3.9.22 3.9.21 3.9.20 3.9.19 3.9.18 3.9.17 3.9.16 3.9.15 3.9.14 3.9.13 3.9.12 3.9.10 3.9.9 3.9.7 3.9.6 3.9.5 3.9.4 3.9.2 3.9.1 3.9.0"
CONDA_R_VERSIONS="4.5.3 4.5.2 4.5.1 4.4.3 4.4.2 4.4.1 4.4.0 4.3.3 4.3.2 4.3.1 4.3.0 4.2.3 4.2.2 4.2.1 4.2.0 4.1.3 4.1.2 4.1.1 4.1.0 4.0.5 4.0.3 4.0.2 4.0.1 4.0.0"

# ============= Config Functions =============

# config_load <helper-name>
#   Sources XDG config: $XDG_CONFIG_HOME/condatainer/helper/<name> (defaults to ~/.config/condatainer/helper/<name>) if it exists.
#   Updates the current shell environment with saved variables and set CWD to pwd.
#   Returns 0 if loaded, 1 if no saved config.
config_load() {
    local f="$HELPER_DEFAULTS_DIR/$1"
    if [ -f "$f" ]; then
        source "$f"
        CWD=$(readlink -f .)
        # Auto-save config defaults with _CONFIG_ prefix for comparison in print_specs
        local key
        while IFS='=' read -r key _; do
            [[ -z "$key" || "$key" =~ ^# ]] && continue
            printf -v "_CONFIG_${key}" '%s' "${!key}"
        done < "$f"
        return 0
    fi
    return 1
}

# config_init <helper-name> KEY=VALUE ...
#   Creates the defaults file on first run with the given key=value pairs.
#   If the file already exists, appends any missing keys without overwriting existing ones.
config_init() {
    local name="$1"; shift
    local f="$HELPER_DEFAULTS_DIR/$name"
    touch "$f"
    for pair in "$@"; do
        local key="${pair%%=*}"
        local val="${pair#*=}"
        grep -q "^${key}=" "$f" || printf '%s="%s"\n' "$key" "$val" >> "$f"
    done
}

# config_update <helper-name> KEY=VALUE ...
#   Updates specific keys in the defaults file without rewriting the whole file.
#   If the key exists, its value is replaced. If not, the key is appended.
config_update() {
    local name="$1"; shift
    local f="$HELPER_DEFAULTS_DIR/$name"
    touch "$f"
    for pair in "$@"; do
        local key="${pair%%=*}"
        local val="${pair#*=}"
        if grep -q "^${key}=" "$f"; then
            sed -i "s|^${key}=.*|${key}=\"${val}\"|" "$f"
        else
            printf '%s="%s"\n' "$key" "$val" >> "$f"
        fi
    done
}

# config_require <helper-name> VAR1 VAR2 ...
#   Checks that each named variable is set and non-empty. Exits on failure.
config_require() {
    local name="$1"; shift
    for var in "$@"; do
        if [ -z "${!var}" ]; then
            print_error "Required config variable ${YELLOW}$var${NC} is not set."
            print_info "Please check your config file: ${BLUE}$(config_path $name)${NC}"
            print_info "Or delete it to regenerate defaults."
            exit 1
        fi
    done
}

# config_show <helper-name>
#   Prints config file path and contents, then exits.
config_show() {
    local f="$HELPER_DEFAULTS_DIR/$1"
    echo -e "Config file: ${BLUE}$f${NC}"
    if [ -f "$f" ]; then
        echo "-------------"
        cat "$f"
    else
        echo "(no config file yet; will be created on first run)"
    fi
    exit 0
}

# config_path <helper-name>
#   Prints the path to the defaults file.
config_path() {
    echo "$HELPER_DEFAULTS_DIR/$1"
}

# state_path <helper-name>
#   Prints the path to the state file.
state_path() {
    echo "$HELPER_STATE_DIR/$1"
}

# resolve_overlay_list <colon-separated-overlays>
#   Converts file-path overlays to absolute paths, leaves named overlays as-is.
#   Takes colon-separated string, returns colon-separated string.
resolve_overlay_list() {
    local input="$1"
    [ -z "$input" ] && return 0

    local result=""
    local IFS=':'
    local -a arr=($input)

    for o in "${arr[@]}"; do
        [ -z "$o" ] && continue
        if echo "$o" | grep -qiE '\.(sqf|sqsh|squashfs|img)$'; then
            local abs_path=$(readlink -f "$o")
            result="${result:+$result:}$abs_path"
        else
            result="${result:+$result:}$o"
        fi
    done
    echo "$result"
}

# build_overlays_arg <colon-separated-overlays>
#   Rebuilds OVERLAYS_ARG from colon-separated overlay list.
#   Takes colon-separated string, returns argument string.
build_overlays_arg() {
    local input="$1"
    [ -z "$input" ] && return 0

    local arg=""
    local IFS=':'
    local -a arr=($input)

    for o in "${arr[@]}"; do
        [ -n "$o" ] && arg+=" -o \"$o\""
    done
    echo "$arg"
}

# ============= Prompt Functions =============

# confirm_default_yes <prompt> <prompt_hint>
#   Prompts the user with [Y/n]. Returns 0 if yes (default), 1 if no.
confirm_default_yes() {
    local prompt="$1"
    local prompt_hint="${2:-Y/n}"
    local resp
    read -p "[MSG] $prompt [$prompt_hint] " resp
    case "$resp" in
        ""|[Yy]*) return 0 ;;
        *) return 1 ;;
    esac
}

# confirm_default_no <prompt> <prompt_hint>
#   Prompts the user with [y/N]. Returns 0 if yes, 1 if no (default).
confirm_default_no() {
    local prompt="$1"
    local prompt_hint="${2:-y/N}"
    local resp
    read -p "[MSG] $prompt [$prompt_hint] " resp
    case "$resp" in
        [Yy]*) return 0 ;;
        *) return 1 ;;
    esac
}

# read_with_default <VAR> <prompt> <default>
#   Reads user input with readline editing; stores result in named variable.
#   Falls back to default if user presses Enter.
read_with_default() {
    local -n _rwd_target="$1"
    local prompt="$2" default="$3" _input
    read -r -e -p "[MSG] $prompt [$default]: " _input
    _rwd_target="${_input:-$default}"
}

# _print_version_groups <full_versions>
#   Displays versions grouped by major.minor, one row per group.
#   If a group has more than four patch releases, shows the first two and the last with an ellipsis.
#   e.g. "3.13.3 3.13.2 3.13.1 3.12.10 3.12.9" →
#     [INFO]   3.13: 3.13.3 ... 3.13.1
#     [INFO]   3.12: 3.12.10 3.12.9
_print_version_groups() {
    local prev_mm=""
    local -a group=()

    _print_group() {
        local mm="$1"
        shift
        local -a versions=("$@")

        case "${#versions[@]}" in
            0) return 0 ;;
            1|2|3|4)
                print_info "  ${mm}: ${versions[*]}"
                ;;
            *)
                print_info "  ${mm}: ${versions[0]} ${versions[1]} ... ${versions[$(( ${#versions[@]} - 1 ))]}"
                ;;
        esac
    }

    for _v in $1; do
        local mm="${_v%.*}"
        if [ -n "$prev_mm" ] && [ "$mm" != "$prev_mm" ]; then
            _print_group "$prev_mm" "${group[@]}"
            group=()
        fi
        group+=("$_v")
        prev_mm="$mm"
    done

    [ -n "$prev_mm" ] && _print_group "$prev_mm" "${group[@]}"
}

# read_version <VAR> <prompt> <default> <full_versions>
#   Displays available versions grouped by major.minor, then reads input.
#   Accepts both major.minor (e.g. 3.12) and full patch (e.g. 3.12.10).
read_version() {
    local -n _rv_target="$1"
    local prompt="$2" default="$3" full_vers="$4" _input
    if [ -n "$full_vers" ]; then
        print_info "Available ${prompt}s:"
        _print_version_groups "$full_vers"
    fi
    read -r -e -p "[MSG] $prompt [$default]: " _input
    _rv_target="${_input:-$default}"
}

# prompt_create_env_overlay
#   Prompts to create env.img with optional conda packages.
prompt_create_env_overlay() {
    print_warn "Overlay ${BLUE}$OVERLAY${NC} not found, which is required for Conda env."
    confirm_default_yes "Create one?" || exit 1
    local _size _pkgs
    read_with_default _size "Size" "20G"
    read -r -e -p "[MSG] Packages to install (e.g. go nodejs, empty to skip): " _pkgs
    if [ -n "$_pkgs" ]; then
        # shellcheck disable=SC2086
        condatainer o "$OVERLAY" -s "$_size" -- $_pkgs || exit 1
    else
        condatainer o "$OVERLAY" -s "$_size" || exit 1
    fi
}

# ============= Port Functions =============

# choose_port
#   Returns a random available port in 20000-65000.
choose_port() {
    local try=0
    while [ $try -lt 10 ]; do
        candidate=$(shuf -i 20000-65000 -n 1)
        if ! lsof -i :$candidate &> /dev/null; then
            echo $candidate
            return 0
        fi
        try=$((try+1))
    done
    return 1
}

# validate_port <port>
#   Validates port is a number in 1024-65535 range. Exits on error.
validate_port() {
    local port="$1"
    if ! printf '%s' "$port" | grep -qE '^[0-9]+$'; then
        print_error "Port must be a number."
        exit 2
    fi
    if [ "$port" -lt 1024 ] || [ "$port" -gt 65535 ]; then
        print_error "Port $port is out of allowed range (1024-65535)."
        exit 2
    fi
}

# check_port_available <port>
#   Exits if port is already in use.
check_port_available() {
    local port="$1"
    if lsof -i :$port &> /dev/null; then
        print_error "Port ${BLUE}$port${NC} is already in use."
        print_info "Please choose a different port using the ${YELLOW}-p${NC} option."
        exit 1
    fi
}

# ============= Overlay Functions =============

# check_overlay_integrity <overlay_file>
#   Runs e2fsck to check and repair overlay. Exits on failure.
check_overlay_integrity() {
    local overlay="$1"

    # Check if in use before running e2fsck
    check_overlay_in_use "$overlay"

    print_info "Checking overlay image integrity..."
    e2fsck -p "$overlay" > /dev/null 2>&1
    # 0 = clean, 1 = errors fixed, >1 = errors unfixable
    if [ $? -gt 1 ]; then
        print_error "Overlay ${BLUE}$overlay${NC} is corrupted and could not be auto repaired."
        print_info "Please run ${YELLOW}e2fsck $overlay${NC} manually to repair."
        exit 1
    fi
}

# check_writable <file>
#   Returns 0 if file is writable and not locked exclusively.
check_writable() {
    [[ -w "$1" ]] && flock -xn 9 9<>"$1" 2>/dev/null
}

# check_readable <file>
#   Returns 0 if file is readable and not locked for writing.
check_readable() {
    [[ -r "$1" ]] && flock -sn 9 9<"$1" 2>/dev/null
}

# require_writable <file>
#   Exits if file is not writable or is currently in use.
#   In headless mode, offers to kill processes holding the file.
require_writable() {
    local file="$1"
    if ! check_writable "$file"; then
        local pid_list=$(lsof "$file" 2>/dev/null | awk 'NR>1 {print $2}' | sort -u)
        if [ -n "$pid_list" ]; then
            print_warn "${BLUE}$file${NC} is currently in use by the following processes: $pid_list"
            if confirm_default_no "Do you want to kill these processes and continue?"; then
                for pid in $pid_list; do
                    kill -9 $pid 2>/dev/null
                done
                print_info "Sent SIGKILL to processes using the file."
                sleep 1
                # Final check after kill
                check_writable "$file" || {
                    print_error "File still in use after kill attempt."
                    exit 1
                }
            else
                print_msg "Aborted."
                exit 1
            fi
        else
            print_error "Can't open ${BLUE}$file${NC} for writing, currently in use."
            exit 1
        fi
    fi
}

# check_overlay_in_use <overlay_file>
#   Checks if overlay is available for writing using flock.
check_overlay_in_use() {
    local overlay="$1"

    # Only .img files support locking
    [[ "$overlay" != *".img" ]] && return 0
    [ ! -f "$overlay" ] && return 0

    require_writable "$overlay"
}

# check_and_install_overlays <pkgs...>
#   Checks if required overlays exist and installs missing ones.
#   Each argument can be a single overlay name or a colon-separated list.
check_and_install_overlays() {
    print_info "Checking required overlays..."
    local -a missing=()
    for arg in "$@"; do
        # Split on colon to handle colon-separated overlay lists
        local IFS=':'
        local -a pkgs=($arg)
        for pkg in "${pkgs[@]}"; do
            [ -z "$pkg" ] && continue
            if echo "$pkg" | grep -qiE '\.(sqf|sqsh|squashfs|img)$'; then
                if [ ! -f "$pkg" ]; then
                    print_error "Overlay file ${BLUE}$pkg${NC} not found."
                    exit 1
                fi
            else
                if ! condatainer list -e "$pkg" > /dev/null 2>&1; then
                    missing+=("$pkg")
                fi
            fi
        done
    done
    if [ ${#missing[@]} -gt 0 ]; then
        print_info "Installing missing overlays: ${missing[*]}."
        condatainer create "${missing[@]}"
        if [ $? -ne 0 ]; then
            print_error "Failed to install required overlays."
            exit 1
        fi
    fi
}

# resolve_env_overlay
#   If OVERLAY is exactly "env.img", searches for the file in order:
#     1. env.img         (current directory)
#     2. overlay/env.img
#     3. src/overlay/env.img
#   Sets OVERLAY to the found relative path for the current run.
#   Sets _OVERLAY_ORIGINAL="env.img" so state files preserve the portable name.
resolve_env_overlay() {
    [ "$OVERLAY" != "env.img" ] && return 0
    _OVERLAY_ORIGINAL="env.img"
    local -a candidates=("env.img" "overlay/env.img" "src/overlay/env.img")
    for candidate in "${candidates[@]}"; do
        if [ -f "$candidate" ]; then
            OVERLAY="$candidate"
            return 0
        fi
    done
}

# ============= Reuse Mode Functions =============

# spec_line <label> <VAR_NAME>
#   Prints one spec line. Shows "(default: X)" if value differs from
#   config default and was not set via CLI (_ARG_ prefix).
spec_line() {
    local label="$1" var="$2"
    local val="${!var}"
    [ -z "$val" ] && return

    local arg_var="_ARG_${var}"
    local config_var="_CONFIG_${var}"
    local note=""

    if [ -z "${!arg_var:-}" ] && [ -n "${!config_var:-}" ]; then
        if [ "$val" != "${!config_var}" ]; then
            note=" (default: ${!config_var})"
        else
            note=" (default)"
        fi
    fi

    local current_len=$(( ${#label} + ${#val} + 4 )) # 4 for beginning space and ": "
    local pad_width=22
    local spaces=""

    if [ "$current_len" -lt "$pad_width" ]; then
        local diff=$(( pad_width - current_len ))
        spaces=$(printf '%*s' "$diff" "")
    fi

    print_msg "  ${label}: ${BLUE}${val}${NC}${spaces}${note}"
}

# print_specs
#   Prints all current job settings. Override in helper scripts for custom fields.
print_specs() {
    spec_line "Port" PORT
    local cwd_hint=""
    local current_dir="${_ORIGINAL_CWD:-$(readlink -f .)}"
    [ "$CWD" != "$current_dir" ] && cwd_hint=" (use -w for current dir)"
    print_msg "  Working Dir: ${BLUE}$CWD${NC}${cwd_hint}"
    spec_line "Base Image" BASE_IMAGE
    spec_line "Overlay" OVERLAY
    [ -n "$OVERLAYS" ] && print_msg "  Additional overlays: ${BLUE}$OVERLAYS${NC}"
}

# countdown [seconds]
#   Prints a countdown with Ctrl+C hint, overwriting the same line each tick.
countdown() {
    local secs="${1:-3}"
    while [ "$secs" -gt 0 ]; do
        printf "\r[MSG] Press Ctrl+C to cancel %d " "$secs"
        sleep 1
        secs=$((secs - 1))
    done
    printf "\r\033[K"
}

# Flag: set to true when print_specs already displayed specs
_SPECS_SHOWN=false

# handle_reuse_mode <helper_name>
#   Handles REUSE_MODE logic when a previous state file exists.
#   Sets global REUSE_PREVIOUS_CWD=true if reusing, false otherwise.
handle_reuse_mode() {
    local helper_name="$1"

    if [ -z "$OVERLAY" ]; then
        config_load "$helper_name"
        return
    fi

    # CLI args given - keep state values with CLI overrides, no prompt
    if [ "${OPTIND:-1}" -gt 1 ]; then
        REUSE_PREVIOUS_CWD=true
        return
    fi

    case "${REUSE_MODE,,}" in  # Convert to lowercase
        always)
            print_info "Auto-reusing previous settings (REUSE_MODE=always)."
            REUSE_PREVIOUS_CWD=true
            ;;
        never)
            print_info "Not reusing previous settings (REUSE_MODE=never)."
            config_load "$helper_name"
            OVERLAYS=""
            rm -f "$STATE_FILE"
            ;;
        *)
            if [ "${REUSE_MODE,,}" != "ask" ]; then
                print_warn "Invalid REUSE_MODE='$REUSE_MODE'. Defaulting to 'ask'."
            fi
            print_msg "Previous settings:"
            print_specs
            if confirm_default_yes "Reuse?" "Y: accept / n: defaults (use pwd) / Ctrl+C: cancel"; then
                REUSE_PREVIOUS_CWD=true
                _SPECS_SHOWN=true
            else
                config_load "$helper_name"
                OVERLAYS=""
                print_msg "Using default settings:"
                print_specs
                _SPECS_SHOWN=true
            fi
            ;;
    esac
}

# read_headless_state <state_file>
#   Sources state file and loads previous settings.
#   Returns: 0 = no state file, 3 = has previous state
read_headless_state() {
    local state_file="$1"
    [ ! -f "$state_file" ] && return 0
    source "$state_file"
    return 3
}
