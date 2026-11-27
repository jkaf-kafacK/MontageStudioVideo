// Pas de fenêtre de console en version finale (l'application n'a que sa fenêtre)
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
//! MSV Éditeur : l'éditeur de Montage Studio Video dans sa propre fenêtre, sans navigateur.
//!
//! Au lancement, l'application démarre MSV (son lanceur habituel, sans fenêtre noire ni navigateur), lit l'adresse
//! qu'il annonce, attend qu'il réponde, puis affiche son éditeur (/editeur) dans la fenêtre. À la fermeture, MSV
//! est arrêté avec tout ce qu'il a lancé. Si MSV Pro tourne déjà (port 7870), la fenêtre s'en sert directement.
//!
//! Lanceur cherché à partir du dossier du programme, puis dans les dossiers parents :
//!   lancer_msv.bat          version installée (l'édition dépend du fichier app\EDITION)
//!   lancer_windows_pro.bat  dossier du projet, édition pro (choix par défaut)
//!   lancer_windows.bat      dossier du projet, édition libre (option --libre)
//! MSV_APP_DIR peut désigner le dossier à utiliser. Journal : %LOCALAPPDATA%\MontageStudioVideo\editeur-bureau.log

use std::fs::{self, File};
use std::io::{BufRead, BufReader, Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{mpsc, Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use tauri::{AppHandle, Manager, RunEvent, WebviewWindow};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

const CREATE_NO_WINDOW: u32 = 0x0800_0000;
const PRO_PORT: u16 = 7870;
const START_TIMEOUT: Duration = Duration::from_secs(15 * 60); // 1re configuration : téléchargements
const KEEP_LINES: usize = 40;

/// MSV lancé par l'application (arrêté à la fermeture) ; None si on utilise un MSV déjà ouvert.
#[derive(Default)]
struct Server {
    child: Mutex<Option<Child>>,
}

type Lines = Arc<Mutex<Vec<String>>>;

fn status(win: &WebviewWindow, text: &str, error: bool, log: &str) {
    let js = format!(
        "window.setStatus && window.setStatus({}, {}, {})",
        serde_json::to_string(text).unwrap_or_default(),
        error,
        serde_json::to_string(log).unwrap_or_default()
    );
    let _ = win.eval(&js);
}

/// Réponse d'une adresse locale de MSV si elle répond « 200 », sinon None.
fn http_get(port: u16, path: &str) -> Option<String> {
    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    let mut s = TcpStream::connect_timeout(&addr, Duration::from_millis(400)).ok()?;
    s.set_read_timeout(Some(Duration::from_secs(3))).ok()?;
    write!(s, "GET {path} HTTP/1.0\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n").ok()?;
    let mut out = Vec::new();
    s.take(256 * 1024).read_to_end(&mut out).ok()?;
    let text = String::from_utf8_lossy(&out).into_owned();
    let first = text.lines().next().unwrap_or("");
    first.contains(" 200 ").then_some(text)
}

fn find_launcher(libre: bool) -> Option<PathBuf> {
    let mut dirs: Vec<PathBuf> = Vec::new();
    if let Some(d) = std::env::var_os("MSV_APP_DIR") {
        dirs.push(PathBuf::from(d));
    }
    if let Ok(exe) = std::env::current_exe() {
        dirs.extend(exe.ancestors().skip(1).map(Path::to_path_buf));
    }
    for dir in dirs {
        let mut candidates = vec![dir.join("lancer_msv.bat")];
        for base in [dir.clone(), dir.join("montage_studio")] {
            if !libre {
                candidates.push(base.join("lancer_windows_pro.bat"));
            }
            candidates.push(base.join("lancer_windows.bat"));
        }
        if let Some(p) = candidates.into_iter().find(|p| p.is_file()) {
            return Some(p);
        }
    }
    None
}

fn log_path() -> PathBuf {
    let base = std::env::var_os("LOCALAPPDATA").map(PathBuf::from).unwrap_or_else(std::env::temp_dir);
    let dir = base.join("MontageStudioVideo");
    let _ = fs::create_dir_all(&dir);
    dir.join("editeur-bureau.log")
}

/// Port de l'adresse « http://127.0.0.1:PORT/ » annoncée par MSV dans une ligne de sa sortie.
fn find_port(line: &str) -> Option<u16> {
    const START: &str = "http://127.0.0.1:";
    let i = line.find(START)? + START.len();
    let digits: String = line[i..].chars().take_while(char::is_ascii_digit).collect();
    digits.parse().ok()
}

/// Lit une sortie de MSV ligne par ligne : journal, dernières lignes, et port annoncé.
fn pump<R: Read>(r: R, lines: Lines, log: Arc<Mutex<Option<File>>>, tx: Option<mpsc::Sender<u16>>) {
    let mut reader = BufReader::new(r);
    let mut buf = Vec::new();
    loop {
        buf.clear();
        match reader.read_until(b'\n', &mut buf) {
            Ok(0) | Err(_) => break,
            Ok(_) => {}
        }
        let line = String::from_utf8_lossy(&buf).trim_end().to_string();
        if let Some(f) = log.lock().unwrap().as_mut() {
            let _ = writeln!(f, "{line}");
        }
        if let (Some(tx), Some(p)) = (&tx, find_port(&line)) {
            let _ = tx.send(p);
        }
        let mut l = lines.lock().unwrap();
        l.push(line);
        if l.len() > KEEP_LINES {
            l.remove(0);
        }
    }
}

fn open_editor(win: &WebviewWindow, port: u16) {
    if let Ok(url) = tauri::Url::parse(&format!("http://127.0.0.1:{port}/editeur?bureau=1")) {
        let _ = win.navigate(url);
    }
}

fn tail(lines: &Lines) -> String {
    lines.lock().unwrap().iter().filter(|l| !l.trim().is_empty()).cloned().collect::<Vec<_>>().join("\n")
}

fn start(app: AppHandle, win: WebviewWindow, libre: bool) {
    thread::sleep(Duration::from_millis(500)); // laisse l'écran de démarrage s'afficher
    let pro_open = http_get(PRO_PORT, "/api/editeur/config").is_some_and(|b| b.contains("\"edition\":\"pro\""));
    if !libre && pro_open {
        return open_editor(&win, PRO_PORT); // MSV Pro est déjà ouvert : on s'en sert
    }
    let Some(launcher) = find_launcher(libre) else {
        let msg = "MSV est introuvable : place MSV-Editeur.exe dans le dossier de Montage Studio Video \
                   (à côté de lancer_msv.bat), ou indique ce dossier dans la variable MSV_APP_DIR.";
        return status(&win, msg, true, "");
    };
    let log_file = log_path();
    let log = Arc::new(Mutex::new(File::create(&log_file).ok()));
    let mut cmd = Command::new("cmd");
    #[cfg(windows)]
    cmd.raw_arg(format!("/d /c \"{}\"", launcher.display())).creation_flags(CREATE_NO_WINDOW);
    cmd.current_dir(launcher.parent().unwrap_or(Path::new(".")))
        .env("MSV_NO_BROWSER", "1")
        .env("PYTHONUNBUFFERED", "1")
        .env("PYTHONIOENCODING", "utf-8")
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    let mut child = match cmd.spawn() {
        Ok(c) => c,
        Err(e) => return status(&win, &format!("Impossible de lancer MSV : {e}"), true, ""),
    };
    let lines: Lines = Arc::new(Mutex::new(Vec::new()));
    let (tx, rx) = mpsc::channel::<u16>();
    let (out, err) = (child.stdout.take(), child.stderr.take());
    app.state::<Server>().child.lock().unwrap().replace(child);
    if let Some(o) = out {
        let (l, g) = (lines.clone(), log.clone());
        thread::spawn(move || pump(o, l, g, Some(tx)));
    }
    if let Some(e) = err {
        let (l, g) = (lines.clone(), log.clone());
        thread::spawn(move || pump(e, l, g, None));
    }

    let t0 = Instant::now();
    let mut port: Option<u16> = None;
    let mut setup_shown = false;
    loop {
        thread::sleep(Duration::from_millis(300));
        while let Ok(p) = rx.try_recv() {
            port = Some(p);
        }
        if let Some(p) = port {
            if http_get(p, "/msv-ping").is_some() {
                return open_editor(&win, p);
            }
        }
        if !setup_shown && lines.lock().unwrap().iter().any(|l| l.to_lowercase().contains("premi")) {
            setup_shown = true; // « Premiere configuration » / « Premiere installation »
            status(&win, "Première configuration de MSV : quelques minutes, une seule fois. Laisse cette fenêtre ouverte.", false, "");
        }
        let exited = app
            .state::<Server>()
            .child
            .lock()
            .unwrap()
            .as_mut()
            .is_none_or(|c| matches!(c.try_wait(), Ok(Some(_))));
        if exited {
            thread::sleep(Duration::from_millis(800)); // derniers messages et dernier essai
            while let Ok(p) = rx.try_recv() {
                port = Some(p);
            }
            if let Some(p) = port.filter(|p| http_get(*p, "/msv-ping").is_some()) {
                return open_editor(&win, p); // MSV était déjà ouvert : sa copie existante sert
            }
            let msg = format!("MSV s'est arrêté avant d'être prêt. Journal complet : {}", log_file.display());
            return status(&win, &msg, true, &tail(&lines));
        }
        if t0.elapsed() > START_TIMEOUT {
            let msg = format!("MSV ne répond pas. Journal complet : {}", log_file.display());
            return status(&win, &msg, true, &tail(&lines));
        }
    }
}

/// Arrête MSV et tout ce qu'il a lancé (rendus FFmpeg, barre flottante…), seulement s'il a été lancé ici.
fn stop(app: &AppHandle) {
    let Some(mut child) = app.state::<Server>().child.lock().unwrap().take() else { return };
    if matches!(child.try_wait(), Ok(None)) {
        let mut kill = Command::new("taskkill");
        kill.args(["/PID", &child.id().to_string(), "/T", "/F"]);
        #[cfg(windows)]
        kill.creation_flags(CREATE_NO_WINDOW);
        let _ = kill.status();
    }
    let _ = child.wait();
}

fn main() {
    let libre = std::env::args().any(|a| a == "--libre");
    tauri::Builder::default()
        .manage(Server::default())
        .setup(move |app| {
            let win = app.get_webview_window("main").expect("fenêtre principale absente");
            let handle = app.handle().clone();
            thread::spawn(move || start(handle, win, libre));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("impossible de démarrer MSV Éditeur")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                stop(app);
            }
        });
}
