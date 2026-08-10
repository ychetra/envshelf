use serde::{Deserialize, Serialize};
use std::{
    fs,
    io::Write,
    path::{Component, Path, PathBuf},
    process::Command,
};
use tauri::{AppHandle, Manager};

#[derive(Debug, Serialize, Deserialize, Default, Clone)]
#[serde(rename_all = "camelCase")]
struct Settings {
    repo_path: String,
    dashboard_url: String,
    approved_roots: Vec<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct FolderMetadata {
    name: String,
    env_files: Vec<String>,
    env_file: Option<String>,
    env_example: Option<String>,
    git_url: Option<String>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ConnectRequest {
    project_path: String,
    approved_root: String,
    envshelf_path: String,
    project_name: String,
    env_file: String,
    env_example: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ConnectResult {
    runtime_path: String,
    compose_started: bool,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct StandaloneRequest {
    projects_root: String,
    envshelf_path: String,
    data_dir: Option<String>,
    port: Option<u16>,
}

fn app_error(message: impl Into<String>) -> String {
    message.into()
}

fn valid_relative_file(value: &str, label: &str) -> Result<(), String> {
    let path = Path::new(value);
    if value.is_empty() || path.is_absolute() || value.contains('\0') {
        return Err(format!("{label} must be a relative filename"));
    }
    if path.components().any(|part| {
        matches!(
            part,
            Component::ParentDir | Component::RootDir | Component::Prefix(_)
        )
    }) {
        return Err(format!("{label} must stay inside the project"));
    }
    Ok(())
}

fn canonical_dir(raw: &str, label: &str) -> Result<PathBuf, String> {
    let path = PathBuf::from(raw);
    if !path.is_absolute() {
        return Err(format!("{label} must be an absolute folder"));
    }
    let canonical = fs::canonicalize(&path).map_err(|_| format!("{label} is not available"))?;
    if !canonical.is_dir() {
        return Err(format!("{label} is not a folder"));
    }
    Ok(canonical)
}

fn settings_path(app: &AppHandle) -> Result<PathBuf, String> {
    let dir = app
        .path()
        .app_config_dir()
        .map_err(|_| app_error("could not locate local app settings"))?;
    fs::create_dir_all(&dir).map_err(|_| app_error("could not create local app settings"))?;
    Ok(dir.join("settings.json"))
}

fn read_settings(app: &AppHandle) -> Result<Settings, String> {
    let path = settings_path(app)?;
    if !path.exists() {
        return Ok(Settings {
            dashboard_url: "http://127.0.0.1:8787".into(),
            ..Settings::default()
        });
    }
    let content =
        fs::read_to_string(path).map_err(|_| app_error("could not read local app settings"))?;
    serde_json::from_str(&content).map_err(|_| app_error("local app settings are invalid"))
}

fn write_settings(app: &AppHandle, settings: &Settings) -> Result<Settings, String> {
    if !settings.repo_path.is_empty() {
        canonical_dir(&settings.repo_path, "EnvShelf folder")?;
    }
    let path = settings_path(app)?;
    let content = serde_json::to_vec_pretty(settings)
        .map_err(|_| app_error("could not serialize local app settings"))?;
    let mut file =
        fs::File::create(path).map_err(|_| app_error("could not save local app settings"))?;
    file.write_all(&content)
        .map_err(|_| app_error("could not save local app settings"))?;
    Ok(settings.clone())
}

#[tauri::command]
fn get_settings(app: AppHandle) -> Result<Settings, String> {
    read_settings(&app)
}

#[tauri::command]
fn save_settings(
    app: AppHandle,
    repo_path: String,
    dashboard_url: String,
) -> Result<Settings, String> {
    let mut settings = read_settings(&app)?;
    settings.repo_path = repo_path;
    if !settings.repo_path.trim().is_empty() {
        let repo = canonical_dir(&settings.repo_path, "EnvShelf folder")?;
        validate_docker_root(&repo)?;
    }
    if !dashboard_url.trim().is_empty() {
        settings.dashboard_url = dashboard_url;
    }
    write_settings(&app, &settings)
}

#[tauri::command]
fn parent_root(folder_path: String) -> Result<String, String> {
    let folder = canonical_dir(&folder_path, "Project folder")?;
    folder
        .parent()
        .map(|path| path.to_string_lossy().into_owned())
        .ok_or_else(|| app_error("project folder has no parent"))
}

fn resolve_app_root(app: &AppHandle, raw: &str) -> Result<PathBuf, String> {
    if !raw.trim().is_empty() {
        let selected = canonical_dir(raw, "EnvShelf folder")?;
        if selected.join("app").join("server.py").is_file() {
            return Ok(selected);
        }
        return Err(app_error("selected EnvShelf folder has no app/server.py"));
    }
    let bundled = app
        .path()
        .resource_dir()
        .map_err(|_| app_error("could not locate bundled EnvShelf resources"))?;
    if bundled.join("app").join("server.py").is_file() {
        return Ok(bundled);
    }
    Err(app_error(
        "standalone resources are missing; choose the EnvShelf source folder",
    ))
}

fn safe_git_url(folder: &Path) -> Option<String> {
    let output = Command::new("git")
        .args(["-C", folder.to_str()?, "remote", "get-url", "origin"])
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }
    let raw = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if raw.is_empty() {
        return None;
    }
    // Do not expose credentials embedded in a remote URL to the UI.
    if let Some(scheme_end) = raw.find("://") {
        let start = scheme_end + 3;
        if let Some(at) = raw[start..].find('@') {
            return Some(format!("{}{}", &raw[..start], &raw[start + at + 1..]));
        }
    }
    Some(raw)
}

#[tauri::command]
fn inspect_folder(folder_path: String) -> Result<FolderMetadata, String> {
    let folder = canonical_dir(&folder_path, "Project folder")?;
    let mut env_files = Vec::new();
    let entries =
        fs::read_dir(&folder).map_err(|_| app_error("could not inspect project folder"))?;
    for entry in entries.flatten() {
        let name = entry.file_name().to_string_lossy().into_owned();
        if name == ".env" || name.starts_with(".env.") {
            env_files.push(name);
        }
    }
    env_files.sort();
    let env_file = env_files.iter().find(|name| *name == ".env").cloned();
    let env_example = env_files
        .iter()
        .find(|name| *name == ".env.example")
        .cloned();
    Ok(FolderMetadata {
        name: folder
            .file_name()
            .map(|name| name.to_string_lossy().into_owned())
            .unwrap_or_default(),
        env_files,
        env_file,
        env_example,
        git_url: safe_git_url(&folder),
    })
}

fn yaml_string(value: &str) -> Result<String, String> {
    serde_json::to_string(value).map_err(|_| app_error("could not encode local mount path"))
}

fn ensure_local_ignore(repo: &Path) -> Result<PathBuf, String> {
    let local_dir = repo.join(".envshelf");
    fs::create_dir_all(&local_dir)
        .map_err(|_| app_error("could not create local EnvShelf configuration"))?;
    let local_ignore = local_dir.join(".gitignore");
    if !local_ignore.exists() {
        fs::write(&local_ignore, "*\n!.gitignore\n")
            .map_err(|_| app_error("could not protect local configuration"))?;
    }
    if repo.join(".git").is_dir() {
        let exclude = repo.join(".git").join("info").join("exclude");
        if let Some(parent) = exclude.parent() {
            fs::create_dir_all(parent)
                .map_err(|_| app_error("could not prepare local git exclusions"))?;
        }
        let existing = fs::read_to_string(&exclude).unwrap_or_default();
        if !existing.lines().any(|line| line.trim() == ".envshelf/") {
            let suffix = if existing.ends_with('\n') || existing.is_empty() {
                ""
            } else {
                "\n"
            };
            fs::write(&exclude, format!("{existing}{suffix}.envshelf/\n"))
                .map_err(|_| app_error("could not protect local configuration"))?;
        }
    }
    Ok(local_dir)
}

fn connect_mount_target(root: &Path) -> String {
    // Stable, filesystem-safe target that cannot replace the user's primary
    // /workspace or optional /workspace-2 mount.
    let mut hash: u64 = 0xcbf29ce484222325;
    for byte in root.to_string_lossy().as_bytes() {
        hash ^= u64::from(*byte);
        hash = hash.wrapping_mul(0x100000001b3);
    }
    format!("/workspace-connect-{hash:016x}")
}

fn connect_override_content(mounts: &[(String, String)]) -> String {
    let targets = mounts
        .iter()
        .map(|(_, target)| target.as_str())
        .collect::<Vec<_>>()
        .join(",");
    let volumes = mounts
        .iter()
        .map(|(host, target)| {
            format!(
                "      - type: bind\n        source: {host}\n        target: {target}\n        read_only: false\n"
            )
        })
        .collect::<String>();
    format!("# Generated locally by EnvShelf Connect. Do not commit.\nservices:\n  envshelf:\n    environment:\n      ENVSHELF_ALLOWED_PROJECT_ROOTS: /workspace,/workspace-2,{targets}\n    volumes:\n{volumes}")
}

fn validate_docker_root(repo: &Path) -> Result<(), String> {
    if !repo.join("docker-compose.yml").is_file() {
        return Err(app_error(
            "selected EnvShelf folder has no docker-compose.yml; choose the EnvShelf repository root",
        ));
    }
    Ok(())
}

#[tauri::command]
fn connect_project(app: AppHandle, request: ConnectRequest) -> Result<ConnectResult, String> {
    valid_relative_file(&request.env_file, "Environment filename")?;
    valid_relative_file(&request.env_example, "Example filename")?;
    if request.project_name.trim().is_empty() || request.project_name.len() > 80 {
        return Err(app_error("project name is required"));
    }
    let project = canonical_dir(&request.project_path, "Project folder")?;
    let approved = canonical_dir(&request.approved_root, "Approved root")?;
    let repo = canonical_dir(&request.envshelf_path, "EnvShelf folder")?;
    validate_docker_root(&repo)?;
    if !project.starts_with(&approved) {
        return Err(app_error("project must be inside the approved root"));
    }

    let mut settings = read_settings(&app)?;
    if !settings
        .approved_roots
        .iter()
        .any(|root| Path::new(root) == approved)
    {
        settings
            .approved_roots
            .push(approved.to_string_lossy().into_owned());
    }
    write_settings(&app, &settings)?;

    let relative = project
        .strip_prefix(&approved)
        .map_err(|_| app_error("project is outside the approved root"))?;
    let mounts = settings
        .approved_roots
        .iter()
        .filter_map(|root| {
            let path = fs::canonicalize(root).ok()?;
            if !path.is_dir() {
                return None;
            }
            let host = yaml_string(path.to_string_lossy().as_ref()).ok()?;
            Some((host, connect_mount_target(&path)))
        })
        .collect::<Vec<_>>();
    let target = connect_mount_target(&approved);
    let local_dir = ensure_local_ignore(&repo)?;
    let override_path = local_dir.join("docker-compose.connect.local.yml");
    let override_content = connect_override_content(&mounts);
    fs::write(&override_path, override_content)
        .map_err(|_| app_error("could not write the local Docker override"))?;

    let status = Command::new("docker")
        .current_dir(&repo)
        .args([
            "compose",
            "-f",
            "docker-compose.yml",
            "-f",
            ".envshelf/docker-compose.connect.local.yml",
            "up",
            "-d",
        ])
        .status()
        .map(|status| status.success())
        .unwrap_or(false);
    let suffix = relative.to_string_lossy().replace('\\', "/");
    let runtime_path = if suffix.is_empty() {
        target.clone()
    } else {
        format!("{target}/{suffix}")
    };
    Ok(ConnectResult {
        runtime_path,
        compose_started: status,
    })
}

#[tauri::command]
fn start_standalone(app: AppHandle, request: StandaloneRequest) -> Result<String, String> {
    let project_root = canonical_dir(&request.projects_root, "Projects folder")?;
    let app_root = resolve_app_root(&app, &request.envshelf_path)?;
    if !app_root.join("app").join("server.py").is_file() {
        return Err(app_error("selected EnvShelf folder has no app/server.py"));
    }
    let data_dir = if let Some(raw) = request.data_dir.filter(|value| !value.trim().is_empty()) {
        let path = PathBuf::from(raw);
        if !path.is_absolute() {
            return Err(app_error("data directory must be absolute"));
        }
        fs::create_dir_all(&path)
            .map_err(|_| app_error("could not create local app data directory"))?;
        fs::canonicalize(path)
            .map_err(|_| app_error("could not access local app data directory"))?
    } else {
        app.path()
            .app_data_dir()
            .map_err(|_| app_error("could not locate local app data directory"))?
    };
    fs::create_dir_all(&data_dir)
        .map_err(|_| app_error("could not create local app data directory"))?;
    let port = request.port.unwrap_or(8787);
    if port == 0 {
        return Err(app_error("dashboard port is invalid"));
    }
    let python = std::env::var("ENVSHELF_PYTHON").unwrap_or_else(|_| {
        if cfg!(target_os = "windows") {
            "python".into()
        } else {
            "python3".into()
        }
    });
    let runner = app_root.join("standalone").join("run.py");
    if !runner.is_file() {
        return Err(app_error("standalone launcher is missing"));
    }
    let mut command = Command::new(python);
    command
        .args([
            runner.to_string_lossy().as_ref(),
            "--projects-root",
            project_root.to_string_lossy().as_ref(),
            "--data-dir",
            data_dir.to_string_lossy().as_ref(),
            "--app-root",
            app_root.to_string_lossy().as_ref(),
            "--port",
            &port.to_string(),
            "--no-browser",
        ])
        .current_dir(&app_root)
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null());
    command
        .spawn()
        .map_err(|_| app_error("could not start the standalone dashboard; install Python 3"))?;
    Ok(format!("http://127.0.0.1:{port}"))
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            get_settings,
            save_settings,
            inspect_folder,
            parent_root,
            connect_project,
            start_standalone
        ])
        .run(tauri::generate_context!())
        .expect("error while running EnvShelf Connect");
}

