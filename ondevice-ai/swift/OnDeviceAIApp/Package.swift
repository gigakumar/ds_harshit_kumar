// swift-tools-version: 5.10
import PackageDescription

let package = Package(
    name: "OnDeviceAIApp",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .executable(name: "OnDeviceAIApp", targets: ["OnDeviceAIApp"])
    ],
    dependencies: [],
    targets: [
        .executableTarget(
            name: "OnDeviceAIApp",
            dependencies: [],
            path: "Sources"
        )
    ]
)
