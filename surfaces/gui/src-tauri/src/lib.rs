//! MimiWork desktop shell.
//!
//! Tauri is a thin native window over the existing React SPA. It:
//!   1. picks a free localhost port and starts the Python `openworker-server` as a managed
//!      sidecar on that port (so it never clashes with a hand-run server on 8765);
//!   2. injects the sidecar HTTP/WS addresses and per-launch authentication token before the
//!      SPA loads (single codebase — the browser build still hits 8765);
//!   3. lives in the system tray: closing the window hides it (keeps MyHelper + the scheduler
//!      running); only tray → Quit stops the sidecar;
//!   4. exposes native commands: folder picker, autostart (open-at-login), and keep-awake
//!      (caffeinate, so scheduled tasks fire while the Mac is idle).
//!
//! The sidecar inherits this process's environment, so a shell-launched `npm run tauri dev`
//! passes `OPENAI_API_KEY` through. A Finder-launched app has no shell env — there the key
//! comes from the SecretStore (Settings tab), see `coworker.providers.resolve_api_key`.

use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
#[cfg(target_os = "windows")]
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};

use ocw_stt::{Dictation, DownloadProgress};
use serde::Serialize;
use tauri::{
    menu::{Menu, MenuItem},
    tray::TrayIconBuilder,
    Emitter, Manager, RunEvent, WebviewUrl, WebviewWindowBuilder, WindowEvent,
};
use tauri_plugin_autostart::ManagerExt;
use uuid::Uuid;

/// The sidecar server child — killed on exit (orphaned servers have bitten us before).
struct ServerProcess(Mutex<Option<Child>>);
/// The active keep-awake guard while keep-awake is on (None when off). Dropping the guard
/// releases the hold (kills `caffeinate` on macOS, clears the execution state on Windows).
struct KeepAwake(Mutex<Option<KeepAwakeGuard>>);

fn free_port() -> u16 {
    std::net::TcpListener::bind("127.0.0.1:0")
        .and_then(|l| l.local_addr())
        .map(|a| a.port())
        .unwrap_or(8765)
}

fn launch_token() -> String {
    format!("{}{}", Uuid::new_v4().simple(), Uuid::new_v4().simple())
}

/// Path to the server entrypoint. Resolution order:
///   1. `COWORKER_SERVER_BIN` env override.
///   2. The bundled onedir sidecar shipped via Tauri `resources` (production): the
///      `sidecar/` folder lands in Contents/Resources on macOS and in the install dir
///      (next to the app exe) on Windows.
///   3. Legacy onefile slot: `openworker-server[.exe]` next to the app binary (pre-onedir
///      builds used Tauri externalBin).
///   4. Dev fallback: the repo venv, relative to this crate (`src-tauri` → repo-root `.venv`;
///      `bin/` on POSIX, `Scripts\` on Windows).
fn server_bin() -> PathBuf {
    if let Ok(p) = std::env::var("COWORKER_SERVER_BIN") {
        return PathBuf::from(p);
    }
    let exe_name = if cfg!(windows) {
        "openworker-server.exe"
    } else {
        "openworker-server"
    };
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            // macOS: Contents/MacOS/<app> → Contents/Resources/sidecar/; Windows: resources
            // unpack next to the exe, so <install>/sidecar/.
            let mut candidates = vec![dir.join("sidecar").join(exe_name)];
            if let Some(contents) = dir.parent() {
                candidates.push(contents.join("Resources").join("sidecar").join(exe_name));
            }
            candidates.push(dir.join(exe_name)); // legacy onefile externalBin slot
            for c in candidates {
                if c.exists() {
                    return c;
                }
            }
        }
    }
    let mut p = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    if cfg!(windows) {
        p.push("../../../.venv/Scripts/openworker-server.exe");
    } else {
        p.push("../../../.venv/bin/openworker-server");
    }
    p
}

/// Mirror of `coworker.secrets.state_dir()` so the shell and server agree on `desktop.json`.
/// Windows: `%APPDATA%\coworker`; POSIX: `~/.config/coworker`. `COWORKER_STATE_DIR` overrides.
fn state_dir() -> PathBuf {
    if let Ok(d) = std::env::var("COWORKER_STATE_DIR") {
        return PathBuf::from(d);
    }
    #[cfg(windows)]
    {
        if let Ok(appdata) = std::env::var("APPDATA") {
            return PathBuf::from(appdata).join("coworker");
        }
    }
    let home = std::env::var("HOME").unwrap_or_else(|_| ".".into());
    PathBuf::from(home).join(".config").join("coworker")
}

fn desktop_prefs_path() -> PathBuf {
    state_dir().join("desktop.json")
}

