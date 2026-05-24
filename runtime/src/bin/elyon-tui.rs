use std::collections::VecDeque;
use std::time::{Duration, Instant};

use crossterm::event::{self, Event, KeyCode, KeyEventKind};
use crossterm::terminal::{self, EnterAlternateScreen, LeaveAlternateScreen};
use ratatui::backend::CrosstermBackend;
use sysinfo::System;
use ratatui::layout::{Alignment, Constraint, Direction, Layout, Rect};
use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, BorderType, Borders, List, ListItem, Paragraph, Wrap};
use ratatui::Frame;
use ratatui::{prelude::*, Terminal};
use serde::{Deserialize, Serialize};
use std::fs;
use tokio::sync::mpsc;

#[derive(Debug, Clone, Serialize, Deserialize)]
struct Config {
    default_provider: String,
    providers: std::collections::BTreeMap<String, ProviderConfig>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct ProviderConfig {
    name: String,
    base_url: String,
    model: String,
    default_temperature: f32,
    default_max_tokens: u32,
    timeout_seconds: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct AgentMapping {
    name: String,
    provider: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
enum TuiEvent {
    AgentUpdate {
        name: String,
        status: String,
        action: String,
        tokens: u64,
    },
    Interaction {
        text: String,
        level: String,
    },
    AstUpdate {
        skeleton: Vec<String>,
    },
    MetricsUpdate {
        total_tokens: u64,
        saved_tokens: u64,
    },
    Log {
        text: String,
    },
    UserCommand {
        text: String,
        target_agent: Option<String>,
    },
}

#[derive(Clone, PartialEq)]
enum LogLevel {
    Info,
    Success,
    Warning,
    Error,
}

#[derive(Clone)]
struct LogEntry {
    text: String,
    level: LogLevel,
}

#[derive(Clone)]
struct AgentState {
    name: String,
    status: AgentStatus,
    token_usage: u64,
    current_action: String,
    history: VecDeque<LogEntry>,
}

#[derive(Clone, PartialEq)]
enum AgentStatus {
    Active,
    Idle,
    Waiting,
    Reasoning,
    Reviewing,
    Failed,
}

impl AgentStatus {
    fn from_str(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "active" => AgentStatus::Active,
            "waiting" => AgentStatus::Waiting,
            "reasoning" => AgentStatus::Reasoning,
            "reviewing" => AgentStatus::Reviewing,
            "failed" => AgentStatus::Failed,
            _ => AgentStatus::Idle,
        }
    }
}

#[derive(PartialEq)]
enum InputMode {
    Normal,
    Command,
}

struct App {
    agents: Vec<AgentState>,
    logs: VecDeque<LogEntry>,
    ast_context: Vec<String>,
    input: String,
    selected_agent: usize,
    total_tokens: u64,
    saved_tokens: u64,
    running: bool,
    mode: InputMode,
    session_id: String,
    tx: mpsc::Sender<TuiEvent>,
    sys: System,
    cpu_usage: f32,
    ram_mb: u64,
    sys_tick: Instant,
    latency_ms: f64,
    latency_samples: VecDeque<f64>,
}

impl App {
    fn new(tx: mpsc::Sender<TuiEvent>) -> Self {
        let mut sys = System::new();
        sys.refresh_memory();
        sys.refresh_cpu_all();
        let session_id = uuid::Uuid::new_v4().to_string();
        App {
            agents: Vec::with_capacity(8),
            logs: VecDeque::with_capacity(50),
            ast_context: Vec::with_capacity(16),
            input: String::with_capacity(128),
            selected_agent: 0,
            total_tokens: 0,
            saved_tokens: 0,
            running: true,
            mode: InputMode::Normal,
            session_id,
            tx,
            cpu_usage: 0.0,
            ram_mb: 0,
            sys_tick: Instant::now(),
            sys,
            latency_ms: 0.0,
            latency_samples: VecDeque::with_capacity(20),
        }
    }

    fn handle_tui_event(&mut self, event: TuiEvent) {
        match event {
            TuiEvent::AgentUpdate {
                name,
                status,
                action,
                tokens,
            } => {
                let status_enum = AgentStatus::from_str(&status);
                if let Some(agent) = self.agents.iter_mut().find(|a| a.name == name) {
                    agent.status = status_enum;
                    agent.current_action = action;
                    agent.token_usage = tokens;
                } else {
                    self.agents.push(AgentState {
                        name,
                        status: status_enum,
                        token_usage: tokens,
                        current_action: action,
                        history: VecDeque::with_capacity(100),
                    });
                }
            }
            TuiEvent::Interaction { text, level } => {
                let log_level = match level.to_lowercase().as_str() {
                    "success" => LogLevel::Success,
                    "warning" => LogLevel::Warning,
                    "error" => LogLevel::Error,
                    _ => LogLevel::Info,
                };

                // Route interaction to the selected agent for now, or all if global
                if let Some(agent) = self.agents.get_mut(self.selected_agent) {
                    agent.history.push_back(LogEntry {
                        text,
                        level: log_level,
                    });
                    if agent.history.len() > 100 {
                        agent.history.pop_front();
                    }
                }
            }
            TuiEvent::AstUpdate { skeleton } => {
                self.ast_context = skeleton;
            }
            TuiEvent::MetricsUpdate {
                total_tokens,
                saved_tokens,
            } => {
                self.total_tokens = total_tokens;
                self.saved_tokens = saved_tokens;
            }
            TuiEvent::Log { text } => {
                if let Some(rest) = text.strip_prefix("__latency__:") {
                    if let Ok(ms) = rest.parse::<f64>() {
                        self.record_latency(Duration::from_secs_f64(ms / 1000.0));
                        return;
                    }
                }
                self.logs.push_back(LogEntry {
                    text,
                    level: LogLevel::Info,
                });
                if self.logs.len() > 50 {
                    self.logs.pop_front();
                }
            }
            TuiEvent::UserCommand { .. } => {}
        }
    }

    fn record_latency(&mut self, duration: Duration) {
        let ms = duration.as_secs_f64() * 1000.0;
        self.latency_samples.push_back(ms);
        if self.latency_samples.len() > 20 {
            self.latency_samples.pop_front();
        }
        self.latency_ms =
            self.latency_samples.iter().sum::<f64>() / self.latency_samples.len() as f64;
    }

    fn refresh_system(&mut self) {
        self.sys.refresh_memory();
        self.sys.refresh_cpu_all();
        self.ram_mb = self.sys.used_memory() / (1024 * 1024);
        self.cpu_usage = self.sys.global_cpu_usage();
        self.sys_tick = Instant::now();
    }

    fn handle_key(&mut self, key: KeyCode, modifiers: event::KeyModifiers) {
        if self.mode == InputMode::Normal {
            match key {
                KeyCode::Char(':') => {
                    self.mode = InputMode::Command;
                    self.input.push(':');
                }
                KeyCode::Char('q') => {
                    self.running = false;
                }
                KeyCode::Char('x') if modifiers.contains(event::KeyModifiers::CONTROL) => {
                    self.running = false;
                }
                KeyCode::Char('i') | KeyCode::Enter => {
                    self.mode = InputMode::Command;
                }
                KeyCode::Up | KeyCode::Char('k') => {
                    if self.selected_agent > 0 {
                        self.selected_agent -= 1;
                    }
                }
                KeyCode::Down | KeyCode::Char('j') => {
                    if !self.agents.is_empty() && self.selected_agent < self.agents.len() - 1 {
                        self.selected_agent += 1;
                    }
                }
                _ => {}
            }
            return;
        }

        // Command/Input Mode
        match key {
            KeyCode::Esc => {
                self.mode = InputMode::Normal;
                self.input.clear();
            }
            KeyCode::Backspace => {
                self.input.pop();
                if self.input.is_empty() {
                    self.mode = InputMode::Normal;
                }
            }
            KeyCode::Enter => {
                if !self.input.is_empty() {
                    let text = if self.input.starts_with(':') {
                        self.input[1..].to_string()
                    } else {
                        self.input.clone()
                    };

                    // Handle :spawn command
                    if text.starts_with("spawn ") {
                        let name = text.trim_start_matches("spawn ").trim().to_string();
                        if !name.is_empty() && !self.agents.iter().any(|a| a.name == name) {
                            let _ = self.tx.try_send(TuiEvent::AgentUpdate {
                                name: name.clone(),
                                status: "idle".to_string(),
                                action: "Standing by".to_string(),
                                tokens: 0,
                            });
                        }
                    } else {
                        let _ = self.tx.try_send(TuiEvent::UserCommand {
                            text,
                            target_agent: None,
                        });
                    }

                    self.input.clear();
                    self.mode = InputMode::Normal;
                }
            }
            KeyCode::Char(c) => {
                self.input.push(c);
            }
            _ => {}
        }
    }
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut tty = std::fs::OpenOptions::new()
        .read(true)
        .write(true)
        .open("/dev/tty")?;

    terminal::enable_raw_mode()?;
    crossterm::execute!(tty, EnterAlternateScreen)?;

    let backend = CrosstermBackend::new(tty);
    let mut terminal = Terminal::new(backend)?;

    let config: Config = match fs::read_to_string("elyon.toml") {
        Ok(content) => toml::from_str(&content).unwrap_or_else(|_| Config {
            default_provider: "local_mock".to_string(),
            providers: std::collections::BTreeMap::new(),
        }),
        Err(_) => Config {
            default_provider: "local_mock".to_string(),
            providers: std::collections::BTreeMap::new(),
        },
    };

    // Build agent mappings from config providers
    let agent_mappings: Vec<AgentMapping> = config
        .providers
        .iter()
        .map(|(name, _)| AgentMapping {
            name: name.clone(),
            provider: name.clone(),
        })
        .collect();

    let (tx, mut rx) = mpsc::channel::<TuiEvent>(100);
    let mut app = App::new(tx.clone());

        // Seed agents from config providers
        if agent_mappings.is_empty() {
            for name in &["agent-1", "agent-2"] {
            let _ = tx.try_send(TuiEvent::AgentUpdate {
                name: name.to_string(),
                status: "idle".to_string(),
                action: "Standing by".to_string(),
                tokens: 0,
            });
        }
    } else {
        for mapping in &agent_mappings {
            let _ = tx.try_send(TuiEvent::AgentUpdate {
                name: mapping.name.clone(),
                status: "idle".to_string(),
                action: "Standing by".to_string(),
                tokens: 0,
            });
        }
    }

    let tick_rate = Duration::from_millis(50);
    let mut last_tick = Instant::now();

    loop {
        terminal.draw(|f| ui(f, &mut app))?;

        let timeout = tick_rate
            .checked_sub(last_tick.elapsed())
            .unwrap_or_else(|| Duration::from_secs(0));

        if event::poll(timeout)? {
            if let Event::Key(key) = event::read()? {
                if key.kind == KeyEventKind::Press {
                    app.handle_key(key.code, key.modifiers);
                    if !app.running {
                        break;
                    }
                }
            }
        }

        while let Ok(event) = rx.try_recv() {
            if let TuiEvent::UserCommand {
                text,
                target_agent: _,
            } = event
            {
                let _ = tx.try_send(TuiEvent::Log {
                    text: format!("Broadcasting command to {} agents...", app.agents.len()),
                });

                    let agent_snapshot: Vec<String> =
                        app.agents.iter().map(|a| a.name.clone()).collect();
                    let tx_clone = tx.clone();
                    let config_clone = config.clone();
                    let latency_tx = tx.clone();

                    // Spawn parallel requests for ALL agents
                    let tasks: Vec<_> = agent_snapshot
                        .into_iter()
                        .map(|agent_name| {
                            let tx = tx_clone.clone();
                            let config = config_clone.clone();
                            let cmd_text = text.clone();
                            let lat_tx = latency_tx.clone();
                            tokio::spawn(async move {
                                let start = Instant::now();

                                let _ = tx
                                    .send(TuiEvent::AgentUpdate {
                                        name: agent_name.clone(),
                                        status: "reasoning".to_string(),
                                        action: "Thinking...".to_string(),
                                        tokens: 0,
                                    })
                                    .await;

                                let provider = config
                                    .providers
                                    .get(&agent_name)
                                    .or_else(|| config.providers.get(&config.default_provider));

                                let response_text = if let Some(p) = provider {
                                    if p.base_url.is_empty() {
                                        tokio::time::sleep(Duration::from_millis(300)).await;
                                        format!("[{agent_name}]: {cmd_text}\n  → (mock response)")
                                    } else {
                                        let client = reqwest::Client::new();
                                        let payload = serde_json::json!({
                                            "model": p.model,
                                            "prompt": cmd_text,
                                            "temperature": p.default_temperature,
                                            "max_tokens": p.default_max_tokens,
                                            "trace_id": uuid::Uuid::new_v4().to_string(),
                                        });
                                        match client.post(&p.base_url).json(&payload).send().await {
                                            Ok(res) => {
                                                if let Ok(json) = res.json::<serde_json::Value>().await
                                                {
                                                    json["text"]
                                                        .as_str()
                                                        .unwrap_or("(no text in response)")
                                                        .to_string()
                                                } else {
                                                    "(response parse error)".to_string()
                                                }
                                            }
                                            Err(e) => format!("(API error: {e})"),
                                        }
                                    }
                                } else {
                                    tokio::time::sleep(Duration::from_millis(300)).await;
                                    format!("[{agent_name}]: {cmd_text}\n  → (no provider configured)")
                                };

                                let elapsed = start.elapsed();
                                let _ = lat_tx
                                    .send(TuiEvent::Log {
                                        text: format!("__latency__:{}", elapsed.as_secs_f64() * 1000.0),
                                    })
                                    .await;

                                let _ = tx
                                    .send(TuiEvent::Interaction {
                                        text: response_text,
                                        level: "success".to_string(),
                                    })
                                    .await;

                                let _ = tx
                                    .send(TuiEvent::AgentUpdate {
                                        name: agent_name,
                                        status: "idle".to_string(),
                                        action: "Standing by".to_string(),
                                        tokens: 0,
                                    })
                                    .await;
                            })
                        })
                        .collect();

                // Run all agent requests concurrently
                for task in tasks {
                    let _ = task.await;
                }
            } else {
                app.handle_tui_event(event);
            }
        }

        if last_tick.elapsed() >= tick_rate {
            last_tick = Instant::now();
            if app.sys_tick.elapsed() >= Duration::from_secs(1) {
                app.refresh_system();
            }
        }

        if !app.running {
            break;
        }
    }

    terminal::disable_raw_mode()?;
    crossterm::execute!(terminal.backend_mut(), LeaveAlternateScreen)?;
    Ok(())
}

fn ui(frame: &mut Frame, app: &mut App) {
    let area = frame.size();

    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(1), // Top status bar
            Constraint::Min(5),    // Main workspace
            Constraint::Length(1), // Session info bar
            Constraint::Length(3), // Command input
        ])
        .split(area);