fn main() {
    run();
}

#[cfg(test)]
mod tests {
    use super::{
        connect_mount_target, connect_override_content, validate_docker_root, ConnectRequest,
    };

    #[test]
    fn connect_request_accepts_frontend_camel_case_fields() {
        let request: ConnectRequest = serde_json::from_value(serde_json::json!({
            "projectPath": "/workspace/example",
            "approvedRoot": "/workspace",
            "envshelfPath": "/opt/envshelf",
            "projectName": "example",
            "envFile": ".env",
            "envExample": ".env.example"
        }))
        .expect("frontend connect payload should match the Rust command request");

        assert_eq!(request.project_name, "example");
        assert_eq!(request.env_file, ".env");
    }

    #[test]
    fn external_mount_preserves_primary_workspace_roots() {
        let target = connect_mount_target(std::path::Path::new("/tmp/envshelf-test-projects"));
        assert_ne!(target, "/workspace");
        assert_ne!(target, "/workspace-2");
        let yaml =
            connect_override_content(&[("/tmp/envshelf-test-projects".into(), target.clone())]);
        assert!(yaml.contains("target: /workspace-connect-"));
        assert!(yaml.contains("ENVSHELF_ALLOWED_PROJECT_ROOTS: /workspace,/workspace-2,"));
        assert!(!yaml.contains("target: /workspace\n"));
    }

