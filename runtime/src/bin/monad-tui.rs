use std::collections::VecDeque;
use std::time::{Duration, Instant};

use crossterm::event::{self, Event, KeyCode, KeyEventKind};
use crossterm::terminal::{self, EnterAlternateScreen, LeaveAlternateScreen};
use ratatui::layout::{Alignment, Constraint, Direction, Layout, Rect};
use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{
    Block, Borders,
    List, ListItem, Paragraph, Wrap,
};
use ratatui::Frame;
use ratatui::{prelude::*, Terminal};
use tokio::sync::mpsc;
use tokio::io::{self, AsyncBufReadExt, BufReader};
use serde::{Deserialize, Serialize};

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
    timestamp: String,
    text: String,
    level: LogLevel,
}

#[derive(Clone)]
struct AgentState {
    name: String,
    status: AgentStatus,
    token_usage: u64,
    current_action: String,
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

struct App {
    agents: Vec<AgentState>,
    logs: VecDeque<LogEntry>,
    interaction_stream: VecDeque<LogEntry>,
    ast_context: Vec<String>,
    input: String,
    selected_agent: usize,
    total_tokens: u64,
    saved_tokens: u64,
    running: bool,
    pid: u32,
}

impl App {
    fn new() -> Self {
        App {
            agents: Vec::with_capacity(8),
            logs: VecDeque::with_capacity(50),
            interaction_stream: VecDeque::with_capacity(200),
            ast_context: Vec::with_capacity(16),
            input: String::with_capacity(128),
            selected_agent: 0,
            total_tokens: 0,
            saved_tokens: 0,
            running: true,
            pid: std::process::id(),
        }
    }

    fn handle_tui_event(&mut self, event: TuiEvent) {
        match event {
            TuiEvent::AgentUpdate { name, status, action, tokens } => {
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
                self.interaction_stream.push_back(LogEntry {
                    timestamp: String::new(), // Don't store timestamps for interaction
                    text,
                    level: log_level,
                });
                if self.interaction_stream.len() > 200 {
                    self.interaction_stream.pop_front();
                }
            }
            TuiEvent::AstUpdate { skeleton } => {
                self.ast_context = skeleton;
            }
            TuiEvent::MetricsUpdate { total_tokens, saved_tokens } => {
                self.total_tokens = total_tokens;
                self.saved_tokens = saved_tokens;
            }
            TuiEvent::Log { text } => {
                self.logs.push_back(LogEntry {
                    timestamp: String::new(),
                    text,
                    level: LogLevel::Info,
                });
                if self.logs.len() > 50 {
                    self.logs.pop_front();
                }
            }
        }
    }

    fn handle_key(&mut self, key: KeyCode, modifiers: event::KeyModifiers) {
        // Exit on 'q' or 'Ctrl+X'
        if key == KeyCode::Char('q') || (key == KeyCode::Char('x') && modifiers.contains(event::KeyModifiers::CONTROL)) {
            self.running = false;
            return;
        }

        match key {
            KeyCode::Backspace => {
                self.input.pop();
            }
            KeyCode::Enter => {
                if !self.input.is_empty() {
                    // In a real functional TUI, we would emit this to stdout
                    // so the parent process can handle it.
                    println!("{}", serde_json::to_string(&serde_json::json!({
                        "type": "user_input",
                        "text": self.input,
                        "target_agent": self.agents.get(self.selected_agent).map(|a| a.name.clone())
                    })).unwrap());
                    
                    self.interaction_stream.push_back(LogEntry {
                        timestamp: chrono_now(),
                        text: format!("[You]: {}", self.input),
                        level: LogLevel::Info,
                    });
                    self.input.clear();
                }
            }
            KeyCode::Char(c) => {
                self.input.push(c);
            }
            KeyCode::Up => {
                if self.selected_agent > 0 {
                    self.selected_agent -= 1;
                }
            }
            KeyCode::Down => {
                if !self.agents.is_empty() && self.selected_agent < self.agents.len() - 1 {
                    self.selected_agent += 1;
                }
            }
            _ => {}
        }
    }
}

fn chrono_now() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let d = SystemTime::now().duration_since(UNIX_EPOCH).unwrap();
    let secs = d.as_secs();
    let h = (secs / 3600) % 24;
    let m = (secs / 60) % 60;
    let s = secs % 60;
    format!("{:02}:{:02}:{:02}", h, m, s)
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Open /dev/tty for terminal I/O so stdout can be used for data
    let mut tty = std::fs::OpenOptions::new()
        .read(true)
        .write(true)
        .open("/dev/tty")?;
    