    render_top_bar(frame, app, chunks[0]);
    render_workspace(frame, app, chunks[1]);
    render_session_bar(frame, app, chunks[2]);
    render_command_bar(frame, app, chunks[3]);
}

fn render_top_bar(frame: &mut Frame, app: &App, area: Rect) {
    let active_count = app
        .agents
        .iter()
        .filter(|a| a.status != AgentStatus::Idle)
        .count();
    let savings_k = app.saved_tokens / 1000;

    let top_line = Line::from(vec![
        Span::styled(
            " ⚡ ELYON ",
            Style::default()
                .fg(Color::Black)
                .bg(Color::Cyan)
                .add_modifier(Modifier::BOLD),
        ),
        Span::raw(" │ "),
        Span::styled("ACTIVE: ", Style::default().fg(Color::Gray)),
        Span::styled(
            format!("{} Agents", active_count),
            Style::default().fg(Color::White),
        ),
        Span::raw(" │ "),
        Span::styled("TOKENS SAVED: ", Style::default().fg(Color::Gray)),
        Span::styled(format!("{}K", savings_k), Style::default().fg(Color::Green)),
        Span::raw(" │ "),
        Span::styled("RAM: ", Style::default().fg(Color::Gray)),
        Span::styled(format!("{}MB", app.ram_mb), Style::default().fg(Color::Yellow)),
        Span::raw(" │ "),
        Span::styled("CPU: ", Style::default().fg(Color::Gray)),
        Span::styled(format!("{:.0}%", app.cpu_usage), Style::default().fg(Color::Yellow)),
    ]);

    frame.render_widget(Paragraph::new(top_line).bg(Color::Indexed(234)), area);
}