/// The sidecar's log file: `<state_dir>/logs/openworker-server.log`, fresh per
/// launch with the previous run kept as `.old`. None (→ /dev/null) only if the
/// directory can't be created — logging must never block startup.
fn server_log_file() -> Option<std::fs::File> {
    let dir = state_dir().join("logs");
    std::fs::create_dir_all(&dir).ok()?;
    let path = dir.join("openworker-server.log");
    if path.exists() {
        let _ = std::fs::rename(&path, dir.join("openworker-server.log.old"));
    }
    std::fs::File::create(&path).ok()
}

fn read_desktop_pref(key: &str, default: bool) -> bool {
    std::fs::read_to_string(desktop_prefs_path())
        .ok()
        .and_then(|s| serde_json::from_str::<serde_json::Value>(&s).ok())
        .and_then(|v| v.get(key).and_then(|b| b.as_bool()))
        .unwrap_or(default)
}

/// Merge-write of arbitrary JSON values; the bool flavor below delegates here.
/// Read-modify-write so one preference never clobbers the others (the old
/// writer serialized only its own key, silently dropping the rest).
fn write_desktop_pref_value(key: &str, value: serde_json::Value) {
    let path = desktop_prefs_path();
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    let mut prefs = std::fs::read_to_string(&path)
        .ok()
        .and_then(|s| serde_json::from_str::<serde_json::Value>(&s).ok())
        .unwrap_or_else(|| serde_json::json!({}));
    if let Some(map) = prefs.as_object_mut() {
        map.insert(key.to_string(), value);
    }
    let _ = std::fs::write(&path, prefs.to_string());
}

fn write_desktop_pref(key: &str, enabled: bool) {
    write_desktop_pref_value(key, serde_json::Value::Bool(enabled));
}

fn read_keep_awake_pref() -> bool {
    read_desktop_pref("keep_awake", false)
}

fn write_keep_awake_pref(enabled: bool) {
    write_desktop_pref("keep_awake", enabled);
}

// -- keep-awake: hold off idle + system sleep so the scheduler keeps firing -------------------
// Cross-platform behind a uniform `start_keep_awake() -> Option<KeepAwakeGuard>`; dropping the
// guard releases the hold. macOS uses the built-in `caffeinate`; Windows uses the
// SetThreadExecutionState API (a dedicated thread holds ES_CONTINUOUS so the state survives
// regardless of which Tauri worker thread toggled it); other platforms are a no-op.

#[cfg(target_os = "macos")]
struct KeepAwakeGuard(Child);

#[cfg(target_os = "macos")]
impl Drop for KeepAwakeGuard {
    fn drop(&mut self) {
        let _ = self.0.kill();
    }
}

#[cfg(target_os = "macos")]
fn start_keep_awake() -> Option<KeepAwakeGuard> {
    Command::new("caffeinate")
        .args(["-i", "-s"])
        .spawn()
        .ok()
        .map(KeepAwakeGuard)
}

#[cfg(target_os = "windows")]
extern "system" {
    fn SetThreadExecutionState(es_flags: u32) -> u32;
}

#[cfg(target_os = "windows")]
const ES_CONTINUOUS: u32 = 0x8000_0000;
#[cfg(target_os = "windows")]
const ES_SYSTEM_REQUIRED: u32 = 0x0000_0001;

#[cfg(target_os = "windows")]
struct KeepAwakeGuard {
    stop: Arc<AtomicBool>,
    handle: Option<std::thread::JoinHandle<()>>,
}

#[cfg(target_os = "windows")]
impl Drop for KeepAwakeGuard {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::SeqCst);
        if let Some(h) = self.handle.take() {
            let _ = h.join();
        }
    }
}

#[cfg(target_os = "windows")]
fn start_keep_awake() -> Option<KeepAwakeGuard> {
    let stop = Arc::new(AtomicBool::new(false));
    let stop_thread = stop.clone();
    let handle = std::thread::spawn(move || {
        // SetThreadExecutionState is thread-affine and the ES_CONTINUOUS hold is dropped when
        // the setting thread exits — so keep this thread alive, re-asserting periodically,
        // until asked to stop, then clear the hold from this same thread.
        unsafe { SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED) };
        while !stop_thread.load(Ordering::SeqCst) {
            unsafe { SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED) };
            std::thread::sleep(std::time::Duration::from_secs(30));
        }
        unsafe { SetThreadExecutionState(ES_CONTINUOUS) };
    });
    Some(KeepAwakeGuard {
        stop,
        handle: Some(handle),
    })
}

#[cfg(not(any(target_os = "macos", target_os = "windows")))]
struct KeepAwakeGuard;

#[cfg(not(any(target_os = "macos", target_os = "windows")))]
fn start_keep_awake() -> Option<KeepAwakeGuard> {
    // No portable built-in inhibitor on Linux; keep-awake is a no-op (the toggle still reflects
    // state so the UI behaves, but the OS sleep policy is left to the user).
    Some(KeepAwakeGuard)
}