    terminal::enable_raw_mode()?;
    crossterm::execute!(tty, EnterAlternateScreen)?;

    let backend = CrosstermBackend::new(tty);
    let mut terminal = Terminal::new(backend)?;

    let mut app = App::new();
    let (tx, mut rx) = mpsc::channel::<TuiEvent>(100);

    let tx_event = tx.clone();
    tokio::spawn(async move {
        let stdin = io::stdin();
        let reader = BufReader::new(stdin);
        let mut lines = reader.lines();

        while let Ok(Some(line)) = lines.next_line().await {
            if let Ok(event) = serde_json::from_str::<TuiEvent>(&line) {
                let _ = tx_event.send(event).await;
            } else {
                let _ = tx_event.send(TuiEvent::Log { text: line }).await;
            }
        }
    });

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
            app.handle_tui_event(event);
        }

        if last_tick.elapsed() >= tick_rate {
            last_tick = Instant::now();
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
    let area = frame.area();
    
    // Responsive constraints: adapt to smaller terminals by reducing header/footer height
    let header_height = if area.height > 20 { 3 } else { 1 };
    let footer_height = if area.height > 15 { 3 } else { 1 };
    let ast_height = if area.height > 25 { 7 } else { 0 };

    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(header_height),
            Constraint::Min(5),
            Constraint::Length(ast_height),
            Constraint::Length(footer_height),
        ])
        .split(area);

    render_header(frame, app, chunks[0]);
    render_middle(frame, app, chunks[1]);
    if ast_height > 0 {
        render_ast_window(frame, app, chunks[2]);
    }
    render_footer(frame, app, chunks[3]);
}

fn render_header(frame: &mut Frame, app: &App, area: Rect) {
    let savings_pct = if app.total_tokens > 0 {
        (app.saved_tokens * 100) / app.total_tokens
    } else {
        0
    };

    let active_agent = app.agents.get(app.selected_agent).map(|a| a.name.as_str()).unwrap_or("None");

    let header_text = format!(
        " Monad CLI v0.1 | Active: @{} | Token Savings: {}% ",
        active_agent, savings_pct
    );
    
    let bar_width = 10;
    let filled = (savings_pct / 10).min(10) as usize;
    let bar = format!("[{}{}]", "|".repeat(filled), "-".repeat(bar_width - filled));

    let header_line = Line::from(vec![
        Span::styled(header_text, Style::default().add_modifier(Modifier::BOLD)),
        Span::styled(bar, Style::default().fg(Color::Green)),
        Span::raw(" | "),
        Span::styled(format!("PID: {}", app.pid), Style::default().fg(Color::DarkGray)),
    ]);

    let block = Block::default()
        .borders(if area.height > 1 { Borders::ALL } else { Borders::NONE })
        .border_style(Style::default().fg(Color::White));
    
    let inner = block.inner(area);
    frame.render_widget(block, area);
    frame.render_widget(Paragraph::new(header_line).alignment(Alignment::Left), inner);
}

fn render_middle(frame: &mut Frame, app: &mut App, area: Rect) {
    let sidebar_width = if area.width > 100 { 30 } else { 25 };
    let chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Length(sidebar_width), Constraint::Min(10)])
        .split(area);

    render_sidebar(frame, app, chunks[0]);
    render_interaction_stream(frame, app, chunks[1]);
}