fn render_workspace(frame: &mut Frame, app: &mut App, area: Rect) {
    let sidebar_width = 16;
    let main_chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Length(sidebar_width), Constraint::Min(20)])
        .split(area);

    render_agent_sidebar(frame, app, main_chunks[0]);
    render_agent_panes(frame, app, main_chunks[1]);
}

fn render_agent_sidebar(frame: &mut Frame, app: &App, area: Rect) {
    let block = Block::default()
        .borders(Borders::RIGHT)
        .border_style(Style::default().fg(Color::Indexed(237)));

    let inner = block.inner(area);
    frame.render_widget(block, area);

    let mut items = Vec::new();
    items.push(ListItem::new(Span::styled(
        "AGENTS",
        Style::default()
            .fg(Color::DarkGray)
            .add_modifier(Modifier::BOLD),
    )));
    items.push(ListItem::new(""));

    let active_agents: Vec<_> = app
        .agents
        .iter()
        .enumerate()
        .filter(|(_, a)| a.status != AgentStatus::Idle && a.status != AgentStatus::Failed)
        .collect();
    let idle_agents: Vec<_> = app
        .agents
        .iter()
        .enumerate()
        .filter(|(_, a)| a.status == AgentStatus::Idle || a.status == AgentStatus::Failed)
        .collect();

    if !active_agents.is_empty() {
        items.push(ListItem::new(Span::styled(
            "ACTIVE",
            Style::default().fg(Color::Indexed(240)),
        )));
        for (i, agent) in active_agents {
            let style = if i == app.selected_agent {
                Style::default()
                    .fg(Color::Cyan)
                    .add_modifier(Modifier::BOLD)
            } else {
                Style::default().fg(Color::Green)
            };
            let prefix = match agent.status {
                AgentStatus::Reasoning => "⚡ ",
                _ => "● ",
            };
            items.push(ListItem::new(Span::styled(
                format!("{}{}", prefix, agent.name),
                style,
            )));
        }
        items.push(ListItem::new(""));
    }

    if !idle_agents.is_empty() {
        items.push(ListItem::new(Span::styled(
            "IDLE",
            Style::default().fg(Color::Indexed(240)),
        )));
        for (i, agent) in idle_agents {
            let style = if i == app.selected_agent {
                Style::default()
                    .fg(Color::Cyan)
                    .add_modifier(Modifier::BOLD)
            } else {
                Style::default().fg(Color::Indexed(243))
            };
            let prefix = if agent.status == AgentStatus::Failed {
                "✖ "
            } else {
                "○ "
            };
            items.push(ListItem::new(Span::styled(
                format!("{}{}", prefix, agent.name),
                style,
            )));
        }
    }

    frame.render_widget(List::new(items), inner);
}

