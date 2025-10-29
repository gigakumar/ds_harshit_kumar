import SwiftUI

struct ControlCenterSheet: View {
    enum Tab: String, CaseIterable, Identifiable {
        case status
        case logs
        case tools

        var id: String { rawValue }

        var title: String {
            switch self {
            case .status: return "Status"
            case .logs: return "Logs"
            case .tools: return "Tools"
            }
        }

        var icon: String {
            switch self {
            case .status: return "waveform.path.ecg"
            case .logs: return "clock.arrow.circlepath"
            case .tools: return "wrench.and.screwdriver"
            }
        }
    }

    @EnvironmentObject private var appState: AppState
    @Environment(\.themeDescriptor) private var theme
    @ObservedObject var dashboardViewModel: AutomationDashboardViewModel
    let openSettings: () -> Void

    @State private var selectedTab: Tab
    @State private var commandQuery: String = ""
    @State private var expandedCategories: Set<String> = Set(Self.defaultCommandCategories.map(\.id))

    init(selectedTab: Tab, dashboardViewModel: AutomationDashboardViewModel, openSettings: @escaping () -> Void) {
        _selectedTab = State(initialValue: selectedTab)
        self.dashboardViewModel = dashboardViewModel
        self.openSettings = openSettings
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            Capsule()
                .fill(theme.secondaryText.opacity(0.35))
                .frame(width: 42, height: 5)
                .frame(maxWidth: .infinity)
                .padding(.top, 4)

            Picker("Focus", selection: $selectedTab) {
                ForEach(Tab.allCases) { tab in
                    Label(tab.title, systemImage: tab.icon)
                        .tag(tab)
                }
            }
            .pickerStyle(.segmented)

            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    switch selectedTab {
                    case .status:
                        statusView
                    case .logs:
                        logsView
                    case .tools:
                        toolsView
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .padding(24)
        .frame(minWidth: 560, minHeight: 480)
        .task {
            await ensureData(for: selectedTab)
        }
        .onChange(of: selectedTab) { _, tab in
            Task { @MainActor in
                await ensureData(for: tab)
            }
        }
    }

    @MainActor
    private func ensureData(for tab: Tab) async {
        switch tab {
        case .status:
            await appState.refreshConnectionStatus(force: true)
        case .logs:
            await dashboardViewModel.refreshLogsOnly()
        case .tools:
            break
        }
    }

    private var statusView: some View {
        VStack(alignment: .leading, spacing: 16) {
            GlassSectionHeader(title: "System status", systemImage: "waveform")
            ConnectionStatusHero(
                status: appState.connectionStatus,
                backendState: appState.backendLaunchState,
                refreshAction: {
                    Task { await appState.refreshConnectionStatus(force: true) }
                },
                openSettings: openSettings
            )
        }
    }

    private var logsView: some View {
        VStack(alignment: .leading, spacing: 16) {
            GlassSectionHeader(title: "Automation log", systemImage: "clock.arrow.circlepath")
            AutomationLogListView(events: dashboardViewModel.automationLog)
        }
    }

    private var toolsView: some View {
        VStack(alignment: .leading, spacing: 18) {
            GlassSectionHeader(title: "Quick tools", systemImage: "wrench.and.screwdriver")

            GlassContainer {
                VStack(alignment: .leading, spacing: 16) {
                    commandSearchField

                    ForEach(commandCategories) { category in
                        let isSearchActive = trimmedCommandQuery.isEmpty == false
                        let disclosureBinding = isSearchActive ? .constant(true) : binding(for: category)

                        DisclosureGroup(isExpanded: disclosureBinding) {
                            VStack(alignment: .leading, spacing: 10) {
                                ForEach(category.commands) { command in
                                    Button {
                                        perform(command: command.action)
                                    } label: {
                                        HStack(spacing: 14) {
                                            Image(systemName: command.icon)
                                                .font(.system(size: 18, weight: .medium))
                                                .foregroundColor(theme.accent)

                                            VStack(alignment: .leading, spacing: 4) {
                                                Text(command.title)
                                                    .font(.system(.body, design: .rounded))
                                                    .foregroundColor(theme.primaryText)
                                                Text(command.subtitle)
                                                    .font(.system(.caption, design: .rounded))
                                                    .foregroundColor(theme.secondaryText)
                                            }

                                            Spacer()
                                        }
                                        .padding(.vertical, 10)
                                        .padding(.horizontal, 12)
                                        .background(theme.quickActionBackground.opacity(0.45), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                                    }
                                    .buttonStyle(.plain)
                                }
                            }
                            .padding(.top, 6)
                        } label: {
                            HStack(spacing: 10) {
                                Image(systemName: category.icon)
                                    .font(.system(size: 16, weight: .semibold))
                                Text(category.title)
                                    .font(.system(.subheadline, design: .rounded))
                                    .fontWeight(.semibold)
                                Spacer()
                                if trimmedCommandQuery.isEmpty {
                                    Image(systemName: expandedCategories.contains(category.id) ? "chevron.down" : "chevron.right")
                                        .font(.system(size: 12, weight: .semibold))
                                        .foregroundColor(theme.secondaryText)
                                }
                            }
                            .foregroundColor(theme.primaryText)
                        }
                        .padding(.vertical, 4)
                    }
                }
            }
        }
    }

    private var commandSearchField: some View {
        HStack(spacing: 10) {
            Image(systemName: "magnifyingglass")
                .foregroundColor(theme.secondaryText)
            TextField("Search tools, status, or themes", text: $commandQuery)
                .textFieldStyle(.plain)
                .foregroundColor(theme.primaryText)
                .disableAutocorrection(true)
            if trimmedCommandQuery.isEmpty == false {
                Button {
                    commandQuery = ""
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundColor(theme.secondaryText.opacity(0.8))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.vertical, 10)
        .padding(.horizontal, 14)
        .background(theme.quickActionBackground.opacity(0.55), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
    }

    private var trimmedCommandQuery: String {
        commandQuery.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var commandCategories: [CommandCategory] {
        let base = Self.defaultCommandCategories
        guard trimmedCommandQuery.isEmpty == false else { return base }
        return base.compactMap { $0.filtered(by: trimmedCommandQuery) }
    }

    private func binding(for category: CommandCategory) -> Binding<Bool> {
        Binding(
            get: { expandedCategories.contains(category.id) },
            set: { isExpanded in
                if isExpanded {
                    expandedCategories.insert(category.id)
                } else {
                    expandedCategories.remove(category.id)
                }
            }
        )
    }

    private func perform(command action: CommandAction) {
        switch action {
        case .showSystemStatus:
            withAnimation { selectedTab = .status }
        case .openAutomationLog:
            withAnimation { selectedTab = .logs }
        case .openSettingsTools:
            withAnimation { selectedTab = .tools }
        case .refreshAllData:
            appState.refreshAll()
        case .jumpToSettings:
            withAnimation { openSettings() }
        case .summarizeInbox:
            if let quickAction = dashboardViewModel.quickActions.first(where: { $0.type == .summarizeInbox }) {
                dashboardViewModel.trigger(action: quickAction)
            }
            withAnimation { selectedTab = .tools }
        }
    }
}

private extension ControlCenterSheet {
    enum CommandAction: String, CaseIterable, Identifiable {
        case showSystemStatus
        case openAutomationLog
        case openSettingsTools
        case refreshAllData
        case jumpToSettings
        case summarizeInbox

        var id: String { rawValue }
    }

    struct CommandItem: Identifiable {
        let action: CommandAction
        let title: String
        let subtitle: String
        let icon: String

        var id: CommandAction { action }

        func matches(_ query: String) -> Bool {
            guard query.isEmpty == false else { return true }
            return title.localizedCaseInsensitiveContains(query) || subtitle.localizedCaseInsensitiveContains(query)
        }
    }

    struct CommandCategory: Identifiable {
        let id: String
        let title: String
        let icon: String
        let commands: [CommandItem]

        func filtered(by query: String) -> CommandCategory? {
            let filteredCommands = commands.filter { $0.matches(query) }
            guard filteredCommands.isEmpty == false else { return nil }
            return CommandCategory(id: id, title: title, icon: icon, commands: filteredCommands)
        }
    }

    static let defaultCommandCategories: [CommandCategory] = [
        CommandCategory(
            id: "system",
            title: "System",
            icon: "waveform.path.ecg",
            commands: [
                CommandItem(action: .showSystemStatus, title: "Show system status", subtitle: "Inspect daemon connection and uptime", icon: "waveform") ,
                CommandItem(action: .openAutomationLog, title: "Open automation log", subtitle: "Review recent automation events", icon: "clock.arrow.circlepath"),
                CommandItem(action: .refreshAllData, title: "Refresh all data", subtitle: "Reload settings, knowledge, and plugins", icon: "arrow.clockwise")
            ]
        ),
        CommandCategory(
            id: "settings",
            title: "Settings",
            icon: "gearshape",
            commands: [
                CommandItem(action: .openSettingsTools, title: "Open settings tools", subtitle: "Quick access to themes and maintenance", icon: "wrench.and.screwdriver"),
                CommandItem(action: .jumpToSettings, title: "Jump to settings", subtitle: "Manage permissions and connections", icon: "gearshape")
            ]
        ),
        CommandCategory(
            id: "automations",
            title: "Automations",
            icon: "sparkles",
            commands: [
                CommandItem(action: .summarizeInbox, title: "Summarize inbox", subtitle: "Scan mail and highlight follow-ups", icon: "tray.full")
            ]
        )
    ]
}