// -- native commands (invoked from the SPA via window.__TAURI__.core.invoke) -----------------

/// Native macOS folder picker for the workspace gate.
#[tauri::command]
async fn pick_folder(app: tauri::AppHandle) -> Option<String> {
    use tauri_plugin_dialog::DialogExt;
    let (tx, rx) = std::sync::mpsc::channel();
    app.dialog().file().pick_folder(move |p| {
        let _ = tx.send(p);
    });
    rx.recv().ok().flatten().map(|fp| fp.to_string())
}

#[tauri::command]
fn get_autostart(app: tauri::AppHandle) -> bool {
    app.autolaunch().is_enabled().unwrap_or(false)
}

#[tauri::command]
fn set_autostart(app: tauri::AppHandle, enabled: bool) -> bool {
    let m = app.autolaunch();
    let _ = if enabled { m.enable() } else { m.disable() };
    m.is_enabled().unwrap_or(false)
}

#[tauri::command]
fn get_keep_awake(state: tauri::State<KeepAwake>) -> bool {
    state.0.lock().unwrap().is_some()
}

#[tauri::command]
fn set_keep_awake(state: tauri::State<KeepAwake>, enabled: bool) -> bool {
    let mut guard = state.0.lock().unwrap();
    if enabled {
        if guard.is_none() {
            *guard = start_keep_awake();
        }
    } else {
        // Dropping the taken guard releases the hold (kills caffeinate / clears the
        // Windows execution state).
        drop(guard.take());
    }
    let on = guard.is_some();
    write_keep_awake_pref(on);
    on
}

#[tauri::command]
fn start_window_drag(window: tauri::WebviewWindow) -> bool {
    window.start_dragging().is_ok()
}

// -- local dictation ---------------------------------------------------------------------------
// The actual microphone/model code lives in the Tauri-free `ocw-stt` crate. This shell owns the
// macOS permission prompt and translates the reusable API into React-friendly Tauri commands.

#[derive(Clone, Serialize)]
struct VoiceInputStatus {
    recording: bool,
    model_installed: bool,
    model_verified: bool,
    test_passed: bool,
    download_in_progress: bool,
    model_name: &'static str,
    model_bytes: u64,
    supported: bool,
    device_summary: String,
    compatibility_reason: Option<String>,
}

fn voice_input_status(dictation: &Dictation) -> VoiceInputStatus {
    let status = dictation.status();
    let (supported, device_summary, compatibility_reason) = voice_input_compatibility();
    VoiceInputStatus {
        recording: status.recording,
        model_installed: status.model_installed,
        model_verified: status.model_verified,
        test_passed: status.test_passed,
        download_in_progress: status.download_in_progress,
        model_name: status.model_name,
        model_bytes: status.model_bytes,
        supported,
        device_summary,
        compatibility_reason,
    }
}

#[cfg(target_os = "macos")]
fn voice_input_compatibility() -> (bool, String, Option<String>) {
    let version = Command::new("/usr/bin/sw_vers")
        .arg("-productVersion")
        .output()
        .ok()
        .filter(|output| output.status.success())
        .map(|output| String::from_utf8_lossy(&output.stdout).trim().to_owned())
        .unwrap_or_else(|| "unknown version".to_owned());
    let major = version
        .split('.')
        .next()
        .and_then(|part| part.parse::<u32>().ok())
        .unwrap_or(0);
    let apple_silicon = std::env::consts::ARCH == "aarch64";
    let supported = apple_silicon && major >= 12;
    let architecture = if apple_silicon {
        "Apple Silicon"
    } else {
        "Intel"
    };
    let summary = format!("macOS {version} · {architecture}");
    let reason = if !apple_silicon {
        Some("Voice Input currently requires an Apple Silicon Mac (M1 or newer).".to_owned())
    } else if major < 12 {
        Some("Voice Input requires macOS 12 or newer.".to_owned())
    } else {
        None
    };
    (supported, summary, reason)
}

#[cfg(target_os = "windows")]
fn voice_input_compatibility() -> (bool, String, Option<String>) {
    let version = Command::new("cmd")
        .args(["/C", "ver"])
        .output()
        .ok()
        .map(|output| String::from_utf8_lossy(&output.stdout).trim().to_owned())
        .unwrap_or_else(|| "Windows (unknown version)".to_owned());
    let build = version
        .split(|character: char| !character.is_ascii_digit() && character != '.')
        .find(|part| part.matches('.').count() >= 2)
        .and_then(|part| part.split('.').nth(2))
        .and_then(|part| part.parse::<u32>().ok())
        .unwrap_or(0);
    let x64 = std::env::consts::ARCH == "x86_64";
    let supported = x64 && build >= 19_045;
    let reason = if !x64 {
        Some("Voice Input currently requires a 64-bit x64 Windows PC.".to_owned())
    } else if build < 19_045 {
        Some("Voice Input requires Windows 10 22H2 or Windows 11.".to_owned())
    } else {
        None
    };
    (supported, format!("{version} · x64"), reason)
}

