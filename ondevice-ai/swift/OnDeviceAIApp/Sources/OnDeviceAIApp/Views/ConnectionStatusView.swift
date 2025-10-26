import SwiftUI

struct ConnectionStatusHero: View {
    let status: ConnectionStatus
    let backendState: BackendProcessManager.LaunchState
    var refreshAction: (() -> Void)?
    var openSettings: (() -> Void)?

    var body: some View {
        GlassContainer(cornerRadius: 30, padding: 24) {
            VStack(alignment: .leading, spacing: 14) {
                HStack(alignment: .center, spacing: 18) {
                    statusIndicator
                    VStack(alignment: .leading, spacing: 6) {
                        Text(status.stateTitle)
                            .font(.system(.title3, design: .rounded, weight: .semibold))
                            .foregroundColor(.white)
                        Text(status.stateDetail)
                            .font(.system(.callout, design: .rounded))
                            .foregroundColor(.white.opacity(0.78))
                            .lineLimit(2)
                        if let backendDetail = backendStateDetail {
                            Text(backendDetail)
                                .font(.system(.caption, design: .rounded))
                                .foregroundColor(.white.opacity(0.65))
                                .lineLimit(2)
                        }
                    }
                    Spacer()
                    statusMetrics
                    heroButtons
                }
                if let error = status.errorMessage, status.isConnected == false {
                    Text(error)
                        .font(.system(.footnote, design: .rounded))
                        .foregroundColor(.yellow.opacity(0.9))
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
        }
    }

    private var statusIndicator: some View {
        ZStack {
            Circle()
                .fill(indicatorColor.opacity(0.28))
                .frame(width: 54, height: 54)
            Circle()
                .fill(indicatorColor)
                .frame(width: 16, height: 16)
                .shadow(color: indicatorColor.opacity(0.7), radius: 6, x: 0, y: 2)
        }
        .overlay(alignment: .center) {
            if status.isChecking {
                ProgressView()
                    .progressViewStyle(.circular)
                    .tint(.white)
                    .frame(width: 54, height: 54)
            }
        }
        .accessibilityLabel(status.stateTitle)
    }

    private var statusMetrics: some View {
        VStack(alignment: .trailing, spacing: 10) {
            if let health = status.health {
                metricBadge(title: "Documents", value: "\(health.documentCount)")
            }
            if let lastUpdated = status.lastUpdated {
                Text("Updated \(lastUpdated, style: .relative) ago")
                    .font(.system(.caption, design: .rounded))
                    .foregroundColor(.white.opacity(0.6))
            }
        }
    }

    private func metricBadge(title: String, value: String) -> some View {
        VStack(alignment: .trailing, spacing: 4) {
            Text(title.uppercased())
                .font(.system(.caption2, design: .rounded))
                .foregroundColor(.white.opacity(0.6))
                .tracking(1.2)
            Text(value)
                .font(.system(.title2, design: .rounded, weight: .semibold))
                .foregroundColor(.white)
        }
        .padding(.vertical, 8)
        .padding(.horizontal, 12)
        .background(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(Color.white.opacity(0.08))
                .overlay(
                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .stroke(Color.white.opacity(0.12), lineWidth: 1)
                )
        )
    }

    private var heroButtons: some View {
        HStack(spacing: 12) {
            if let refreshAction {
                Button(action: refreshAction) {
                    Label("Refresh", systemImage: "arrow.clockwise")
                        .font(.system(.subheadline, design: .rounded, weight: .medium))
                }
                .buttonStyle(GlassToolbarButtonStyle())
            }
            if let openSettings {
                Button(action: openSettings) {
                    Label("Open settings", systemImage: "gearshape")
                        .font(.system(.subheadline, design: .rounded))
                }
                .buttonStyle(GlassToolbarButtonStyle())
            }
        }
    }

    private var indicatorColor: Color {
        if case .launching = backendState { return .blue.opacity(0.8) }
        if status.isChecking { return .blue.opacity(0.8) }
        if status.isConnected { return .green.opacity(0.8) }
        return .red.opacity(0.9)
    }

    private var backendStateDetail: String? {
        switch backendState {
        case .stopped:
            return "Local daemon is not running. It will auto-start when needed."
        case .launching:
            return "Launching the bundled Python automation daemon…"
        case .running:
            return nil
        case let .failed(message):
            return "Daemon launch failed: \(message)"
        }
    }
}

struct ConnectionStatusBadge: View {
    let status: ConnectionStatus

    var body: some View {
        HStack(spacing: 12) {
            Circle()
                .fill(indicatorColor)
                .frame(width: 10, height: 10)
            VStack(alignment: .leading, spacing: 4) {
                Text(status.stateTitle)
                    .font(.system(.subheadline, design: .rounded, weight: .medium))
                    .foregroundColor(.white)
                Text(status.stateDetail)
                    .font(.system(.caption, design: .rounded))
                    .foregroundColor(.white.opacity(0.65))
                    .lineLimit(2)
            }
            Spacer()
            if let health = status.health {
                Text("\(health.documentCount) docs")
                    .font(.system(.caption, design: .rounded))
                    .foregroundColor(.white.opacity(0.68))
            }
        }
        .padding(14)
        .background(Color.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
    }

    private var indicatorColor: Color {
        if status.isChecking { return .blue.opacity(0.8) }
        if status.isConnected { return .green.opacity(0.8) }
        return .yellow.opacity(0.9)
    }
}
