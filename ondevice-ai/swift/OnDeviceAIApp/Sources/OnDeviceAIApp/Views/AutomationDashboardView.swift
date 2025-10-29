import SwiftUI

struct AutomationDashboardView: View {
    @ObservedObject var viewModel: AutomationDashboardViewModel
    @Environment(\.themeDescriptor) private var theme
    @State private var hoveredQuickActionID: UUID?

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
        .foregroundColor(theme.primaryText)
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
                            .tint(theme.accent)
                    }
                }

                metricsRow

                LazyVGrid(columns: gridColumns, spacing: 20) {
                    ForEach(viewModel.quickActions) { action in
                        let isHovered = hoveredQuickActionID == action.id
                        Button {
                            viewModel.trigger(action: action)
                        } label: {
                            VStack(alignment: .leading, spacing: 10) {
                                HStack {
                                    Image(systemName: action.icon)
                                        .font(.system(size: 24, weight: .semibold))
                                        .symbolRenderingMode(.palette)
                                        .foregroundStyle(theme.accent, theme.accent.opacity(0.35))
                                    Spacer()
                                    Image(systemName: "arrow.forward.circle.fill")
                                        .font(.title3)
                                        .foregroundColor(theme.secondaryText)
                                }
                                Text(action.title)
                                    .font(.system(.title3, design: .rounded, weight: .semibold))
                                    .foregroundColor(theme.primaryText)
                                Text(action.subtitle)
                                    .font(.system(.footnote, design: .rounded))
                                    .foregroundColor(theme.secondaryText)
                                    .multilineTextAlignment(.leading)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(18)
                            .background(
                                RoundedRectangle(cornerRadius: 24, style: .continuous)
                                    .fill(theme.quickActionBackground.opacity(isHovered ? 0.55 : 0.38))
                            )
                            .overlay(
                                RoundedRectangle(cornerRadius: 24, style: .continuous)
                                    .stroke(
                                        LinearGradient(
                                            colors: [theme.accent.opacity(isHovered ? 0.35 : 0.18), theme.cardStroke],
                                            startPoint: .topLeading,
                                            endPoint: .bottomTrailing
                                        ),
                                        lineWidth: 1
                                    )
                            )
                        }
                        .buttonStyle(.plain)
                        .disabled(viewModel.isRunningQuickAction)
#if os(macOS)
                        .onHover { hovering in
                            hoveredQuickActionID = hovering ? action.id : (hoveredQuickActionID == action.id ? nil : hoveredQuickActionID)
                        }
#endif
                        .animation(.easeInOut(duration: 0.2), value: isHovered)
                    }
                }

                if let status = viewModel.statusMessage {
                    Text(status)
                        .font(.footnote)
                        .foregroundColor(theme.secondaryText)
                }
            }
        }
    }

    private var metricsRow: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 12) {
                metricChip(icon: "bolt.badge.checkmark", title: "Runs today", value: logCountText, tint: theme.accent)
                metricChip(icon: "sparkles", title: "Quick automations", value: "\(viewModel.quickActions.count)", tint: theme.statusChecking)
                metricChip(icon: "lock.circle", title: "Permissions on", value: "\(enabledPermissions)", tint: theme.statusConnected)
            }
            .padding(.vertical, 4)
        }
    }

    private func metricChip(icon: String, title: String, value: String, tint: Color) -> some View {
        HStack(alignment: .center, spacing: 12) {
            ZStack {
                Circle()
                    .fill(tint.opacity(0.18))
                    .frame(width: 36, height: 36)
                Image(systemName: icon)
                    .foregroundColor(tint)
                    .font(.system(size: 16, weight: .semibold))
            }

            VStack(alignment: .leading, spacing: 2) {
                Text(title.uppercased())
                    .font(.system(.caption2, design: .rounded))
                    .foregroundColor(theme.secondaryText)
                    .tracking(0.8)
                Text(value)
                    .font(.system(.title3, design: .rounded))
                    .fontWeight(.semibold)
                    .foregroundColor(theme.primaryText)
            }
        }
        .padding(.vertical, 12)
        .padding(.horizontal, 16)
        .background(
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .fill(theme.quickActionBackground.opacity(0.45))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .stroke(tint.opacity(0.35), lineWidth: 1)
        )
    }

    private var logCountText: String {
        let count = viewModel.automationLog.count
        return count == 0 ? "—" : "\(count)"
    }

    private var enabledPermissions: Int {
        let permissions = viewModel.permissions
        return [
            permissions.fileAccess,
            permissions.calendarAccess,
            permissions.mailAccess,
            permissions.networkAccess,
            permissions.browserAccess,
            permissions.shellAccess,
            permissions.automationAccess
        ].filter { $0 }.count
    }

    private var modelStatus: some View {
        GlassContainer {
            VStack(alignment: .leading, spacing: 16) {
                GlassSectionHeader(title: "Model status", systemImage: "cpu")
                if let summary = viewModel.modelSummary {
                    HStack(alignment: .center, spacing: 16) {
                        GlassTag(text: summary.backend.uppercased(), tint: theme.quickActionBackground.opacity(0.45))
                        if let runtime = summary.runtimeURL {
                            Text(runtime)
                                .font(.system(.caption, design: .monospaced))
                                .foregroundColor(theme.secondaryText)
                                .lineLimit(1)
                        }
                        Spacer()
                        if let active = summary.profiles.first(where: { $0.isSelected }) {
                            VStack(alignment: .trailing, spacing: 6) {
                                Text(active.label)
                                    .font(.system(.headline, design: .rounded))
                                    .foregroundColor(theme.primaryText)
                                Text(active.description)
                                    .font(.system(.caption, design: .rounded))
                                    .foregroundColor(theme.secondaryText)
                                    .multilineTextAlignment(.trailing)
                                if let environments = active.requires?.environment, environments.isEmpty == false {
                                    HStack(spacing: 8) {
                                        ForEach(environments, id: \.self) { item in
                                            GlassTag(text: item, tint: theme.quickActionBackground.opacity(0.35))
                                        }
                                    }
                                }
                                if active.capabilities.isEmpty == false {
                                    HStack(spacing: 8) {
                                        ForEach(active.capabilities, id: \.self) { capability in
                                            GlassTag(text: capability.uppercased(), tint: theme.quickActionBackground.opacity(0.35))
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
                        .foregroundColor(theme.secondaryText)
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
                    .foregroundColor(theme.secondaryText)
            }
        }
    }

    private func permissionBadge(title: String, icon: String, enabled: Bool) -> some View {
        VStack(spacing: 8) {
            Image(systemName: icon)
                .font(.system(size: 24, weight: .semibold))
                .foregroundColor(enabled ? theme.statusConnected : theme.secondaryText)
            Text(title)
                .font(.system(.footnote, design: .rounded))
                .foregroundColor(theme.primaryText)
            Text(enabled ? "Allowed" : "Blocked")
                .font(.system(.caption, design: .rounded))
                .foregroundColor(enabled ? theme.statusConnected.opacity(0.85) : theme.secondaryText)
        }
        .frame(width: 120, height: 100)
        .background(theme.quickActionBackground.opacity(0.35), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(enabled ? theme.statusConnected.opacity(0.45) : theme.cardStroke, lineWidth: 1)
        )
    }

    private var logSection: some View {
        GlassContainer {
            VStack(alignment: .leading, spacing: 18) {
                GlassSectionHeader(title: "Automation log", systemImage: "clock.arrow.circlepath")
                if viewModel.automationLog.isEmpty {
                    Text("No automation events captured yet.")
                        .font(.footnote)
                        .foregroundColor(theme.secondaryText)
                } else {
                    ForEach(viewModel.automationLog) { event in
                        VStack(alignment: .leading, spacing: 6) {
                            HStack {
                                Text(event.type.capitalized)
                                    .font(.system(.headline, design: .rounded))
                                Spacer()
                                Text(event.ts, style: .time)
                                    .font(.caption)
                                    .foregroundColor(theme.secondaryText)
                            }
                            if event.payload.isEmpty == false {
                                Text(event.payload.map { "\($0.key): \($0.value)" }.sorted().joined(separator: ", "))
                                    .font(.system(.caption, design: .monospaced))
                                    .foregroundColor(theme.secondaryText)
                                    .lineLimit(3)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(14)
                        .background(theme.quickActionBackground.opacity(0.32), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                    }
                }
            }
        }
    }
}
