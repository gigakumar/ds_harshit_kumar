import SwiftUI

enum ThemePreference: String, CaseIterable, Identifiable {
    case system
    case midnight
    case lightBlue
    case sunset

    var id: String { rawValue }

    var title: String {
        switch self {
        case .system: return "Match System"
        case .midnight: return "Midnight"
        case .lightBlue: return "Lightwave"
        case .sunset: return "Sunset Glow"
        }
    }

    var caption: String {
        switch self {
        case .system: return "Follow macOS appearance"
        case .midnight: return "Deep glass dark mode"
        case .lightBlue: return "Bright ice-blue workspace"
        case .sunset: return "Warm gradient with bold accents"
        }
    }

    var iconName: String {
        switch self {
        case .system: return "macwindow"
        case .midnight: return "moon.stars"
        case .lightBlue: return "sun.max"
        case .sunset: return "sunset"
        }
    }
}

struct ThemeDescriptor {
    let preference: ThemePreference
    let backgroundGradient: [Color]
    let primaryText: Color
    let secondaryText: Color
    let accent: Color
    let cardStroke: Color
    let chipBackground: Color
    let chipText: Color
    let quickActionBackground: Color
    let quickActionStroke: Color
    let cardShadow: Color
    let sidebarBackground: Color
    let listSelection: Color
    let statusChecking: Color
    let statusConnected: Color
    let statusError: Color

    var blurMaterial: Material {
        preference == .lightBlue ? .thinMaterial : .ultraThinMaterial
    }
}

extension ThemeDescriptor {
    static let midnight = ThemeDescriptor(
        preference: .midnight,
        backgroundGradient: [
            Color(red: 25/255, green: 35/255, blue: 82/255).opacity(0.92),
            Color(red: 49/255, green: 24/255, blue: 92/255).opacity(0.82),
            Color.black.opacity(0.86)
        ],
        primaryText: Color.white,
        secondaryText: Color.white.opacity(0.75),
        accent: Color.cyan,
        cardStroke: Color.white.opacity(0.16),
        chipBackground: Color.white.opacity(0.14),
        chipText: Color.white,
        quickActionBackground: Color.white.opacity(0.07),
        quickActionStroke: Color.white.opacity(0.12),
        cardShadow: Color.black.opacity(0.26),
        sidebarBackground: Color.white.opacity(0.04),
        listSelection: Color.white.opacity(0.18),
        statusChecking: Color.blue.opacity(0.85),
        statusConnected: Color.green.opacity(0.78),
        statusError: Color.red.opacity(0.82)
    )

    static let lightBlue = ThemeDescriptor(
        preference: .lightBlue,
        backgroundGradient: [
            Color(red: 210/255, green: 231/255, blue: 248/255),
            Color(red: 188/255, green: 215/255, blue: 241/255),
            Color(red: 155/255, green: 193/255, blue: 235/255)
        ],
        primaryText: Color(red: 20/255, green: 33/255, blue: 61/255),
        secondaryText: Color(red: 45/255, green: 64/255, blue: 89/255).opacity(0.76),
        accent: Color(red: 18/255, green: 114/255, blue: 229/255),
        cardStroke: Color(red: 64/255, green: 119/255, blue: 173/255).opacity(0.25),
        chipBackground: Color(red: 255/255, green: 255/255, blue: 255/255).opacity(0.6),
        chipText: Color(red: 20/255, green: 33/255, blue: 61/255),
        quickActionBackground: Color.white.opacity(0.7),
        quickActionStroke: Color(red: 135/255, green: 185/255, blue: 239/255).opacity(0.4),
        cardShadow: Color(red: 155/255, green: 193/255, blue: 235/255).opacity(0.45),
        sidebarBackground: Color.white.opacity(0.6),
        listSelection: Color(red: 110/255, green: 170/255, blue: 231/255).opacity(0.4),
        statusChecking: Color(red: 0/255, green: 122/255, blue: 255/255).opacity(0.9),
        statusConnected: Color(red: 38/255, green: 172/255, blue: 65/255).opacity(0.85),
        statusError: Color(red: 222/255, green: 68/255, blue: 55/255).opacity(0.85)
    )

    static let sunset = ThemeDescriptor(
        preference: .sunset,
        backgroundGradient: [
            Color(red: 69/255, green: 17/255, blue: 65/255).opacity(0.95),
            Color(red: 175/255, green: 54/255, blue: 62/255).opacity(0.88),
            Color(red: 253/255, green: 160/255, blue: 102/255).opacity(0.85)
        ],
        primaryText: Color.white,
        secondaryText: Color.white.opacity(0.78),
        accent: Color(red: 255/255, green: 207/255, blue: 86/255),
        cardStroke: Color.white.opacity(0.18),
        chipBackground: Color(red: 255/255, green: 207/255, blue: 86/255).opacity(0.3),
        chipText: Color.white,
        quickActionBackground: Color.white.opacity(0.08),
        quickActionStroke: Color.white.opacity(0.22),
        cardShadow: Color.black.opacity(0.28),
        sidebarBackground: Color.white.opacity(0.05),
        listSelection: Color(red: 255/255, green: 207/255, blue: 86/255).opacity(0.35),
        statusChecking: Color(red: 255/255, green: 130/255, blue: 67/255).opacity(0.9),
        statusConnected: Color(red: 112/255, green: 223/255, blue: 155/255).opacity(0.92),
        statusError: Color(red: 238/255, green: 75/255, blue: 106/255).opacity(0.88)
    )

    static let automatic = midnight
}

private struct ThemeDescriptorKey: EnvironmentKey {
    static let defaultValue: ThemeDescriptor = .midnight
}

extension EnvironmentValues {
    var themeDescriptor: ThemeDescriptor {
        get { self[ThemeDescriptorKey.self] }
        set { self[ThemeDescriptorKey.self] = newValue }
    }
}
