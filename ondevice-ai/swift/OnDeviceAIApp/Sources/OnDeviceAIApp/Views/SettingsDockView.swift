import SwiftUI

struct SettingsDockView: View {
    @EnvironmentObject private var appState: AppState
    @ObservedObject var viewModel: SettingsViewModel
    @Environment(\.themeDescriptor) private var theme
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                connectionSection
                permissionsSection
                modelSection
                appearanceSection
                healthSection
            }
            .padding(.bottom, 36)
        }
        .scrollIndicators(.hidden)
        .foregroundColor(theme.primaryText)
        .task {
            if viewModel.health == nil && viewModel.isRefreshing == false {
                await viewModel.refresh()
            }
        }
    }

    private var connectionSection: some View {
        GlassContainer {
            VStack(alignment: .leading, spacing: 16) {
                GlassSectionHeader(title: "Daemon connection", systemImage: "antenna.radiowaves.left.and.right")

                ConnectionStatusBadge(status: appState.connectionStatus)

                Text("Automation requests are routed through the local daemon bundled with the app. Advanced overrides are optional for custom deployments.")
                    .font(.system(.callout, design: .rounded))
                    .foregroundColor(theme.secondaryText)

                Toggle("Enable custom daemon URL", isOn: advancedConnectionBinding)
                    .toggleStyle(.switch)
                    .tint(theme.accent)
                    .onChange(of: appState.preferences.showAdvancedConnectionSettings) { _, isEnabled in
                        guard isEnabled == false else { return }
                        Task { @MainActor in
                            let defaultURL = "http://127.0.0.1:9000"
                            viewModel.baseURL = defaultURL
                            let success = await viewModel.applyBaseURL()
                            if success {
                                await viewModel.refresh()
                                appState.refreshAll()
                            }
                        }
                    }

                if appState.preferences.showAdvancedConnectionSettings {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Base URL override")
                            .font(.system(.caption, design: .rounded))
                            .foregroundColor(theme.secondaryText.opacity(0.8))
                        TextField("http://127.0.0.1:9000", text: $viewModel.baseURL)
                            .textFieldStyle(.plain)
                            .padding(14)
                            .background(theme.quickActionBackground.opacity(0.6), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                            .foregroundColor(theme.primaryText)
                            .onSubmit {
                                Task { @MainActor in
                                    let success = await viewModel.applyBaseURL()
                                    if success {
                                        appState.refreshAll()
                                    }
                                }
                            }
                        Text("Default endpoint is http://127.0.0.1:9000 when this override is disabled.")
                            .font(.system(.caption, design: .rounded))
                            .foregroundColor(theme.secondaryText.opacity(0.75))
                    }
                }

                HStack(spacing: 12) {
                    if appState.preferences.showAdvancedConnectionSettings {
                        Button {
                            Task { @MainActor in
                                let success = await viewModel.applyBaseURL()
                                if success {
                                    await viewModel.refresh()
                                    appState.refreshAll()
                                }
                            }
                        } label: {
                            Label("Apply", systemImage: "checkmark.circle")
                                .font(.system(.headline, design: .rounded))
                        }
                        .buttonStyle(GlassToolbarButtonStyle())
                    }

                    Button {
                        Task { await viewModel.refresh() }
                    } label: {
                        Label("Check health", systemImage: "waveform.path.ecg")
                            .font(.system(.subheadline, design: .rounded))
                    }
                    .buttonStyle(GlassToolbarButtonStyle())
                    .disabled(viewModel.isRefreshing)

                    if viewModel.isRefreshing {
                        ProgressView()
                            .progressViewStyle(.circular)
                            .tint(theme.accent)
                    }

                    Spacer()
                }

                if let error = viewModel.errorMessage {
                    HStack(spacing: 10) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundColor(.yellow)
                        Text(error)
                            .font(.footnote)
                            .foregroundColor(theme.secondaryText)
                    }
                }
            }
        }
    }

    private var permissionsSection: some View {
        GlassContainer {
            VStack(alignment: .leading, spacing: 16) {
                GlassSectionHeader(title: "Automation permissions", systemImage: "switch.2")
                VStack(alignment: .leading, spacing: 14) {
                    permissionToggle(
                        title: "Files & Folders",
                        subtitle: "Allow automations to read and write within your workspace.",
                        binding: Binding(
                            get: { viewModel.permissions.fileAccess },
                            set: { viewModel.updatePermission(\.fileAccess, to: $0) }
                        )
                    )

                    permissionToggle(
                        title: "Calendar",
                        subtitle: "Enable smart scheduling and availability automations.",
                        binding: Binding(
                            get: { viewModel.permissions.calendarAccess },
                            set: { viewModel.updatePermission(\.calendarAccess, to: $0) }
                        )
                    )

                    permissionToggle(
                        title: "Mail & Messages",
                        subtitle: "Allow drafting and sending responses using stored credentials.",
                        binding: Binding(
                            get: { viewModel.permissions.mailAccess },
                            set: { viewModel.updatePermission(\.mailAccess, to: $0) }
                        )
                    )

                    permissionToggle(
                        title: "Network",
                        subtitle: "Permit outbound requests for web research and APIs.",
                        binding: Binding(
                            get: { viewModel.permissions.networkAccess },
                            set: { viewModel.updatePermission(\.networkAccess, to: $0) }
                        )
                    )

                    permissionToggle(
                        title: "Browser Control",
                        subtitle: "Allow scripted browsing with the agentic web driver.",
                        binding: Binding(
                            get: { viewModel.permissions.browserAccess },
                            set: { viewModel.updatePermission(\.browserAccess, to: $0) }
                        )
                    )

                    permissionToggle(
                        title: "Shell Commands",
                        subtitle: "Grant access to run shell tasks in the sandbox.",
                        binding: Binding(
                            get: { viewModel.permissions.shellAccess },
                            set: { viewModel.updatePermission(\.shellAccess, to: $0) }
                        )
                    )

                    permissionToggle(
                        title: "Automation Scripts",
                        subtitle: "Enable apps and AppleScript automation for system tasks.",
                        binding: Binding(
                            get: { viewModel.permissions.automationAccess },
                            set: { viewModel.updatePermission(\.automationAccess, to: $0) }
                        )
                    )
                }
            }
        }
    }

    private var healthSection: some View {
        GlassContainer {
            VStack(alignment: .leading, spacing: 18) {
                GlassSectionHeader(title: "Health overview", systemImage: "heart.circle")
                if let health = viewModel.health {
                    VStack(alignment: .leading, spacing: 12) {
                        HStack(alignment: .center, spacing: 10) {
                            Circle()
                                .fill(health.ok ? theme.statusConnected : theme.statusError)
                                .frame(width: 12, height: 12)
                            Text(health.ok ? "Daemon reachable" : "Daemon offline")
                                .font(.system(.headline, design: .rounded))
                                .foregroundColor(theme.primaryText)
                        }
                        HStack {
                            Text("Indexed documents")
                                .font(.system(.callout, design: .rounded))
                                .foregroundColor(theme.secondaryText)
                            Spacer()
                            Text(String(health.documentCount))
                                .font(.system(.title2, design: .rounded))
                                .foregroundColor(theme.primaryText)
                        }
                    }
                } else if viewModel.isRefreshing {
                    ProgressView("Checking daemon status…")
                        .progressViewStyle(.circular)
                        .tint(theme.accent)
                } else {
                    Text("Health metrics will appear after contacting the daemon.")
                        .font(.footnote)
                        .foregroundColor(theme.secondaryText)
                }
            }
        }
    }

    private var modelSection: some View {
        GlassContainer {
            VStack(alignment: .leading, spacing: 18) {
                GlassSectionHeader(title: "Model profile", systemImage: "brain.head.profile")
                if let model = viewModel.modelConfiguration {
                    Text("Pick the default automation brain packaged with this install or connect to remote backends.")
                        .font(.system(.callout, design: .rounded))
                        .foregroundColor(theme.secondaryText)

                    HStack(alignment: .center, spacing: 12) {
                        GlassTag(text: model.backend.uppercased(), tint: Color.white.opacity(0.18))
                        if let runtimeURL = model.runtimeURL {
                            Text(runtimeURL)
                                .font(.system(.caption, design: .monospaced))
                                .foregroundColor(theme.secondaryText)
                                .lineLimit(1)
                        }
                    }

                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 16) {
                            ForEach(model.profiles) { profile in
                                VStack(alignment: .leading, spacing: 12) {
                                    HStack {
                                        Text(profile.label)
                                            .font(.system(.headline, design: .rounded))
                                        if profile.isSelected {
                                            GlassTag(text: "Selected", tint: Color.blue.opacity(0.4))
                                        }
                                    }
                                    Text(profile.description)
                                        .font(.system(.subheadline, design: .rounded))
                                        .foregroundColor(theme.secondaryText)
                                        .frame(maxWidth: .infinity, alignment: .leading)
                                    if profile.capabilities.isEmpty == false {
                                        HStack(spacing: 8) {
                                            ForEach(profile.capabilities, id: \.self) { capability in
                                                GlassTag(text: capability.uppercased(), tint: Color.white.opacity(0.15))
                                            }
                                        }
                                    }
                                    Button {
                                        viewModel.selectModel(profileID: profile.id)
                                    } label: {
                                        Label("Use profile", systemImage: profile.isSelected ? "checkmark.circle" : "arrow.triangle.2.circlepath")
                                            .font(.system(.footnote, design: .rounded))
                                    }
                                    .buttonStyle(GlassToolbarButtonStyle())
                                    .disabled(profile.isSelected || viewModel.isUpdatingModel)
                                }
                                .padding(18)
                                .frame(width: 260, alignment: .leading)
                                .background(theme.quickActionBackground.opacity(0.35), in: RoundedRectangle(cornerRadius: 22, style: .continuous))
                                .overlay(
                                    RoundedRectangle(cornerRadius: 22, style: .continuous)
                                        .stroke(profile.isSelected ? theme.accent.opacity(0.7) : theme.cardStroke, lineWidth: profile.isSelected ? 2 : 1)
                                )
                            }
                        }
                        .padding(.vertical, 4)
                    }

                    if viewModel.isUpdatingModel {
                        ProgressView("Switching model…")
                            .progressViewStyle(.circular)
                            .tint(theme.accent)
                    }
                } else {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Model configuration unavailable.")
                            .font(.system(.subheadline, design: .rounded))
                            .foregroundColor(theme.secondaryText)
                        Button {
                            Task { await viewModel.refresh() }
                        } label: {
                            Label("Retry", systemImage: "arrow.clockwise")
                                .font(.system(.footnote, design: .rounded))
                        }
                        .buttonStyle(GlassToolbarButtonStyle())
                    }
                }
            }
        }
    }

    private var appearanceSection: some View {
        GlassContainer {
            VStack(alignment: .leading, spacing: 18) {
                GlassSectionHeader(title: "Appearance", systemImage: "paintpalette")
                Text("Choose a theme and tweak layout preferences for the sidebar and background.")
                    .font(.system(.callout, design: .rounded))
                    .foregroundColor(theme.secondaryText)

                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 12) {
                        ForEach(ThemePreference.allCases) { preference in
                            Button {
                                appState.applyTheme(preference, colorScheme: colorScheme)
                            } label: {
                                VStack(alignment: .leading, spacing: 8) {
                                    Image(systemName: preference.iconName)
                                        .font(.system(size: 18, weight: .semibold))
                                    Text(preference.title)
                                        .font(.system(.subheadline, design: .rounded))
                                        .fontWeight(.semibold)
                                        .frame(maxWidth: .infinity, alignment: .leading)
                                    Text(preference.caption)
                                        .font(.system(.caption, design: .rounded))
                                        .foregroundColor(theme.secondaryText.opacity(0.8))
                                        .frame(maxWidth: .infinity, alignment: .leading)
                                }
                                .padding(.vertical, 14)
                                .padding(.horizontal, 16)
                                .frame(width: 200, alignment: .leading)
                                .background(theme.quickActionBackground.opacity(0.5), in: RoundedRectangle(cornerRadius: 22, style: .continuous))
                                .overlay(
                                    RoundedRectangle(cornerRadius: 22, style: .continuous)
                                        .stroke(preference == appState.themePreference ? theme.accent.opacity(0.7) : theme.cardStroke, lineWidth: preference == appState.themePreference ? 2 : 1)
                                )
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }

                Divider()
                    .background(theme.cardStroke)

                VStack(alignment: .leading, spacing: 14) {
                    Text("Sidebar density")
                        .font(.system(.subheadline, design: .rounded))
                        .fontWeight(.medium)
                        .foregroundColor(theme.secondaryText)
                    Picker("Sidebar density", selection: sidebarDensityBinding) {
                        ForEach(UserPreferences.SidebarDensity.allCases) { density in
                            Text(density.title).tag(density)
                        }
                    }
                    .pickerStyle(.segmented)

                    Toggle("Show automation status indicator", isOn: statusIndicatorBinding)
                        .toggleStyle(.switch)
                        .tint(theme.accent)

                    Toggle("Animate glass background", isOn: animatedBackgroundBinding)
                        .toggleStyle(.switch)
                        .tint(theme.accent)
                }
            }
        }
    }

    private func permissionToggle(title: String, subtitle: String, binding: Binding<Bool>) -> some View {
        Toggle(isOn: binding) {
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.system(.body, design: .rounded))
                    .foregroundColor(theme.primaryText)
                Text(subtitle)
                    .font(.system(.caption, design: .rounded))
                    .foregroundColor(theme.secondaryText)
            }
        }
        .tint(theme.accent)
    }

    private var sidebarDensityBinding: Binding<UserPreferences.SidebarDensity> {
        Binding(
            get: { appState.preferences.sidebarDensity },
            set: { newValue in appState.updatePreferences { $0.sidebarDensity = newValue } }
        )
    }

    private var statusIndicatorBinding: Binding<Bool> {
        Binding(
            get: { appState.preferences.showAutomationStatus },
            set: { newValue in appState.updatePreferences { $0.showAutomationStatus = newValue } }
        )
    }

    private var animatedBackgroundBinding: Binding<Bool> {
        Binding(
            get: { appState.preferences.animateBackground },
            set: { newValue in appState.updatePreferences { $0.animateBackground = newValue } }
        )
    }

    private var advancedConnectionBinding: Binding<Bool> {
        Binding(
            get: { appState.preferences.showAdvancedConnectionSettings },
            set: { newValue in appState.updatePreferences { $0.showAdvancedConnectionSettings = newValue } }
        )
    }
}
