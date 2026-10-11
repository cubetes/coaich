// swift-tools-version: 6.2
import PackageDescription

let package = Package(
    name: "AthleteCore",
    platforms: [.iOS(.v26), .watchOS(.v26), .macOS(.v15)],
    products: [.library(name: "AthleteCore", targets: ["AthleteCore"])],
    targets: [
        .target(name: "AthleteCore"),
        .testTarget(name: "AthleteCoreTests", dependencies: ["AthleteCore"]),
    ]
)
