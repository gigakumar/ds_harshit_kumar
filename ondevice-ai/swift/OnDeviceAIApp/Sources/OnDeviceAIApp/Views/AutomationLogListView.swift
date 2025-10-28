import SwiftUI

struct AutomationLogListView: View {
    @Environment(\.themeDescriptor) private var theme
    let events: [AutomationLogEvent]

    var body: some View {
        if events.isEmpty {
            Text("No automation events captured yet.")
                .font(.footnote)
                .foregroundColor(theme.secondaryText)
                .frame(maxWidth: .infinity, alignment: .leading)
        } else {
            VStack(alignment: .leading, spacing: 12) {
                ForEach(events) { event in
                    VStack(alignment: .leading, spacing: 6) {
                        HStack {
                            Text(event.type.capitalized)
                                .font(.system(.headline, design: .rounded))
                                .foregroundColor(theme.primaryText)
                            Spacer()
                            Text(event.ts, style: .time)
                                .font(.caption)
                                .foregroundColor(theme.secondaryText)
                        }
                        if event.payload.isEmpty == false {
                            Text(event.payload.map { "\($0.key): \($0.value)" }.sorted().joined(separator: ", "))
                                .font(.system(.caption, design: .monospaced))
                                .foregroundColor(theme.secondaryText)
                                .lineLimit(4)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(14)
                    .background(theme.quickActionBackground, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                }
            }
        }
    }
}
