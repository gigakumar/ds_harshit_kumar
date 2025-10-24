import Foundation
import SwiftUI

struct QuickAction: Identifiable, Hashable {
    enum ActionType: String {
        case summarizeInbox = "summarize_inbox"
        case planDay = "plan_day"
        case draftResponse = "draft_response"
        case custom = "custom"
    }

    let id = UUID()
    let title: String
    let subtitle: String
    let icon: String
    let type: ActionType
    let goal: String
}

@MainActor
final class AutomationDashboardViewModel: ObservableObject {
    @Published var quickActions: [QuickAction] = [
        QuickAction(title: "Summarize inbox", subtitle: "Scan mail and highlight follow-ups", icon: "tray.full", type: .summarizeInbox, goal: "Summarize today's inbox and list the top action items."),
        QuickAction(title: "Plan my day", subtitle: "Generate a 5-step morning plan", icon: "sun.max", type: .planDay, goal: "Create a prioritized plan for my day with calendar blocks."),
        QuickAction(title: "Draft a response", subtitle: "Use knowledge base for context", icon: "bubble.left.and.text.bubble.right", type: .draftResponse, goal: "Draft a friendly response summarizing the last meeting notes."),
        QuickAction(title: "Custom automation", subtitle: "Bring your own workflow", icon: "sparkles", type: .custom, goal: "")
    ]
    @Published var selectedAction: QuickAction?
    @Published var automationLog: [AutomationLogEvent] = []
    @Published var isRunningQuickAction: Bool = false
    @Published var statusMessage: String?

    private let client: AutomationClient

    init(client: AutomationClient) {
        self.client = client
    }

    func refresh() async {
        do {
            automationLog = try await client.logs(limit: 60)
        } catch {
            statusMessage = error.localizedDescription
        }
    }

    func trigger(action: QuickAction) {
        isRunningQuickAction = true
        statusMessage = nil
        let goal = action.goal
        guard goal.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false else {
            statusMessage = "Provide a goal for this automation."
            isRunningQuickAction = false
            return
        }
        Task {
            do {
                let actions = try await client.plan(goal: goal)
                guard let first = actions.first else {
                    statusMessage = "No actions generated."
                    isRunningQuickAction = false
                    return
                }
                let success = try await client.execute(action: first)
                statusMessage = success ? "Dispatched automation: \(first.name)" : "Automation reported an error"
            } catch {
                statusMessage = "Automation failed: \(error.localizedDescription)"
            }
            isRunningQuickAction = false
            await refresh()
        }
    }
}
