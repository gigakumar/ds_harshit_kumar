import Foundation

struct AnyCodable: Codable, CustomStringConvertible {
    let value: Any

    init(_ value: Any) {
        self.value = value
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self.value = NSNull()
        } else if let bool = try? container.decode(Bool.self) {
            self.value = bool
        } else if let int = try? container.decode(Int.self) {
            self.value = int
        } else if let double = try? container.decode(Double.self) {
            self.value = double
        } else if let string = try? container.decode(String.self) {
            self.value = string
        } else if let dict = try? container.decode([String: AnyCodable].self) {
            self.value = dict
        } else if let array = try? container.decode([AnyCodable].self) {
            self.value = array
        } else {
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Unsupported value")
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch value {
        case is NSNull:
            try container.encodeNil()
        case let bool as Bool:
            try container.encode(bool)
        case let int as Int:
            try container.encode(int)
        case let double as Double:
            try container.encode(double)
        case let string as String:
            try container.encode(string)
        case let dict as [String: AnyCodable]:
            try container.encode(dict)
        case let array as [AnyCodable]:
            try container.encode(array)
        default:
            let description = String(describing: value)
            try container.encode(description)
        }
    }

    var description: String {
        switch value {
        case is NSNull:
            return "null"
        case let bool as Bool:
            return bool ? "true" : "false"
        case let int as Int:
            return String(int)
        case let double as Double:
            return String(double)
        case let string as String:
            return string
        case let dict as [String: AnyCodable]:
            let pairs = dict.map { "\($0.key): \($0.value.description)" }.sorted().joined(separator: ", ")
            return "{\(pairs)}"
        case let array as [AnyCodable]:
            return "[\(array.map { $0.description }.joined(separator: ", "))]"
        default:
            return String(describing: value)
        }
    }
}