#[cfg(not(any(target_os = "macos", target_os = "windows")))]
fn voice_input_compatibility() -> (bool, String, Option<String>) {
    (
        false,
        format!("{} · {}", std::env::consts::OS, std::env::consts::ARCH),
        Some("Voice Input is currently supported on macOS and Windows.".to_owned()),
    )
}

#[tauri::command]
fn get_dictation_status(state: tauri::State<Arc<Dictation>>) -> VoiceInputStatus {
    voice_input_status(&state)
}

#[tauri::command]
async fn start_dictation(
    state: tauri::State<'_, Arc<Dictation>>,
) -> Result<VoiceInputStatus, String> {
    // Off the main thread: opening the input device blocks on macOS's one-time microphone
    // permission dialog (and CoreAudio device setup) — a sync command would freeze the UI
    // behind the system prompt.
    let (supported, _, reason) = voice_input_compatibility();
    if !supported {
        return Err(
            reason.unwrap_or_else(|| "Voice Input is not supported on this device.".to_owned())
        );
    }
    let dictation = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        dictation.start()?;
        Ok::<VoiceInputStatus, String>(voice_input_status(&dictation))
    })
    .await
    .map_err(|e| format!("Dictation failed to start: {e}"))?
}

#[tauri::command]
async fn stop_dictation(state: tauri::State<'_, Arc<Dictation>>) -> Result<String, String> {
    let dictation = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || dictation.stop_and_transcribe())
        .await
        .map_err(|e| format!("Dictation stopped unexpectedly: {e}"))?
}

#[tauri::command]
fn cancel_dictation(state: tauri::State<Arc<Dictation>>) {
    state.cancel();
}

#[tauri::command]
async fn download_dictation_model(
    app: tauri::AppHandle,
    state: tauri::State<'_, Arc<Dictation>>,
) -> Result<VoiceInputStatus, String> {
    let dictation = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        dictation.install_default_model_with_progress(|progress: DownloadProgress| {
            let _ = app.emit("dictation-download-progress", progress);
        })?;
        Ok::<VoiceInputStatus, String>(voice_input_status(&dictation))
    })
    .await
    .map_err(|e| format!("Voice model download stopped unexpectedly: {e}"))?
}

#[tauri::command]
fn cancel_dictation_model_download(state: tauri::State<Arc<Dictation>>) {
    state.cancel_model_download();
}

#[tauri::command]
async fn verify_dictation_model(
    state: tauri::State<'_, Arc<Dictation>>,
) -> Result<VoiceInputStatus, String> {
    let dictation = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        dictation.verify_default_model()?;
        Ok::<VoiceInputStatus, String>(voice_input_status(&dictation))
    })
    .await
    .map_err(|e| format!("Voice model verification stopped unexpectedly: {e}"))?
}

#[tauri::command]
fn mark_dictation_test_passed(
    state: tauri::State<Arc<Dictation>>,
) -> Result<VoiceInputStatus, String> {
    state.mark_test_passed()?;
    Ok(voice_input_status(&state))
}

#[tauri::command]
fn delete_dictation_model(state: tauri::State<Arc<Dictation>>) -> Result<VoiceInputStatus, String> {
    state.delete_default_model()?;
    Ok(voice_input_status(&state))
}

/// Instantaneous mic loudness (0..1) while a dictation is recording — the composer polls
/// this to draw a real input-driven waveform instead of decorative bars (owner catch,
/// DMG #28 walkthrough).
#[tauri::command]
fn dictation_level(state: tauri::State<Arc<Dictation>>) -> f32 {
    state.input_level()
}

fn show_main(app: &tauri::AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.unminimize();
        let _ = w.show();
        let _ = w.set_focus();
    }
    hide_companion(app);
}

// --- Floating Mimi companion -------------------------------------------------------
// A tiny always-on-top window that appears when the main window is minimized or
// closed to tray: Mimi sleeps while the coworker is busy and wakes when the work
// is done (the webview side renders the sprite states from /ws/events activity
// frames). Clicking Mimi restores the main window.

/// "Not now": the pet's own ✕ hides it until the app restarts. The persistent
/// off-switch is the Settings preference below; re-enabling there clears this.
static COMPANION_DISMISSED: std::sync::atomic::AtomicBool =
    std::sync::atomic::AtomicBool::new(false);

fn show_companion(app: &tauri::AppHandle) {
    if !read_desktop_pref("companion", true) {
        return; // turned off in Settings
    }
    if COMPANION_DISMISSED.load(std::sync::atomic::Ordering::Relaxed) {
        return; // dismissed from the pet itself, for this run
    }
    if let Some(w) = app.get_webview_window("companion") {
        position_companion(&w);
        let _ = w.show();
    }
}

