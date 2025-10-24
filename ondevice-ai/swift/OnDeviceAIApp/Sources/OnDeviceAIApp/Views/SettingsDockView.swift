import SwiftUI

struct SettingsDockView: View {
    @EnvironmentObject private var appState: AppState
    @ObservedObject var viewModel: SettingsViewModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                connectionSection
                healthSection
            }
            .padding(.bottom, 36)
        }
        .scrollIndicators(.hidden)
        .foregroundColor(.white)
        .task {
            if viewModel.health == nil && viewModel.isRefreshing == false {
                await viewModel.refreshHealth()
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
                                appState.refreshAll()
                            }
                        }
                    } label: {
                        Label("Apply", systemImage: "checkmark.circle")
                            .font(.system(.headline, design: .rounded))
                    }
                    .buttonStyle(GlassToolbarButtonStyle())

                    Button {
                        Task { await viewModel.refreshHealth() }
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
}
