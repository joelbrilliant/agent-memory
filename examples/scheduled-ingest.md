# Scheduled ingest

`agent-memory ingest` does a full rebuild every run, so keeping the index fresh is just a
matter of running it on a schedule. For a corpus of a few thousand files this
takes about a second, so a daily rebuild is more than enough. Both examples
below write ingest output to `ingest.log` in `~/.local/share/agent-memory`.

Replace `/REPLACE/WITH/YOUR/HOME` with your home folder. The command is the installed one in uv's tool folder (`uv tool dir --bin` prints it, usually `~/.local/bin`); a scheduler doesn't read your shell's `PATH`, so use the full path. A rebuild that can't read one of the files `corpus.txt` lists stops, keeps the previous index and says which file in the log.

## macOS (launchd)

Save this as `~/Library/LaunchAgents/com.example.agent-memory-ingest.plist`,
then load it with `launchctl load ~/Library/LaunchAgents/com.example.agent-memory-ingest.plist`.
It runs daily at 08:45 local time.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.example.agent-memory-ingest</string>
  <key>ProgramArguments</key>
  <array>
        <string>/REPLACE/WITH/YOUR/HOME/.local/bin/agent-memory</string>
    <string>ingest</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>8</integer>
    <key>Minute</key>
    <integer>45</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>/REPLACE/WITH/YOUR/HOME/.local/share/agent-memory/ingest.log</string>
  <key>StandardErrorPath</key>
  <string>/REPLACE/WITH/YOUR/HOME/.local/share/agent-memory/ingest.log</string>
</dict>
</plist>
```

To unload it later: `launchctl unload ~/Library/LaunchAgents/com.example.agent-memory-ingest.plist`.

## Linux (cron)

Add this line with `crontab -e`. It runs daily at 08:45 and appends output to
`ingest.log`.

```
45 8 * * * $HOME/.local/bin/agent-memory ingest >> $HOME/.local/share/agent-memory/ingest.log 2>&1
```