#[tauri::command]
fn get_companion_enabled() -> bool {
    read_desktop_pref("companion", true)
}

#[tauri::command]
fn set_companion_enabled(app: tauri::AppHandle, enabled: bool) -> bool {
    write_desktop_pref("companion", enabled);
    if enabled {
        // An explicit re-enable also forgives a same-session dismiss.
        COMPANION_DISMISSED.store(false, std::sync::atomic::Ordering::Relaxed);
    } else {
        hide_companion(&app);
    }
    enabled
}

#[tauri::command]
fn companion_dismiss(app: tauri::AppHandle) {
    COMPANION_DISMISSED.store(true, std::sync::atomic::Ordering::Relaxed);
    hide_companion(&app);
}

fn hide_companion(app: &tauri::AppHandle) {
    if let Some(w) = app.get_webview_window("companion") {
        let _ = w.hide();
    }
}

/// Bottom-right of the monitor the main window lives on, above the Dock/taskbar.
fn position_companion(w: &tauri::WebviewWindow) {
    let ws = w.outer_size().unwrap_or(tauri::PhysicalSize::new(240, 250));
    // A position the user dragged her to previously — but only if it still lands
    // fully on a connected monitor (a saved spot on an unplugged display would
    // otherwise make the pet unfindable).
    if let Some((x, y)) = companion_saved_position(w, &ws) {
        let _ = w.set_position(tauri::PhysicalPosition::new(x, y));
        return;
    }
    let monitor = w.current_monitor().ok().flatten().or_else(|| {
        w.primary_monitor().ok().flatten()
    });
    if let Some(mon) = monitor {
        let ms = mon.size();
        let mp = mon.position();
        let sf = mon.scale_factor();
        let margin = (24.0 * sf) as i32;
        let x = mp.x + ms.width as i32 - ws.width as i32 - margin;
        let y = mp.y + ms.height as i32 - ws.height as i32 - (80.0 * sf) as i32;
        let _ = w.set_position(tauri::PhysicalPosition::new(x, y));
    }
}

/// The last user-dragged companion position (physical px), if it fits entirely
/// within one of the currently connected monitors.
fn companion_saved_position(
    w: &tauri::WebviewWindow,
    ws: &tauri::PhysicalSize<u32>,
) -> Option<(i32, i32)> {
    let prefs = std::fs::read_to_string(desktop_prefs_path())
        .ok()
        .and_then(|s| serde_json::from_str::<serde_json::Value>(&s).ok())?;
    let x = prefs.get("companion_pos_x")?.as_i64()? as i32;
    let y = prefs.get("companion_pos_y")?.as_i64()? as i32;
    let monitors = w.available_monitors().ok()?;
    monitors.into_iter().find(|mon| {
        let mp = mon.position();
        let ms = mon.size();
        x >= mp.x
            && y >= mp.y
            && x + ws.width as i32 <= mp.x + ms.width as i32
            && y + ws.height as i32 <= mp.y + ms.height as i32
    })?;
    Some((x, y))
}

// Drag persistence: WindowEvent::Moved fires continuously while the OS drags the
// window (~60Hz), so saves are debounced — the event handler only parks the latest
// coordinates and arms one writer thread; the thread drains whatever is parked
// after 500ms of quiet and exits when there's nothing left.
static COMPANION_POS_PENDING: std::sync::Mutex<Option<(i32, i32)>> =
    std::sync::Mutex::new(None);
static COMPANION_POS_SAVE_ARMED: std::sync::atomic::AtomicBool =
    std::sync::atomic::AtomicBool::new(false);

fn queue_companion_pos_save(x: i32, y: i32) {
    if let Ok(mut pending) = COMPANION_POS_PENDING.lock() {
        *pending = Some((x, y));
    }
    // The losing arm call does nothing: whichever thread is armed drains any
    // newer value parked after it, so no save is lost either way.
    if COMPANION_POS_SAVE_ARMED.swap(true, std::sync::atomic::Ordering::AcqRel) {
        return;
    }
    std::thread::spawn(|| loop {
        std::thread::sleep(std::time::Duration::from_millis(500));
        let parked = COMPANION_POS_PENDING
            .lock()
            .ok()
            .and_then(|mut p| p.take());
        match parked {
            Some((x, y)) => {
                write_desktop_pref_value("companion_pos_x", serde_json::json!(x));
                write_desktop_pref_value("companion_pos_y", serde_json::json!(y));
            }
            None => {
                COMPANION_POS_SAVE_ARMED.store(false, std::sync::atomic::Ordering::Release);
                break;
            }
        }
    });
}

