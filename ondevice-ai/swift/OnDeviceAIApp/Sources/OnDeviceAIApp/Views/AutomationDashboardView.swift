import SwiftUI

struct AutomationDashboardView: View {
    @ObservedObject var viewModel: AutomationDashboardViewModel

    private let gridColumns = [
        GridItem(.adaptive(minimum: 220), spacing: 20)
    ]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                quickActions
                modelStatus
                permissionsSummary
                logSection
            }
            .padding(.bottom, 48)
        }
        .scrollIndicators(.hidden)
        .foregroundColor(.white)
        .task {
            await viewModel.refresh()
        }
    }

    private var quickActions: some View {
        GlassContainer {
            VStack(alignment: .leading, spacing: 20) {
                HStack {
                    GlassSectionHeader(title: "Quick automations", systemImage: "bolt.fill")
                    Spacer()
                    if viewModel.isRunningQuickAction {
                        ProgressView()
                            .progressViewStyle(.circular)
                            .tint(.white)
                    }
                }

                LazyVGrid(columns: gridColumns, spacing: 20) {
                    ForEach(viewModel.quickActions) { action in
                        Button {
                            viewModel.trigger(action: action)
                        } label: {
                            VStack(alignment: .leading, spacing: 10) {
                                HStack {
                                    Image(systemName: action.icon)
                                        .font(.system(size: 24, weight: .semibold))
                                        .symbolRenderingMode(.palette)
                                        .foregroundStyle(.white, Color.white.opacity(0.4))
                                    Spacer()
                                    Image(systemName: "arrow.forward.circle.fill")
                                        .font(.title3)
                                        .foregroundColor(.white.opacity(0.75))
                                }
                                Text(action.title)
                                    .font(.system(.title3, design: .rounded, weight: .semibold))
                                    .foregroundColor(.white)
                                Text(action.subtitle)
                                    .font(.system(.footnote, design: .rounded))
                                    .foregroundColor(.white.opacity(0.75))
                                    .multilineTextAlignment(.leading)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(18)
                            .background(Color.white.opacity(0.05), in: RoundedRectangle(cornerRadius: 24, style: .continuous))
                            .overlay(
                                RoundedRectangle(cornerRadius: 24, style: .continuous)
                                    .stroke(Color.white.opacity(0.12), lineWidth: 1)
                            )
                        }
                        .buttonStyle(.plain)
                        .disabled(viewModel.isRunningQuickAction)
                    }
                }

                if let status = viewModel.statusMessage {
                    Text(status)
                        .font(.footnote)
                        .foregroundColor(.white.opacity(0.8))
                }
            }
        }
    }

    private var modelStatus: some View {
        GlassContainer {
            VStack(alignment: .leading, spacing: 16) {
                GlassSectionHeader(title: "Model status", systemImage: "cpu")
                if let summary = viewModel.modelSummary {
                    HStack(alignment: .center, spacing: 16) {
                        GlassTag(text: summary.backend.uppercased(), tint: Color.white.opacity(0.18))
                        if let runtime = summary.runtimeURL {
                            Text(runtime)
                                .font(.system(.caption, design: .monospaced))
                                .foregroundColor(.white.opacity(0.7))
                                .lineLimit(1)
                        }
                        Spacer()
                        if let active = summary.profiles.first(where: { $0.isSelected }) {
                            VStack(alignment: .trailing, spacing: 6) {
                                Text(active.label)
                                    .font(.system(.headline, design: .rounded))
                                Text(active.description)
                                    .font(.system(.caption, design: .rounded))
                                    .foregroundColor(.white.opacity(0.7))
                                    .multilineTextAlignment(.trailing)
                                if let environments = active.requires?.environment, environments.isEmpty == false {
                                    HStack(spacing: 8) {
                                        ForEach(environments, id: \.self) { item in
                                            GlassTag(text: item, tint: Color.white.opacity(0.12))
                                        }
                                    }
                                }
                                if active.capabilities.isEmpty == false {
                                    HStack(spacing: 8) {
                                        ForEach(active.capabilities, id: \.self) { capability in
                                            GlassTag(text: capability.uppercased(), tint: Color.white.opacity(0.12))
                                        }
                                    }
                                }
                            }
                            .frame(maxWidth: 260, alignment: .trailing)
                        }
                    }
                } else {
                    Text("Model configuration unavailable. Verify the daemon is running.")
                        .font(.system(.footnote, design: .rounded))
                        .foregroundColor(.white.opacity(0.75))
                }
            }
        }
    }

    private var permissionsSummary: some View {
        GlassContainer {
            VStack(alignment: .leading, spacing: 16) {
                GlassSectionHeader(title: "Permission footprint", systemImage: "lock.shield")
                let permissions = viewModel.permissions
                HStack(spacing: 18) {
                    permissionBadge(title: "Files", icon: "folder", enabled: permissions.fileAccess)
                    permissionBadge(title: "Calendar", icon: "calendar", enabled: permissions.calendarAccess)
                    permissionBadge(title: "Mail", icon: "envelope", enabled: permissions.mailAccess)
                    Spacer(minLength: 0)
                }
                Text("Fine-tune in Settings → Automation permissions.")
                    .font(.system(.caption, design: .rounded))
                    .foregroundColor(.white.opacity(0.65))
            }
        }
    }

    private func permissionBadge(title: String, icon: String, enabled: Bool) -> some View {
        VStack(spacing: 8) {
            Image(systemName: icon)
                .font(.system(size: 24, weight: .semibold))
                .foregroundColor(enabled ? .green : .white.opacity(0.5))
            Text(title)
                .font(.system(.footnote, design: .rounded))
            Text(enabled ? "Allowed" : "Blocked")
                .font(.system(.caption, design: .rounded))
                .foregroundColor(enabled ? .green.opacity(0.7) : .white.opacity(0.45))
        }
        .frame(width: 120, height: 100)
        .background(Color.white.opacity(0.05), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(enabled ? Color.green.opacity(0.4) : Color.white.opacity(0.1), lineWidth: 1)
        )
    }

    private var logSection: some View {
        GlassContainer {
            VStack(alignment: .leading, spacing: 18) {
                GlassSectionHeader(title: "Automation log", systemImage: "clock.arrow.circlepath")
                if viewModel.automationLog.isEmpty {
                    Text("No automation events captured yet.")
                        .font(.footnote)
                        .foregroundColor(.white.opacity(0.75))
                } else {
                    ForEach(viewModel.automationLog) { event in
                        VStack(alignment: .leading, spacing: 6) {
                            HStack {
                                Text(event.type.capitalized)
                                    .font(.system(.headline, design: .rounded))
                                Spacer()
                                Text(event.ts, style: .time)
                                    .font(.caption)
                                    .foregroundColor(.white.opacity(0.58))
                            }
                            if event.payload.isEmpty == false {
                                Text(event.payload.map { "\($0.key): \($0.value)" }.sorted().joined(separator: ", "))
                                    .font(.system(.caption, design: .monospaced))
                                    .foregroundColor(.white.opacity(0.78))
                                    .lineLimit(3)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(14)
                        .background(Color.white.opacity(0.05), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                    }
                }
            }
        }
    }
}
