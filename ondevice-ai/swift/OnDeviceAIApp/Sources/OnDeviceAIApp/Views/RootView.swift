import SwiftUI

enum AppSection: String, CaseIterable, Identifiable {
    case planner
    case knowledge
    case automation
    case plugins
    case settings

    var id: String { rawValue }

    var title: String {
        switch self {
        case .planner: return "Planner"
        case .knowledge: return "Knowledge"
        case .automation: return "Automation"
        case .plugins: return "Plugins"
        case .settings: return "Settings"
        }
    }

    var caption: String {
        switch self {
        case .planner: return "Draft step-by-step plans"
        case .knowledge: return "Search indexed notes"
        case .automation: return "Monitor active automations"
        case .plugins: return "Manage integrations"
        case .settings: return "Configure the workspace"
        }
    }

    var icon: String {
        switch self {
        case .planner: return "list.bullet.rectangle"
        case .knowledge: return "books.vertical"
        case .automation: return "bolt.circle"
        case .plugins: return "puzzlepiece.extension"
        case .settings: return "gearshape"
        }
    }
}

struct RootView: View {
    @EnvironmentObject private var appState: AppState
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.themeDescriptor) private var theme
    @State private var selection: AppSection? = .planner
    @State private var hoveredSection: AppSection?
    @State private var globalSearch: String = ""
    @State private var controlCenterPresented: Bool = false

    var body: some View {
        let descriptor = appState.descriptor(for: colorScheme)
        return GlassBackground {
            NavigationSplitView {
                sidebar
            } detail: {
                detailStack
            }
            .environment(\.themeDescriptor, descriptor)
            .navigationSplitViewStyle(.balanced)
        }
        .task {
            await reload()
        }
        .onChange(of: scenePhase) { _, phase in
            guard phase == .active else { return }
            Task { await appState.refreshConnectionStatus(force: true) }
        }
        .onAppear {
            appState.updateSystemColorScheme(colorScheme)
        }
        .onChange(of: colorScheme) { _, newScheme in
            appState.updateSystemColorScheme(newScheme)
        }
    }

    private var sidebar: some View {
        List(selection: $selection) {
            sidebarHeader
                .listRowInsets(.init(top: 12, leading: 8, bottom: 4, trailing: 8))
                .listRowSeparator(.hidden)
                .listRowBackground(Color.clear)

            ForEach(AppSection.allCases) { section in
                sidebarRow(for: section)
                    .tag(section as AppSection?)
                    .listRowSeparator(.hidden)
                    .listRowInsets(.init(top: 4, leading: 10, bottom: 4, trailing: 10))
                    .listRowBackground(Color.clear)
            }
        }
        .listStyle(.sidebar)
        .environment(\.defaultMinListRowHeight, 44)
        .scrollContentBackground(.hidden)
        .background(theme.sidebarBackground)
        .frame(minWidth: 240)
        .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
        .padding(.vertical, 16)
        .padding(.leading, 12)
        .padding(.trailing, 18)
    }

    private var detailStack: some View {
        VStack(spacing: 24) {
            detailHeader
            detail(for: selection ?? .planner)
        }
        .padding(.horizontal, 32)
        .padding(.top, 16)
        .padding(.bottom, 28)
        .safeAreaInset(edge: .top, spacing: 0) {
            ConnectionStatusHero(
                status: appState.connectionStatus,
                backendState: appState.backendLaunchState,
                refreshAction: {
                    Task { await appState.refreshConnectionStatus(force: true) }
                },
                openSettings: {
                    selection = .settings
                }
            )
            .padding(.horizontal, 32)
            .padding(.top, 24)
        }
        .sheet(isPresented: $controlCenterPresented) {
            ControlCenterSheet(
                selectedTab: .status,
                dashboardViewModel: appState.automationDashboard,
                openSettings: { selection = .settings }
            )
            .environmentObject(appState)
            .environment(\.themeDescriptor, appState.themeDescriptor)
        }
    }

    @ViewBuilder
    private func detail(for section: AppSection) -> some View {
        switch section {
        case .planner:
            PlannerView(viewModel: appState.plannerViewModel)
        case .knowledge:
            KnowledgeView(viewModel: appState.knowledgeViewModel)
        case .automation:
            AutomationDashboardView(viewModel: appState.automationDashboard)
        case .plugins:
            PluginsView(viewModel: appState.pluginsViewModel)
        case .settings:
            SettingsDockView(viewModel: appState.settingsViewModel)
        }
    }

    private func reload() async {
        await appState.settingsViewModel.refresh()
        await appState.knowledgeViewModel.refresh()
        await appState.pluginsViewModel.refresh()
        await appState.automationDashboard.refresh()
        await appState.refreshConnectionStatus(force: false)
    }

    @ViewBuilder
    private func sidebarRow(for section: AppSection) -> some View {
    let isSelected = section == selection
    let isHovered = hoveredSection == section
        let density = appState.preferences.sidebarDensity
        let verticalPadding: CGFloat = density == .compact ? 6 : 10
        let iconSize: CGFloat = density == .compact ? 28 : 32

        HStack(spacing: 14) {
            ZStack {
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(isSelected ? theme.accent.opacity(0.22) : theme.listSelection.opacity(0.25))
                    .frame(width: iconSize, height: iconSize)
                Image(systemName: section.icon)
                    .foregroundColor(isSelected ? theme.accent : theme.primaryText)
                    .font(.system(size: density == .compact ? 14 : 16, weight: .semibold))
            }

            VStack(alignment: .leading, spacing: 2) {
                Text(section.title)
                    .font(.system(density == .compact ? .callout : .headline, design: .rounded, weight: .medium))
                    .foregroundColor(theme.primaryText)
                Text(section.caption)
                    .font(.system(.caption, design: .rounded))
                    .foregroundColor(theme.secondaryText.opacity(0.8))
                    .lineLimit(1)
            }

            Spacer(minLength: 8)

            if section == .knowledge, let documents = appState.connectionStatus.health?.documentCount,
               documents > 0 {
                sidebarBadge(text: "\(documents)")
            }

            if section == .automation, appState.preferences.showAutomationStatus {
                statusDot
            }
        }
        .padding(.vertical, verticalPadding)
        .padding(.horizontal, 10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(isSelected ? theme.listSelection : (isHovered ? theme.listSelection.opacity(0.45) : Color.clear))
                .overlay(
                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .stroke(isSelected ? theme.accent.opacity(0.45) : (isHovered ? theme.accent.opacity(0.25) : Color.white.opacity(0.08)), lineWidth: isSelected ? 1.5 : 1)
                )
        )
        .animation(.easeInOut(duration: 0.18), value: selection)
        .animation(.easeInOut(duration: 0.18), value: hoveredSection)
        .contentShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
#if os(macOS)
        .onHover { hovering in
            hoveredSection = hovering ? section : (hoveredSection == section ? nil : hoveredSection)
        }
#endif
    }

    private var sidebarHeader: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .center, spacing: 12) {
                Image(systemName: "sparkles.rectangle.stack")
                    .font(.system(size: 20, weight: .semibold))
                    .foregroundColor(theme.accent)
                VStack(alignment: .leading, spacing: 2) {
                    Text("OnDevice AI")
                        .font(.system(.headline, design: .rounded, weight: .semibold))
                        .foregroundColor(theme.primaryText)
                    Text("Choose where to work next")
                        .font(.system(.caption, design: .rounded))
                        .foregroundColor(theme.secondaryText.opacity(0.85))
                }
            }

            Divider()
                .overlay(theme.cardStroke)
                .padding(.top, 4)
        }
        .padding(.horizontal, 4)
    }

    private var detailHeader: some View {
        GlassContainer {
            VStack(alignment: .leading, spacing: 18) {
                HStack(alignment: .center, spacing: 16) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(greeting)
                            .font(.system(.title3, design: .rounded, weight: .semibold))
                            .foregroundColor(theme.primaryText)
                        Text("Here's what's happening across your automations")
                            .font(.system(.callout, design: .rounded))
                            .foregroundColor(theme.secondaryText)
                    }

                    Spacer()

                    HStack(spacing: 12) {
                        Button {
                            selection = .planner
                            appState.plannerViewModel.goal = ""
                        } label: {
                            Label("New plan", systemImage: "plus.circle")
                                .font(.system(.subheadline, design: .rounded))
                                .fontWeight(.medium)
                        }
                        .buttonStyle(GlassToolbarButtonStyle())

                        Button {
                            controlCenterPresented = true
                        } label: {
                            Label("Control center", systemImage: "slider.horizontal.3")
                                .font(.system(.subheadline, design: .rounded))
                                .fontWeight(.medium)
                        }
                        .buttonStyle(GlassToolbarButtonStyle())

                        Menu {
                            ForEach(ThemePreference.allCases) { preference in
                                Button {
                                    appState.applyTheme(preference, colorScheme: colorScheme)
                                } label: {
                                    Label(preference.title, systemImage: preference.iconName)
                                }
                            }
                        } label: {
                            Label("Theme", systemImage: "paintpalette")
                                .font(.system(.subheadline, design: .rounded))
                                .fontWeight(.medium)
                        }
                        .menuStyle(.borderlessButton)
                    }
                }

                HStack(spacing: 12) {
                    Image(systemName: "magnifyingglass")
                        .foregroundColor(theme.secondaryText)
                    TextField("Search tasks, notes, or automations", text: $globalSearch)
                        .textFieldStyle(.plain)
                        .foregroundColor(theme.primaryText)
                        .disableAutocorrection(true)
                        .onSubmit(handleGlobalSearch)
                    if globalSearch.isEmpty == false {
                        Button {
                            globalSearch = ""
                        } label: {
                            Image(systemName: "xmark.circle.fill")
                                .foregroundColor(theme.secondaryText.opacity(0.8))
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.vertical, 12)
                .padding(.horizontal, 16)
                .background(
                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .fill(theme.quickActionBackground.opacity(0.55))
                )
            }
        }
    }

    private var greeting: String {
        let hour = Calendar.current.component(.hour, from: Date())
        switch hour {
        case 5..<12: return "Good morning, operator"
        case 12..<17: return "Good afternoon, operator"
        case 17..<22: return "Good evening, operator"
        default: return "Burning the midnight oil?"
        }
    }

    private func handleGlobalSearch() {
        let trimmed = globalSearch.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.isEmpty == false else { return }
        selection = .knowledge
        appState.knowledgeViewModel.searchTerm = trimmed
        appState.knowledgeViewModel.performSearch()
    }

    private func sidebarBadge(text: String) -> some View {
        Text(text)
            .font(.system(.caption, design: .rounded, weight: .medium))
            .foregroundColor(theme.chipText)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(
                Capsule(style: .continuous)
                    .fill(theme.chipBackground)
            )
    }

    private var statusDot: some View {
        let color: Color
        if appState.connectionStatus.isChecking {
            color = theme.statusChecking
        } else if appState.connectionStatus.isConnected {
            color = theme.statusConnected
        } else {
            color = theme.statusError
        }
        return Circle()
            .fill(color)
            .frame(width: 10, height: 10)
            .overlay(
                Circle()
                    .stroke(theme.secondaryText.opacity(0.4), lineWidth: 1)
            )
    }
}
