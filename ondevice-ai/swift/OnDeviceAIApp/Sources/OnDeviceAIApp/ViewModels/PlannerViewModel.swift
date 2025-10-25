import Foundation
import SwiftUI

@MainActor
final class PlannerViewModel: ObservableObject {
    @Published var goal: String = ""
    @Published var actions: [PlanAction] = []
    @Published var contextHits: [QueryHit] = []
    @Published var isPlanning: Bool = false
    @Published var planError: String?
    @Published var executionStatus: String?
    @Published var temperature: Double = 0.2
    @Published var maxTokens: Double = 256
    @Published var includeKnowledge: Bool = true

    private let client: AutomationClient

    init(client: AutomationClient) {
        self.client = client
    }

    func runPlanning() {
        guard goal.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false else {
            planError = "Enter a goal to generate a plan."
            return
        }
        planError = nil
        executionStatus = nil
        isPlanning = true

        Task {
            do {
                let parameters = PlanParameters(temperature: temperature, maxTokens: Int(maxTokens))
                if includeKnowledge {
                    async let planTask = client.plan(goal: goal, params: parameters)
                    async let hitsTask = client.query(goal, limit: 5)
                    let (actions, hits) = try await (planTask, hitsTask)
                    self.actions = actions
                    self.contextHits = hits
                } else {
                    let actions = try await client.plan(goal: goal, params: parameters)
                    self.actions = actions
                    self.contextHits = []
                }
            } catch {
                self.planError = error.localizedDescription
                self.actions = []
            }
            self.isPlanning = false
        }
    }

    func execute(action: PlanAction) {
        Task {
            do {
                let success = try await client.execute(action: action)
                executionStatus = success ? "Action sent to automation daemon" : "Action execution returned non-zero status"
            } catch {
                executionStatus = "Execution failed: \(error.localizedDescription)"
            }
        }
    }
}