fn render_agent_panes(frame: &mut Frame, app: &App, area: Rect) {
    let active_count = app
        .agents
        .iter()
        .filter(|a| a.status != AgentStatus::Idle)
        .count();

    if active_count == 0 {
        let block = Block::default()
            .borders(Borders::ALL)
            .border_style(Style::default().fg(Color::Indexed(237)));
        let inner = block.inner(area);
        frame.render_widget(block, area);
        frame.render_widget(
            Paragraph::new("No active agents. Use :spawn to start.")
                .alignment(Alignment::Center)
                .style(Style::default().fg(Color::Indexed(240))),
            inner,
        );
        return;
    }

    // Dynamic grid layout
    let active_agents: Vec<_> = app
        .agents
        .iter()
        .enumerate()
        .filter(|(_, a)| a.status != AgentStatus::Idle)
        .collect();
    let cols = if active_count > 1 { 2 } else { 1 };
    let rows = (active_count + 1) / 2;

    let row_constraints = vec![Constraint::Percentage(100 / rows as u16); rows];
    let row_chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints(row_constraints)
        .split(area);

    for r in 0..rows {
        let col_count = if r == rows - 1 && active_count % 2 != 0 {
            1
        } else {
            cols
        };
        let col_constraints = vec![Constraint::Percentage(100 / col_count as u16); col_count];
        let col_chunks = Layout::default()
            .direction(Direction::Horizontal)
            .constraints(col_constraints)
            .split(row_chunks[r]);

        for c in 0..col_count {
            let idx = r * 2 + c;
            if let Some((i, agent)) = active_agents.get(idx) {
                render_pane(frame, app, *i, agent, col_chunks[c]);
            }
        }
    }
}

