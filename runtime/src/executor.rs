use crate::error::RuntimeError;
use crate::models::{ExecRequest, ExecResult};
use crate::sandbox::SandboxPolicy;
use crate::stream::read_limited;
use std::path::Path;
use std::process::Stdio;
use std::time::{Duration, Instant};
use tokio::process::Command;
use tokio::time::timeout;

#[derive(Debug, Clone)]
pub struct RuntimeExecutor {
    policy: SandboxPolicy,
}

impl RuntimeExecutor {
    pub fn new(policy: SandboxPolicy) -> Self {
        Self { policy }
    }

    pub async fn execute(&self, request: ExecRequest) -> Result<ExecResult, RuntimeError> {
        if request.command.is_empty() {
            return Err(RuntimeError::InvalidRequest("command cannot be empty".to_string()));
        }

        self.policy.validate_command(&request.command, &request.policy_level)?;

        let cwd = Path::new(&request.cwd);
        if !cwd.exists() {
            return Err(RuntimeError::InvalidRequest(format!(
                "cwd does not exist: {}",
                request.cwd
            )));
        }

        let program = request
            .command
            .first()
            .ok_or_else(|| RuntimeError::InvalidRequest("missing executable".to_string()))?
            .clone();
        let args: Vec<String> = request.command.iter().skip(1).cloned().collect();

        let mut command = Command::new(program);
        command
            .args(args)
            .current_dir(cwd)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .stdin(Stdio::null())
            .kill_on_drop(true)
            .envs(request.env.clone());

        let start = Instant::now();
        let mut child = command
            .spawn()
            .map_err(|err| RuntimeError::SpawnFailed(err.to_string()))?;

        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| RuntimeError::Io("stdout pipe was not available".to_string()))?;
        let stderr = child
            .stderr
            .take()
            .ok_or_else(|| RuntimeError::Io("stderr pipe was not available".to_string()))?;

        let stdout_limit = request.limits.max_stdout_bytes;
        let stderr_limit = request.limits.max_stderr_bytes;

        let stdout_task = tokio::spawn(async move { read_limited(stdout, stdout_limit).await });
        let stderr_task = tokio::spawn(async move { read_limited(stderr, stderr_limit).await });

        let wait_result = timeout(Duration::from_millis(request.limits.timeout_ms), child.wait()).await;

        let status = match wait_result {
            Ok(wait_output) => wait_output.map_err(|err| RuntimeError::WaitFailed(err.to_string()))?,
            Err(_) => {
                let _ = child.kill().await;
                return Err(RuntimeError::Timeout);
            }
        };

        let stdout = stdout_task
            .await
            .map_err(|err| RuntimeError::Io(err.to_string()))??;
        let stderr = stderr_task
            .await
            .map_err(|err| RuntimeError::Io(err.to_string()))??;

        Ok(ExecResult {
            exit_code: status.code().unwrap_or(-1),
            stdout,
            stderr,
            duration_ms: u64::try_from(start.elapsed().as_millis()).unwrap_or(u64::MAX),
        })
    }
}