fn render_sidebar(frame: &mut Frame, app: &App, area: Rect) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Percentage(60), Constraint::Percentage(40)])
        .split(area);

    // Agent Registry
    let registry_block = Block::default()
        .title(" AGENT REGISTRY ")
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::White));
    let registry_inner = registry_block.inner(chunks[0]);
    frame.render_widget(registry_block, chunks[0]);

    let mut agent_items = Vec::new();
    for (i, agent) in app.agents.iter().enumerate() {
        let check = if agent.status == AgentStatus::Active { "[✓]" } else { "[ ]" };
        let style = if i == app.selected_agent {
            Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)
        } else {
            match agent.status {
                AgentStatus::Failed => Style::default().fg(Color::Red),
                _ => Style::default().fg(Color::White),
            }
        };
        agent_items.push(ListItem::new(format!(" {} @{}", check, agent.name)).style(style));
    }
    if agent_items.is_empty() {
        agent_items.push(ListItem::new(" (No agents detected)").style(Style::default().fg(Color::DarkGray)));
    }
    frame.render_widget(List::new(agent_items), registry_inner);

    // Session Logs
    let logs_block = Block::default()
        .title(" SESSION LOGS ")
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::White));
    let logs_inner = logs_block.inner(chunks[1]);
    frame.render_widget(logs_block, chunks[1]);

    let log_items: Vec<ListItem> = app.logs.iter().rev().map(|l| {
        ListItem::new(format!(" > {}", l.text)).style(Style::default().fg(Color::DarkGray))
    }).collect();
    frame.render_widget(List::new(log_items), logs_inner);
}

fn render_interaction_stream(frame: &mut Frame, app: &App, area: Rect) {
    let block = Block::default()
        .title(" INTERACTION STREAM ")
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::White));
    let inner = block.inner(area);
    frame.render_widget(block, area);

    let lines: Vec<Line> = app.interaction_stream.iter().map(|l| {
        let color = match l.level {
            LogLevel::Success => Color::Green,
            LogLevel::Warning => Color::Yellow,
            LogLevel::Error => Color::Red,
            LogLevel::Info => {
                if l.text.contains("[You]:") {
                    Color::White
                } else if l.text.contains("[ZeroLang]:") {
                    Color::Cyan
                } else {
                    Color::DarkGray
                }
            }
        };

        Line::from(Span::styled(&l.text, Style::default().fg(color)))
    }).collect();

    frame.render_widget(Paragraph::new(lines).wrap(Wrap { trim: true }).scroll(( (app.interaction_stream.len() as u16).saturating_sub(inner.height), 0)), inner);
}

fn render_ast_window(frame: &mut Frame, app: &App, area: Rect) {
    let block = Block::default()
        .title(" AST CONTEXT WINDOW (Live ZeroLang Skeleton View) ")
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::White));
    let inner = block.inner(area);
    frame.render_widget(block, area);

    let lines: Vec<Line> = app.ast_context.iter().map(|l| {
        Line::from(Span::styled(l, Style::default().fg(Color::Cyan)))
    }).collect();

    if lines.is_empty() {
        frame.render_widget(Paragraph::new(" (No AST context active)").style(Style::default().fg(Color::DarkGray)), inner);
    } else {
        frame.render_widget(Paragraph::new(lines), inner);
    }
}

fn render_footer(frame: &mut Frame, app: &App, area: Rect) {
    let active_agent = app.agents.get(app.selected_agent).map(|a| a.name.as_str()).unwrap_or("aider");
    let input_text = if area.height > 1 {
        format!("> @{} {}_ ", active_agent, app.input)
    } else {
        format!("@{} > {} ", active_agent, app.input)
    };

    let block = Block::default()
        .borders(if area.height > 1 { Borders::ALL } else { Borders::NONE })
        .border_style(Style::default().fg(Color::White));
    let inner = block.inner(area);
    frame.render_widget(block, area);

    frame.render_widget(Paragraph::new(input_text).style(Style::default().fg(Color::White)), inner);
}
