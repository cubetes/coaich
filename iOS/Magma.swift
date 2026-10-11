import SwiftUI
import UIKit

/// The web app's MAGMA look on the iPhone (G81/G82; tokens from the web's `styles/themes/magma.css`). iPhone only: the
/// Watch and the Live Activity keep their own tokens (`docs/design/DESIGN.md` §2). Light / dark per appearance.
enum Magma {
    static let bg = dyn(0xF4F4F2, 0x0E0F12)
    static let card = dyn(0xFFFFFF, 0x181A20)
    static let text = dyn(0x111316, 0xF1F2F4)
    static let dim = dyn(0x5B5E66, 0x9CA0A8, high: (0x111316, 0xF1F2F4))
    /// a11y: 4.6:1 on the light bg (MAGMA's #9A9DA4 would be ≈ 2.6).
    static let faint = dyn(0x6B6E76, 0x9398A1, high: (0x3D4047, 0xC9CCD2))
    static let divider = Magma.adaptive { $0.userInterfaceStyle == .dark ? UIColor(white: 1, alpha: 0.08) : UIColor(white: 0.07, alpha: 0.08) }
    static let scrim = Magma.adaptive { $0.userInterfaceStyle == .dark ? UIColor(white: 1, alpha: 0.07) : UIColor(white: 0.07, alpha: 0.055) }
    static let hitFg = dyn(0x0E7B45, 0x57E099)
    static let hit = dyn(0x149E5B, 0x2BD27A)
    /// Caution ink (✗, "Estancado"): never red for a grade.
    static let cautionFg = dyn(0x985700, 0xFFC65E)
    static let cautionBg = Magma.adaptive { $0.userInterfaceStyle == .dark ? UIColor(rgb: 0xFFB02E, alpha: 0.15) : UIColor(rgb: 0xFDEBD6) }
    static let missedFg = dyn(0xB61E24, 0xFF858A)
    /// Text on the hero card (both appearances: the hero is always dark).
    static let heroText = Color(rgb: 0xF6F6F4)
    static let aura2 = dyn(0x8B5CF6, 0xA78BFA)
    /// The rest countdown in the Live Activity's colour (Watch `elapsed`) in dark mode, ink in light (panel lens 3).
    static let rest = dyn(0x111316, 0xFFD60A)

    /// A colour that follows light/dark. `@Sendable` + nonisolated: UIKit may resolve it off the main thread, and a
    /// MainActor-isolated provider then traps in Swift 6 (crash 2026-10-10, `_dispatch_assert_queue_fail` in `dyn`).
    nonisolated static func adaptive(_ pick: @escaping @Sendable (UITraitCollection) -> UIColor) -> Color {
        Color(UIColor(dynamicProvider: pick))
    }

    /// A colour per appearance; `high` = the Increase Contrast pair (light, dark), else the same as normal.
    static func dyn(_ light: UInt32, _ dark: UInt32, high: (UInt32, UInt32)? = nil) -> Color {
        adaptive { t in
            let (l, d) = t.accessibilityContrast == .high ? high ?? (light, dark) : (light, dark)
            return UIColor(rgb: t.userInterfaceStyle == .dark ? d : l)
        }
    }

    // MARK: Type: Archivo (OFL, bundled static instances of the web's variable font), always scaled with Dynamic Type.

    enum Weight: String { case regular = "Regular", semibold = "SemiBold", bold = "Bold", heavy = "ExtraBold", black = "Black" }

    /// Bold Text (a custom font ignores it by itself) moves every weight one step up.
    static func font(_ size: CGFloat, _ weight: Weight = .regular, relativeTo style: Font.TextStyle = .body) -> Font {
        let order: [Weight] = [.regular, .semibold, .bold, .heavy, .black]
        let w = UIAccessibility.isBoldTextEnabled ? order[min(order.count - 1, order.firstIndex(of: weight)! + 1)] : weight
        return .custom("Archivo-\(w.rawValue)", size: size, relativeTo: style).monospacedDigit()
    }
}

extension AppTheme {
    /// The iPhone accent as text, links and controls (`.tint`): MAGMA's darker #D0103F in light mode so small text
    /// passes 4.5:1 on white (#F5184E is 4.1), #FF3D6E in dark. Neón verde as before (G43).
    var tint: Color {
        self == .neon ? Magma.dyn(0x4A7500, 0xB4F03C, high: (0x3F6400, 0xC8F56A))
                      : Magma.dyn(0xD0103F, 0xFF3D6E, high: (0xB80D37, 0xFF7A9A))
    }

    /// The accent as a large fill (the start button): MAGMA #F5184E / #FF3D6E. Labels on it: bold ≥ 15 pt.
    var fill: Color {
        self == .neon ? Magma.dyn(0x4A7500, 0xB4F03C) : Magma.dyn(0xF5184E, 0xFF3D6E)
    }

    /// The pale accent behind today's day and the editable pill.
    var soft: Color {
        self == .neon
            ? Magma.adaptive { $0.userInterfaceStyle == .dark ? UIColor(rgb: 0xB4F03C, alpha: 0.17) : UIColor(rgb: 0xE9F2D9) }
            : Magma.adaptive { $0.userInterfaceStyle == .dark ? UIColor(rgb: 0xFF3D6E, alpha: 0.17) : UIColor(rgb: 0xFFE1E9) }
    }

    /// Small accent text on `soft`: #B80D37 on #FFE1E9 (panel: #D0103F there is 4.49:1).
    var onSoft: Color {
        self == .neon ? Magma.dyn(0x3F6400, 0xB4F03C) : Magma.dyn(0xB80D37, 0xFF6F92)
    }

    /// The label on a `tint`/`fill` (G75): black on the lime; white on magenta (bold, ≥ 15 pt) and on the light green.
    var onTint: Color {
        self == .neon ? Magma.adaptive { $0.userInterfaceStyle == .dark ? .black : .white } : .white
    }
}

extension UIColor {
    nonisolated convenience init(rgb: UInt32, alpha: CGFloat = 1) {
        self.init(red: CGFloat(rgb >> 16 & 0xFF) / 255, green: CGFloat(rgb >> 8 & 0xFF) / 255, blue: CGFloat(rgb & 0xFF) / 255, alpha: alpha)
    }
}

extension Color {
    init(rgb: UInt32) { self.init(UIColor(rgb: rgb)) }
}

/// A section header in MAGMA style, uppercase in the string itself (ios-ui), marked as a heading.
struct SectionLabel: View {
    let text: String
    var body: some View {
        Text(text.uppercased(with: Locale(identifier: "es_ES")))
            .font(Magma.font(12, .heavy, relativeTo: .caption))
            .kerning(0.8)
            .foregroundStyle(Magma.dim)
            .accessibilityAddTraits(.isHeader)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.top, 20)
            .padding(.bottom, 6)
    }
}

/// MAGMA's solid card (never Liquid Glass on content).
struct CardBackground: ViewModifier {
    @Environment(\.colorScheme) private var scheme
    func body(content: Content) -> some View {
        content
            .background(Magma.card, in: .rect(cornerRadius: 16))
            .overlay {
                if scheme == .dark { RoundedRectangle(cornerRadius: 16).stroke(Color.white.opacity(0.10)) }
            }
            .shadow(color: .black.opacity(scheme == .dark ? 0 : 0.06), radius: 8, y: 4)
    }
}

extension View {
    func card() -> some View { modifier(CardBackground()) }
}

extension String {
    /// MAGMA's uppercase display, written into the string (not `textCase`), Spanish rules.
    var upper: String { uppercased(with: Locale(identifier: "es_ES")) }
}
