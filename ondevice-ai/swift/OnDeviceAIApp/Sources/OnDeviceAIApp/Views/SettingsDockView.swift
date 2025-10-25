import SwiftUI

struct SettingsDockView: View {
    @EnvironmentObject private var appState: AppState
    @ObservedObject var viewModel: SettingsViewModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                connectionSection
                permissionsSection
                modelSection
                healthSection
            }
            .padding(.bottom, 36)
        }
        .scrollIndicators(.hidden)
        .foregroundColor(.white)
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

                Text("Automation requests are routed through the local daemon. Update the base URL if you're running it on another host.")
                    .font(.system(.callout, design: .rounded))
                    .foregroundColor(.white.opacity(0.78))

                VStack(alignment: .leading, spacing: 12) {
                    Text("Base URL")
                        .font(.system(.caption, design: .rounded))
                        .foregroundColor(.white.opacity(0.6))
                    TextField("http://127.0.0.1:9000", text: $viewModel.baseURL)
                        .textFieldStyle(.plain)
                        .padding(14)
                        .background(Color.white.opacity(0.08), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                        .foregroundColor(.white)
                        .onSubmit {
                            Task { @MainActor in
                                let success = await viewModel.applyBaseURL()
                                if success {
                                    appState.refreshAll()
                                }
                            }
                        }
                }

                HStack(spacing: 12) {
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
                            .tint(.white)
                    }

                    Spacer()
                }

                if let error = viewModel.errorMessage {
                    HStack(spacing: 10) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundColor(.yellow)
                        Text(error)
                            .font(.footnote)
                            .foregroundColor(.white.opacity(0.85))
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
                    Toggle(isOn: Binding(
                        get: { viewModel.permissions.fileAccess },
                        set: { viewModel.updatePermission(\.fileAccess, to: $0) }
                    )) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Files & Folders")
                                .font(.system(.body, design: .rounded))
                            Text("Allow automations to read and write within your workspace.")
                                .font(.system(.caption, design: .rounded))
                                .foregroundColor(.white.opacity(0.68))
                        }
                    }

                    Toggle(isOn: Binding(
                        get: { viewModel.permissions.calendarAccess },
                        set: { viewModel.updatePermission(\.calendarAccess, to: $0) }
                    )) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Calendar")
                                .font(.system(.body, design: .rounded))
                            Text("Enable smart scheduling and availability automations.")
                                .font(.system(.caption, design: .rounded))
                                .foregroundColor(.white.opacity(0.68))
                        }
                    }

                    Toggle(isOn: Binding(
                        get: { viewModel.permissions.mailAccess },
                        set: { viewModel.updatePermission(\.mailAccess, to: $0) }
                    )) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Mail & Messages")
                                .font(.system(.body, design: .rounded))
                            Text("Allow drafting and sending responses using stored credentials.")
                                .font(.system(.caption, design: .rounded))
                                .foregroundColor(.white.opacity(0.68))
                        }
                    }
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
                                .fill(health.ok ? Color.green.opacity(0.7) : Color.red.opacity(0.8))
                                .frame(width: 12, height: 12)
                            Text(health.ok ? "Daemon reachable" : "Daemon offline")
                                .font(.system(.headline, design: .rounded))
                                .foregroundColor(.white)
                        }
                        HStack {
                            Text("Indexed documents")
                                .font(.system(.callout, design: .rounded))
                                .foregroundColor(.white.opacity(0.72))
                            Spacer()
                            Text(String(health.documentCount))
                                .font(.system(.title2, design: .rounded))
                                .foregroundColor(.white)
                        }
                    }
                } else if viewModel.isRefreshing {
                    ProgressView("Checking daemon status…")
                        .progressViewStyle(.circular)
                        .tint(.white)
                } else {
                    Text("Health metrics will appear after contacting the daemon.")
                        .font(.footnote)
                        .foregroundColor(.white.opacity(0.75))
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
                        .foregroundColor(.white.opacity(0.75))

                    HStack(alignment: .center, spacing: 12) {
                        GlassTag(text: model.backend.uppercased(), tint: Color.white.opacity(0.18))
                        if let runtimeURL = model.runtimeURL {
                            Text(runtimeURL)
                                .font(.system(.caption, design: .monospaced))
                                .foregroundColor(.white.opacity(0.7))
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
                                        .foregroundColor(.white.opacity(0.75))
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
                                .background(Color.white.opacity(0.05), in: RoundedRectangle(cornerRadius: 22, style: .continuous))
                                .overlay(
                                    RoundedRectangle(cornerRadius: 22, style: .continuous)
                                        .stroke(profile.isSelected ? Color.blue.opacity(0.6) : Color.white.opacity(0.12), lineWidth: profile.isSelected ? 2 : 1)
                                )
                            }
                        }
                        .padding(.vertical, 4)
                    }

                    if viewModel.isUpdatingModel {
                        ProgressView("Switching model…")
                            .progressViewStyle(.circular)
                            .tint(.white)
                    }
                } else {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Model configuration unavailable.")
                            .font(.system(.subheadline, design: .rounded))
                            .foregroundColor(.white.opacity(0.7))
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
}
