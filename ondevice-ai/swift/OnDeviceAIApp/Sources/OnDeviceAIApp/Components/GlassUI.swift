import SwiftUI

struct GlassBackground<Content: View>: View {
    var content: () -> Content

    var body: some View {
        ZStack {
            LinearGradient(
                colors: [Color.blue.opacity(0.45), Color.purple.opacity(0.35), Color.black.opacity(0.65)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .ignoresSafeArea()

            RadialGradient(colors: [Color.white.opacity(0.25), Color.clear], center: .topTrailing, startRadius: 40, endRadius: 420)
                .blendMode(.screen)
                .ignoresSafeArea()

            content()
        }
    }
}

struct GlassContainer<Content: View>: View {
    var cornerRadius: CGFloat = 26
    var padding: CGFloat = 20
    var content: () -> Content

    var body: some View {
        content()
            .padding(padding)
            .background(
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .fill(.ultraThinMaterial)
                    .overlay(
                        RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                            .stroke(Color.white.opacity(0.18), lineWidth: 1)
                    )
                    .shadow(color: Color.black.opacity(0.25), radius: 18, x: 0, y: 14)
            )
    }
}

struct GlassSectionHeader: View {
    let title: String
    let systemImage: String

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: systemImage)
                .symbolVariant(.fill)
                .font(.system(size: 18, weight: .semibold))
                .foregroundStyle(.white.opacity(0.9))
            Text(title.uppercased())
                .font(.system(.caption, design: .rounded, weight: .medium))
                .foregroundColor(.white.opacity(0.75))
                .tracking(1.5)
        }
        .padding(.bottom, 4)
    }
}

struct GlassTag: View {
    let text: String
    var tint: Color = .white.opacity(0.4)

    var body: some View {
        Text(text)
            .font(.system(.caption, design: .rounded))
            .padding(.vertical, 4)
            .padding(.horizontal, 10)
            .background(
                Capsule().fill(tint).blendMode(.plusLighter)
            )
            .foregroundColor(.white)
    }
}

struct GlassToolbarButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .padding(.vertical, 8)
            .padding(.horizontal, 14)
            .background(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(.ultraThinMaterial)
                    .overlay(
                        RoundedRectangle(cornerRadius: 16, style: .continuous)
                            .stroke(Color.white.opacity(configuration.isPressed ? 0.4 : 0.2), lineWidth: 1.2)
                    )
            )
            .foregroundColor(.white)
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
            .animation(.spring(response: 0.35, dampingFraction: 0.8), value: configuration.isPressed)
    }
}

extension View {
    func glassCard(cornerRadius: CGFloat = 24) -> some View {
        self
            .padding(20)
            .background(
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .fill(.ultraThinMaterial)
                    .overlay(
                        RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                            .stroke(Color.white.opacity(0.18), lineWidth: 1)
                    )
            )
            .shadow(color: Color.black.opacity(0.22), radius: 18, x: 0, y: 12)
    }

    func glassSection() -> some View {
        self
            .glassCard(cornerRadius: 28)
            .padding(.vertical, 6)
    }
}
