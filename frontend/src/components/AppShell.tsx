import type { ReactNode } from "react";

import "../styles/workbench.css";

type AppShellProps = {
  children: ReactNode;
};

export function AppShell({ children }: AppShellProps) {
  const links = [
    ["workbench-task", "选择 Agent / 任务", "Submit Task"],
    ["workbench-runtime", "运行配置", "Runtime Configuration"],
    ["workbench-chat", "会话聊天", "Conversation Chat"],
    ["workbench-memory", "Agent 记忆", "Agent Memory"],
    ["workbench-shared-memory", "共享记忆", "Shared User Memory"],
    ["workbench-history", "执行历史", "Execution History"],
    ["workbench-inspector", "执行详情", "Execution Inspector"],
  ];

  return (
    <div className="workbench-shell">
      <a className="workbench-skip-link" href="#workbench-main">跳到工作区</a>
      <aside className="workbench-sidebar">
        <a className="workbench-brand" href="#workbench-top">
          <span className="workbench-brand-mark" aria-hidden="true">AD</span>
          <span><strong>AgentDesk</strong><small>本地工作台</small></span>
        </a>
        <nav aria-label="Workbench navigation">
          {links.map(([id, title, subtitle], index) => (
            <a className="workbench-nav-link" key={id} href={`#${id}`}>
              <span className="workbench-nav-number" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
              <span><strong>{title}</strong><small>{subtitle}</small></span>
            </a>
          ))}
        </nav>
        <p className="workbench-sidebar-tip">先选择 Agent，再选择会话。点击导航可直接跳转到对应功能。</p>
      </aside>
      <main id="workbench-main" className="workbench-main" tabIndex={-1}>
        {children}
        <footer className="workbench-footer">AgentDesk · 本地工作台</footer>
      </main>
    </div>
  );
}
