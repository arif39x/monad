use elyon_runtime::{ExecRequest, RuntimeExecutor, RuntimeError, SandboxPolicy};
use serde_json::json;
use std::env;
use std::io::{self, Read};
use std::path::PathBuf;

#[tokio::main]
async fn main() {
    let mut raw = String::new();
    if let Err(err) = io::stdin().read_to_string(&mut raw) {
        emit_error(RuntimeError::InvalidRequest(err.to_string()));
        std::process::exit(1);
    }

    let request: ExecRequest = match serde_json::from_str(&raw) {
        Ok(request) => request,
        Err(err) => {
            emit_error(RuntimeError::InvalidRequest(err.to_string()));
            std::process::exit(1);
        }
    };

    let allowed_prefixes = env::var("ELYON_RUNTIME_ALLOWED_PREFIXES")
        .ok()
        .map(|value| {
            value
                .split(',')
                .map(str::trim)
                .filter(|part| !part.is_empty())
                .map(ToOwned::to_owned)
                .collect::<Vec<String>>()
        })
        .unwrap_or_default();

    let cwd = match env::current_dir() {
        Ok(path) => path,
        Err(err) => {
            emit_error(RuntimeError::InvalidRequest(err.to_string()));
            std::process::exit(1);
        }
    };

    let policy = SandboxPolicy::new(
        allowed_prefixes,
        vec![PathBuf::from(&cwd)],
        vec![PathBuf::from(&cwd)],
    );

    let executor = RuntimeExecutor::new(policy);
    match executor.execute(request).await {
        Ok(result) => println!("{}", serde_json::to_string(&result).unwrap_or_else(|_| "{}".to_string())),
        Err(err) => {
            emit_error(err);
            std::process::exit(1);
        }
    }
}

fn emit_error(error: RuntimeError) {
    let payload = json!({"error": error.to_string()});
    println!("{}", payload);
}
