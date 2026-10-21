MimiWork now starts on Macs where an earlier installer left the `~/.config` folder owned by the administrator account.

- **Starts instead of "Server unreachable"**: when MimiWork can't write to `~/.config/coworker`, it now keeps its settings and logs in `~/Library/Application Support/coworker` on macOS (`~/.local/state/coworker` on Linux) and starts normally. Existing settings in `~/.config/coworker` stay where they are and are used as before.
- **A reason instead of an empty log**: if neither folder can be written, Settings ▸ Copy diagnostic log now names the folder and the Terminal command that fixes it, instead of "(log is empty)".