/// Companion click-through to the app: restore the main window, hide the pet.
#[tauri::command]
fn companion_restore(app: tauri::AppHandle) {
    show_main(&app);
}

// --- Auto-update (tauri-plugin-updater) -------------------------------------------
// The GUI drives updates through these commands (same invoke bridge as everything
// else — no global plugin JS): check, background pre-download, install. Update
// artifacts are minisign-verified against the pubkey in tauri.conf.json before
// anything is installed; the manifest lives at the endpoints configured there
// (download.openworker.com → GitHub Releases).

#[derive(serde::Serialize)]
struct UpdateInfo {
    version: String,
    notes: String,
}

#[tauri::command]
async fn check_for_update(app: tauri::AppHandle) -> Result<Option<UpdateInfo>, String> {
    use tauri_plugin_updater::UpdaterExt;
    let updater = app.updater().map_err(|e| e.to_string())?;
    let update = updater.check().await.map_err(|e| e.to_string())?;
    Ok(update.map(|u| UpdateInfo {
        version: u.version.clone(),
        notes: u.body.clone().unwrap_or_default(),
    }))
}

/// Update bytes pre-fetched by `download_update`, keyed by version. The GUI kicks the
/// download off as soon as a release is offered, so clicking "Restart to update" installs
/// from memory instead of sitting on a multi-minute download behind a spinner.
struct PendingUpdate(Mutex<Option<(String, Vec<u8>)>>);

#[tauri::command]
async fn download_update(
    app: tauri::AppHandle,
    pending: tauri::State<'_, PendingUpdate>,
) -> Result<(), String> {
    use tauri_plugin_updater::UpdaterExt;
    let updater = app.updater().map_err(|e| e.to_string())?;
    let Some(update) = updater.check().await.map_err(|e| e.to_string())? else {
        return Err("no update available".into());
    };
    // Periodic re-checks re-invoke this for the same release — the cached bytes stand.
    // (Guard scope stays sync: a std MutexGuard must not live across an await.)
    {
        let slot = pending.0.lock().unwrap();
        if slot.as_ref().map(|(v, _)| v == &update.version).unwrap_or(false) {
            return Ok(());
        }
    }
    let bytes = update
        .download(|_, _| {}, || {})
        .await
        .map_err(|e| e.to_string())?;
    *pending.0.lock().unwrap() = Some((update.version.clone(), bytes));
    Ok(())
}

/// Drop the pre-fetched bundle. Invoked on "Later": a dismissed release would
/// otherwise pin tens of MB in memory for the rest of an app run that can last
/// weeks. Changing one's mind just re-downloads.
#[tauri::command]
fn clear_pending_update(pending: tauri::State<'_, PendingUpdate>) {
    *pending.0.lock().unwrap() = None;
}

#[tauri::command]
async fn install_update(
    app: tauri::AppHandle,
    pending: tauri::State<'_, PendingUpdate>,
) -> Result<(), String> {
    use tauri_plugin_updater::UpdaterExt;
    let updater = app.updater().map_err(|e| e.to_string())?;
    let Some(update) = updater.check().await.map_err(|e| e.to_string())? else {
        return Err("no update available".into());
    };
    // Pre-fetched bytes for this exact version install instantly; a stale or missing
    // cache falls back to the original blocking download-and-install.
    let cached = {
        let mut slot = pending.0.lock().unwrap();
        match slot.take() {
            Some((v, bytes)) if v == update.version => Some(bytes),
            _ => None,
        }
    };
    match cached {
        Some(bytes) => update.install(bytes).map_err(|e| e.to_string())?,
        None => update
            .download_and_install(|_, _| {}, || {})
            .await
            .map_err(|e| e.to_string())?,
    }
    // Windows never reaches here (the NSIS installer takes over and relaunches).
    // macOS: the .app was swapped in place — restart into the new version. The tray
    // Exit path's sidecar kill runs via RunEvent, so no orphaned openworker-server.
    app.restart();
}

