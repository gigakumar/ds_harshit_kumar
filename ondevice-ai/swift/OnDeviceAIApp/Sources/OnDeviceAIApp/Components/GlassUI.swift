import SwiftUI

struct GlassBackground<Content: View>: View {
    var content: () -> Content
    @Environment(\.themeDescriptor) private var theme
    @EnvironmentObject private var appState: AppState

    var body: some View {
        ZStack {
            LinearGradient(
                colors: theme.backgroundGradient,
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .ignoresSafeArea()

            if appState.preferences.animateBackground {
                AnimatedGlassBlobs()
                    .blendMode(.plusLighter)
                    .ignoresSafeArea()
            }

            GrainOverlay()
                .allowsHitTesting(false)

            content()
        }
        .animation(.easeInOut(duration: 0.6), value: appState.preferences.animateBackground)
    }
}

struct GlassContainer<Content: View>: View {
    var cornerRadius: CGFloat = 26
    var padding: CGFloat = 20
    var content: () -> Content
    @Environment(\.themeDescriptor) private var theme

    var body: some View {
        content()
            .padding(padding)
            .background(
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .fill(theme.blurMaterial)
                    .overlay(
                        RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                            .stroke(
                                LinearGradient(
                                    colors: [theme.cardStroke.opacity(0.9), theme.cardStroke.opacity(0.4)],
                                    startPoint: .topLeading,
                                    endPoint: .bottomTrailing
                                ),
                                lineWidth: 1
                            )
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                            .stroke(theme.accent.opacity(0.12), lineWidth: 0.9)
                            .blendMode(.screen)
                    )
                    .shadow(color: theme.cardShadow, radius: 20, x: 0, y: 18)
            )
    }
}

struct GlassSectionHeader: View {
    let title: String
    let systemImage: String
    @Environment(\.themeDescriptor) private var theme

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: systemImage)
                .symbolVariant(.fill)
                .font(.system(size: 18, weight: .semibold))
                .foregroundStyle(theme.accent)
            Text(title.uppercased())
                .font(.system(.caption, design: .rounded, weight: .medium))
                .foregroundColor(theme.secondaryText)
                .tracking(1.5)
        }
        .padding(.bottom, 4)
    }
}

struct GlassTag: View {
    let text: String
    var tint: Color = .white.opacity(0.4)
    @Environment(\.themeDescriptor) private var theme

    var body: some View {
        Text(text)
            .font(.system(.caption, design: .rounded))
            .padding(.vertical, 4)
            .padding(.horizontal, 10)
            .background(
                Capsule().fill(tint).blendMode(.plusLighter)
            )
            .foregroundColor(theme.chipText)
    }
}

struct GlassToolbarButtonStyle: ButtonStyle {
    @Environment(\.themeDescriptor) private var theme

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .padding(.vertical, 8)
            .padding(.horizontal, 14)
            .background(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(theme.blurMaterial)
                    .overlay(
                        RoundedRectangle(cornerRadius: 16, style: .continuous)
                            .stroke(
                                LinearGradient(
                                    colors: [theme.cardStroke.opacity(configuration.isPressed ? 1.4 : 1.0), theme.accent.opacity(configuration.isPressed ? 0.45 : 0.2)],
                                    startPoint: .topLeading,
                                    endPoint: .bottomTrailing
                                ),
                                lineWidth: 1.2
                            )
                    )
            )
            .foregroundColor(theme.primaryText)
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
            .animation(.spring(response: 0.35, dampingFraction: 0.8), value: configuration.isPressed)
    }
}

private struct AnimatedGlassBlobs: View {
    @Environment(\.themeDescriptor) private var theme

    var body: some View {
        TimelineView(.animation) { timeline in
            let time = timeline.date.timeIntervalSinceReferenceDate
            Canvas { context, size in
                context.addFilter(.blur(radius: 120))
                context.addFilter(.alphaThreshold(min: 0.15))

                let base = max(size.width, size.height)
                let blobs = animatedPositions(for: time, in: size)

                for (index, entry) in blobs.enumerated() {
                    let rect = CGRect(
                        x: entry.point.x - base * entry.scale / 2,
                        y: entry.point.y - base * entry.scale / 2,
                        width: base * entry.scale,
                        height: base * entry.scale
                    )
                    let gradient = Gradient(colors: blobColors[index % blobColors.count])
                    context.fill(
                        Path(ellipseIn: rect),
                        with: .linearGradient(gradient, startPoint: rect.origin, endPoint: CGPoint(x: rect.maxX, y: rect.maxY))
                    )
                }
            }
        }
        .opacity(0.9)
    }

    private var blobColors: [[Color]] {
        [
            [theme.accent.opacity(0.45), theme.quickActionBackground.opacity(0.4)],
            [theme.quickActionBackground.opacity(0.35), .clear],
            [theme.secondaryText.opacity(0.25), theme.accent.opacity(0.2)]
        ]
    }

    private func animatedPositions(for time: TimeInterval, in size: CGSize) -> [(point: CGPoint, scale: CGFloat)] {
        let width = size.width
        let height = size.height
        let x1 = width * 0.3 + CGFloat(sin(time / 7.5)) * width * 0.18
        let y1 = height * 0.25 + CGFloat(cos(time / 6.2)) * height * 0.18
        let x2 = width * 0.7 + CGFloat(cos(time / 9.8)) * width * 0.22
        let y2 = height * 0.65 + CGFloat(sin(time / 7.4)) * height * 0.16
        let x3 = width * 0.5 + CGFloat(sin(time / 5.4)) * width * 0.24
        let y3 = height * 0.5 + CGFloat(cos(time / 8.1)) * height * 0.2
        return [
            (CGPoint(x: x1, y: y1), 0.85),
            (CGPoint(x: x2, y: y2), 0.75),
            (CGPoint(x: x3, y: y3), 1.05)
        ]
    }
}

private struct GrainOverlay: View {
    var body: some View {
        GeometryReader { proxy in
            let size = proxy.size
            Canvas { context, canvasSize in
                let particleCount = Int((size.width * size.height) / 4200)
                for _ in 0..<particleCount {
                    let x = CGFloat.random(in: 0...canvasSize.width)
                    let y = CGFloat.random(in: 0...canvasSize.height)
                    let rect = CGRect(x: x, y: y, width: 1.2, height: 1.2)
                    context.fill(Path(ellipseIn: rect), with: .color(Color.white.opacity(0.08)))
                }
            }
            .blendMode(.softLight)
            .opacity(0.35)
            .ignoresSafeArea()
        }
    }
}

extension View {
    func glassCard(cornerRadius: CGFloat = 24) -> some View {
        modifier(GlassCardModifier(cornerRadius: cornerRadius))
    }

    func glassSection() -> some View {
        modifier(GlassSectionModifier())
    }
}

private struct GlassCardModifier: ViewModifier {
    let cornerRadius: CGFloat
    @Environment(\.themeDescriptor) private var theme

    func body(content: Content) -> some View {
        content
            .padding(20)
            .background(
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .fill(theme.blurMaterial)
                    .overlay(
                        RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                            .stroke(theme.cardStroke, lineWidth: 1)
                    )
            )
            .shadow(color: theme.cardShadow, radius: 18, x: 0, y: 12)
    }
}

private struct GlassSectionModifier: ViewModifier {
    func body(content: Content) -> some View {
        content
            .modifier(GlassCardModifier(cornerRadius: 28))
            .padding(.vertical, 6)
    }
}
