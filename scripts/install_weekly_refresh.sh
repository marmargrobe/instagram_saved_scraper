#!/bin/bash
# Run the refresh pipeline every Sunday at 9:00 with macOS launchd (the Mac's built-in scheduler).
# If the Mac is asleep at that time, the run happens at the next wake.
#
#   scripts/install_weekly_refresh.sh              # install / update the schedule
#   scripts/install_weekly_refresh.sh --uninstall  # remove it
#
# Runs are logged in ops.pipeline_runs (triggered_by = 'schedule') and in logs/refresh.log.
set -euo pipefail

LABEL="com.saved-instagram.refresh"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$PROJECT_ROOT/.venv_data_cleaner/bin/python"

if [[ "${1:-}" == "--uninstall" ]]; then
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
    rm -f "$PLIST"
    echo "Weekly refresh removed."
    exit 0
fi

[[ -x "$PYTHON" ]] || { echo "Missing $PYTHON (create .venv_data_cleaner first)"; exit 1; }
mkdir -p "$PROJECT_ROOT/logs" "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON</string>
        <string>-W</string><string>ignore</string>
        <string>-m</string><string>src.pipeline.refresh</string>
        <string>--triggered-by</string><string>schedule</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$PROJECT_ROOT</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key><integer>0</integer>
        <key>Hour</key><integer>9</integer>
        <key>Minute</key><integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>$PROJECT_ROOT/logs/refresh.log</string>
    <key>StandardErrorPath</key>
    <string>$PROJECT_ROOT/logs/refresh.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Weekly refresh installed: Sundays at 9:00 (next wake if asleep)."
echo "Run it now to test:  launchctl kickstart gui/$(id -u)/$LABEL"