pub fn run() {
    let port = free_port();
    let api_token = launch_token();
    let http = format!("http://127.0.0.1:{port}");
    let ws = format!("ws://127.0.0.1:{port}");
    // Debug-format yields a quoted JS string literal.
    let inject = format!(
        "window.__COWORKER_HTTP__={http:?};window.__COWORKER_WS__={ws:?};window.__COWORKER_API_TOKEN__={api_token:?};window.__OCW_PLATFORM__={:?};",
        std::env::consts::OS
    );

    tauri::Builder::default()
        // MUST be the first plugin: when a second launch happens (e.g. the user relaunches
        // while the window is closed-to-tray), this fires in the ALREADY-running instance to
        // surface its healthy window, and the second process exits before it can spawn a
        // duplicate sidecar — which previously left a window stuck on "Starting coworker…".
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            show_main(app);
        }))
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            None,
        ))
        .invoke_handler(tauri::generate_handler![
            pick_folder,
            get_autostart,
            set_autostart,
            get_keep_awake,
            set_keep_awake,
            start_window_drag,
            get_dictation_status,
            start_dictation,
            stop_dictation,
            cancel_dictation,
            download_dictation_model,
            cancel_dictation_model_download,
            verify_dictation_model,
            mark_dictation_test_passed,
            delete_dictation_model,
            dictation_level,
            check_for_update,
            download_update,
            clear_pending_update,
            install_update,
            companion_restore,
            companion_dismiss,
            get_companion_enabled,
            set_companion_enabled
        ])
        .setup(move |app| {
            // 1. Start the Python server sidecar on the chosen port (inherits our env).
            let mut server_cmd = Command::new(server_bin());
            server_cmd
                .args(["--host", "127.0.0.1", "--port", &port.to_string()])
                // The sidecar self-exits if we die abruptly (dev-watcher restart, crash) —
                // belt-and-suspenders alongside the RunEvent::ExitRequested kill below.
                // The explicit PID matters: under PyInstaller onefile the python process is a
                // *grandchild* (bootloader in between), so getppid() never points at us and a
                // reparenting check alone leaks both processes on quit.
                .env("COWORKER_EXIT_WITH_PARENT", "1")
                .env("COWORKER_PARENT_PID", std::process::id().to_string())
                .env("COWORKER_API_TOKEN", &api_token)
                // This GUI app has no console, so a console-subsystem child would inherit
                // invalid std handles and crash a few seconds in when uvicorn writes its logs
                // (the "Starting coworker…" freeze on Windows). Hand it real handles: the
                // server's output goes to a log file so field issues are debuggable at all
                // ("relay off, no messages" was undiagnosable with everything on /dev/null).
                // One file per launch, previous run kept as .old.
                .stdin(Stdio::null());
            match server_log_file() {
                Some(log) => {
                    if let Ok(err_clone) = log.try_clone() {
                        server_cmd
                            .stdout(Stdio::from(log))
                            .stderr(Stdio::from(err_clone));
                    } else {
                        server_cmd.stdout(Stdio::from(log)).stderr(Stdio::null());
                    }
                }
                None => {
                    server_cmd.stdout(Stdio::null()).stderr(Stdio::null());
                }
            }
            // CREATE_NO_WINDOW: the sidecar is a console binary; without this a console window
            // would flash when the GUI app spawns it on Windows.
            #[cfg(windows)]
            {
                use std::os::windows::process::CommandExt;
                server_cmd.creation_flags(0x0800_0000);
            }
            let child = match server_cmd.spawn() {
                Ok(child) => Some(child),
                Err(e) => {
                    eprintln!("[coworker] failed to start server sidecar: {e}");
                    None
                }
            };
            app.manage(ServerProcess(Mutex::new(child)));

            // Restore keep-awake from the last session.
            let ka = if read_keep_awake_pref() {
                start_keep_awake()
            } else {
                None
            };
            app.manage(KeepAwake(Mutex::new(ka)));
            app.manage(PendingUpdate(Mutex::new(None)));
            // Voice recordings are transient; only the explicitly installed local Whisper model
            // lives in the existing application state directory.
            app.manage(Arc::new(Dictation::new(state_dir().join("models"))));

            // 2. Build the window, injecting the sidecar endpoints before the SPA loads.
            //    Overlay title bar (macOS): traffic lights float over the edge-to-edge UI.
            let mut builder =
                WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
                    .title("MimiWork")
                    .inner_size(1360.0, 900.0)
                    .min_inner_size(980.0, 640.0)
                    // Let the WEBVIEW receive OS file drags: Tauri's own drag-drop handler
                    // otherwise intercepts them, so the composer's HTML5 onDrop (attach by
                    // dragging a file in) never fired in the desktop shell — browser dev
                    // worked, DMGs didn't. main.tsx guards against drops outside the
                    // composer navigating the page.
                    .disable_drag_drop_handler()
                    .initialization_script(&inject);
            #[cfg(target_os = "macos")]
            {
                builder = builder
                    .title_bar_style(tauri::TitleBarStyle::Overlay)
                    .hidden_title(true)
                    // Nudge the traffic lights down + in so they sit vertically centered in a
                    // roomier top strip, aligned with the sidebar toggle and title rather than
                    // jammed against the top edge.
                    .traffic_light_position(tauri::LogicalPosition::new(19.0, 24.0));
            }
            let win = builder.build()?;

            // The floating Mimi companion: built hidden up-front (same endpoint injection,
            // plus a flag main.tsx branches on), shown whenever the main window leaves the
            // screen. Transparent + frameless so only the dog is visible.
            #[allow(unused_mut)]
            let mut companion_builder = WebviewWindowBuilder::new(
                app,
                "companion",
                WebviewUrl::App("index.html".into()),
            )
            .title("Mimi")
            .inner_size(240.0, 250.0)
            .resizable(false)
            .decorations(false)
            .transparent(true)
            .always_on_top(true)
            .skip_taskbar(true)
            .shadow(false)
            .visible(false)
            // Never steal focus when appearing — the user just minimized on purpose.
            .focused(false)
            .initialization_script(&format!("{inject}window.__MIMI_COMPANION__=true;"));
            match companion_builder.build() {
                Ok(companion) => {
                    position_companion(&companion);
                    // Persist wherever the user drags her (debounced in
                    // queue_companion_pos_save); position_companion restores it.
                    companion.on_window_event(|event| {
                        if let WindowEvent::Moved(pos) = event {
                            queue_companion_pos_save(pos.x, pos.y);
                        }
                    });
                }
                Err(e) => eprintln!("[coworker] companion window failed to build: {e}"),
            }

            // Close-to-tray: hide instead of quitting so the sidecar keeps running —
            // and let the companion take over the screen corner. Minimize does the
            // same handoff; focusing the main window sends the pet away.
            let w = win.clone();
            let app_handle = app.handle().clone();
            win.on_window_event(move |event| match event {
                WindowEvent::CloseRequested { api, .. } => {
                    let _ = w.hide();
                    api.prevent_close();
                    show_companion(&app_handle);
                }
                // Windows signals minimize through a resize; macOS's miniaturize does
                // NOT resize the NSWindow, so this arm alone never fired there
                // (owner report 2026-08-20) — the Focused(false) arm below covers it.
                WindowEvent::Resized(_) => {
                    if w.is_minimized().unwrap_or(false) {
                        show_companion(&app_handle);
                    }
                }
                WindowEvent::Focused(true) => {
                    hide_companion(&app_handle);
                }
                WindowEvent::Focused(false) => {
                    // Focus loss also happens when the user just switches apps — check
                    // shortly after whether the window actually left the screen
                    // (minimized, or hidden via Cmd+H). Window getters are thread-safe
                    // (they dispatch to the main thread), so a helper thread is fine.
                    let w2 = w.clone();
                    let handle = app_handle.clone();
                    std::thread::spawn(move || {
                        std::thread::sleep(std::time::Duration::from_millis(400));
                        let gone = w2.is_minimized().unwrap_or(false)
                            || !w2.is_visible().unwrap_or(true);
                        if gone {
                            show_companion(&handle);
                        }
                    });
                }
                _ => {}
            });

            // 3. System tray: Open / Settings / Quit.
            let open_i = MenuItem::with_id(app, "open", "Open MimiWork", true, None::<&str>)?;
            let settings_i = MenuItem::with_id(app, "settings", "Settings", true, None::<&str>)?;
            let quit_i = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open_i, &settings_i, &quit_i])?;

            // A monochrome template icon (black + alpha, raw RGBA 44×44) so the menu bar tints
            // it for light/dark automatically — not the full-color app icon.
            let tray_icon = tauri::image::Image::new(include_bytes!("../icons/tray.rgba"), 44, 44);
            TrayIconBuilder::new()
                .tooltip("MimiWork")
                .icon(tray_icon)
                .icon_as_template(true)
                .menu(&menu)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "open" => show_main(app),
                    "settings" => {
                        show_main(app);
                        if let Some(w) = app.get_webview_window("main") {
                            let _ = w.eval(
                                "window.dispatchEvent(new CustomEvent('coworker:open-settings'))",
                            );
                        }
                    }
                    "quit" => app.exit(0),
                    _ => {}
                })
                .build(app)?;

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building the MimiWork desktop app")
        .run(|app, event| {
            // macOS Dock click = "reopen". AppKit's default only deminiaturizes a
            // window when the app has NO other windows — and the companion (hidden
            // or visible) always counts as one, so a minimized/tray-hidden main
            // window never came back on Dock click (owner report 2026-08-20).
            // Handle reopen explicitly: bring the app back, send the pet away.
            #[cfg(target_os = "macos")]
            if matches!(event, RunEvent::Reopen { .. }) {
                show_main(app);
            }
            // Also on Exit: belt-and-suspenders in case a quit path reaches teardown without
            // a preceding ExitRequested (observed with macOS Cmd+Q under the tray setup).
            if matches!(event, RunEvent::ExitRequested { .. } | RunEvent::Exit) {
                if let Some(state) = app.try_state::<ServerProcess>() {
                    if let Some(mut child) = state.0.lock().unwrap().take() {
                        let _ = child.kill();
                    }
                }
                if let Some(state) = app.try_state::<KeepAwake>() {
                    // Dropping the guard releases the hold (caffeinate kill / execution-state clear).
                    drop(state.0.lock().unwrap().take());
                }
            }
        });
}
