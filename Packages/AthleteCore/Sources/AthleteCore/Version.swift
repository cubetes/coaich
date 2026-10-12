import Foundation

extension Bundle {
    /// "v0.1.1 (42)": marketing version from project.yml, build = git commit count at build time.
    public var versionLabel: String {
        let v = infoDictionary?["CFBundleShortVersionString"] as? String ?? "?"
        let b = infoDictionary?["CFBundleVersion"] as? String ?? "?"
        return "v\(v) (\(b))"
    }
}