fn render_pane(frame: &mut Frame, app: &App, id: usize, agent: &AgentState, area: Rect) {
    let is_selected = id == app.selected_agent;
    let border_color = if is_selected {
        Color::Cyan
    } else {
        Color::Indexed(237)
    };

    let title = Span::styled(
        format!(" [ !{} ] {} ", id + 1, agent.name.to_uppercase()),
        Style::default()
            .fg(if is_selected {
                Color::Black
            } else {
                Color::White
            })
            .bg(if is_selected {
                Color::Cyan
            } else {
                Color::Indexed(237)
            }),
    );

    let block = Block::default()
        .title(title)
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(border_color));

    let inner = block.inner(area);
    frame.render_widget(block, area);

    let mut lines = Vec::new();
    for log in &agent.history {
        let color = match log.level {
            LogLevel::Success => Color::Green,
            LogLevel::Warning => Color::Yellow,
            LogLevel::Error => Color::Red,
            LogLevel::Info => Color::White,
        };
        let prefix = match log.level {
            LogLevel::Success => "✓ ",
            LogLevel::Warning => "⚠ ",
            LogLevel::Error => "✖ ",
            _ => "  ",
        };
        lines.push(Line::from(Span::styled(
            format!("{}{}", prefix, log.text),
            Style::default().fg(color),
        )));
    }

    if agent.status == AgentStatus::Reasoning {
        lines.push(Line::from(Span::styled(
            format!("... {}", agent.current_action),
            Style::default().fg(Color::Magenta),
        )));
    }

    frame.render_widget(Paragraph::new(lines).wrap(Wrap { trim: true }), inner);
}