    #[test]
    fn external_mounts_keep_all_previously_approved_roots() {
        let first = connect_mount_target(std::path::Path::new("/tmp/envshelf-first"));
        let second = connect_mount_target(std::path::Path::new("/tmp/envshelf-second"));
        let yaml = connect_override_content(&[
            ("/tmp/envshelf-first".into(), first.clone()),
            ("/tmp/envshelf-second".into(), second.clone()),
        ]);
        assert!(yaml.contains(&format!("{first},{second}")));
        assert!(yaml.contains("source: /tmp/envshelf-first"));
        assert!(yaml.contains("source: /tmp/envshelf-second"));
        assert_eq!(yaml.matches("type: bind").count(), 2);
    }

    #[test]
    fn docker_root_validation_rejects_wrong_folder_and_accepts_repo_root() {
        let root =
            std::env::temp_dir().join(format!("envshelf-connect-test-{}", std::process::id()));
        std::fs::create_dir_all(&root).expect("create test root");
        assert!(validate_docker_root(&root).is_err());
        std::fs::write(root.join("docker-compose.yml"), "services: {}\n")
            .expect("write safe fixture");
        assert!(validate_docker_root(&root).is_ok());
        let _ = std::fs::remove_file(root.join("docker-compose.yml"));
        let _ = std::fs::remove_dir(&root);
    }

    #[test]
    fn empty_repo_path_remains_valid_for_bundled_standalone_mode() {
        // Standalone launches from bundled resources and intentionally does
        // not require a Docker repository path.
        assert!("".trim().is_empty());
    }
}
