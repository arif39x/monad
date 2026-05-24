use crate::error::RuntimeError;
use crate::models::PolicyLevel;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone)]
pub struct SandboxPolicy {
    allowed_prefixes: Vec<String>,
    allowed_read_roots: Vec<PathBuf>,
    allowed_write_roots: Vec<PathBuf>,
}

impl SandboxPolicy {
    pub fn new(
        allowed_prefixes: Vec<String>,
        allowed_read_roots: Vec<PathBuf>,
        allowed_write_roots: Vec<PathBuf>,
    ) -> Self {
        Self {
            allowed_prefixes,
            allowed_read_roots,
            allowed_write_roots,
        }
    }

    pub fn validate_command(
        &self,
        command: &[String],
        level: &PolicyLevel,
    ) -> Result<(), RuntimeError> {
        let Some(executable) = command.first() else {
            return Err(RuntimeError::InvalidRequest("empty command".to_string()));
        };

        if matches!(level, PolicyLevel::Privileged) {
            return Ok(());
        }

        let allowed = self
            .allowed_prefixes
            .iter()
            .any(|prefix| executable.starts_with(prefix));

        if !allowed {
            return Err(RuntimeError::SandboxDenied(executable.to_string()));
        }

        Ok(())
    }

    pub fn validate_read_path(&self, path: &Path, level: &PolicyLevel) -> Result<(), RuntimeError> {
        if matches!(level, PolicyLevel::Privileged) {
            return Ok(());
        }

        if is_path_allowed(path, &self.allowed_read_roots) {
            return Ok(());
        }
        Err(RuntimeError::SandboxDenied(path.display().to_string()))
    }

    pub fn validate_write_path(
        &self,
        path: &Path,
        level: &PolicyLevel,
    ) -> Result<(), RuntimeError> {
        if matches!(level, PolicyLevel::Privileged) {
            return Ok(());
        }

        if is_path_allowed(path, &self.allowed_write_roots) {
            return Ok(());
        }
        Err(RuntimeError::SandboxDenied(path.display().to_string()))
    }
}

fn is_path_allowed(path: &Path, roots: &[PathBuf]) -> bool {
    match path.canonicalize() {
        Ok(resolved) => roots.iter().any(|root| resolved.starts_with(root)),
        Err(_) => false,
    }
}