fn render_session_bar(frame: &mut Frame, app: &App, area: Rect) {
    let mode_str = match app.mode {
        InputMode::Normal => " NORMAL ",
        InputMode::Command => " COMMAND ",
    };
    let mode_style = match app.mode {
        InputMode::Normal => Style::default()
            .fg(Color::Black)
            .bg(Color::White)
            .add_modifier(Modifier::BOLD),
        InputMode::Command => Style::default()
            .fg(Color::Black)
            .bg(Color::Yellow)
            .add_modifier(Modifier::BOLD),
    };

    let line = Line::from(vec![
        Span::styled(mode_str, mode_style),
        Span::raw(" │ "),
        Span::styled("SESSION: ", Style::default().fg(Color::Gray)),
        Span::styled(&app.session_id, Style::default().fg(Color::White)),
        Span::raw(" │ "),
        Span::styled("LATENCY: ", Style::default().fg(Color::Gray)),
        Span::styled(format!("{:.0}ms", app.latency_ms), Style::default().fg(Color::Green)),
    ]);

    frame.render_widget(Paragraph::new(line).bg(Color::Indexed(234)), area);
}

fn render_command_bar(frame: &mut Frame, app: &App, area: Rect) {
    let border_color = match app.mode {
        InputMode::Command => Color::Yellow,
        _ => Color::Indexed(237),
    };

    let block = Block::default()
        .borders(Borders::ALL)
        .border_style(Style::default().fg(border_color));

    let inner = block.inner(area);
    frame.render_widget(block, area);

    let input_text = if app.input.is_empty() && app.mode == InputMode::Normal {
        Span::styled(
            "Press 'i' or ':' to enter command...",
            Style::default().fg(Color::Indexed(240)),
        )
    } else {
        Span::raw(&app.input)
    };

    let input_line = Line::from(vec![
        Span::styled(
            "> ",
            Style::default()
                .fg(Color::Cyan)
                .add_modifier(Modifier::BOLD),
        ),
        input_text,
        if app.mode == InputMode::Command {
            Span::styled(
                "_",
                Style::default()
                    .fg(Color::White)
                    .add_modifier(Modifier::SLOW_BLINK),
            )
        } else {
            Span::raw("")
        },
    ]);

    frame.render_widget(Paragraph::new(input_line), inner);
}
