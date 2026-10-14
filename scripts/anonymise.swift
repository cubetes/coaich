// Face detection and anonymised re-encoding for progress photos, on the user's Mac, offline (Apple Vision +
// ImageIO, both built into macOS). photos.py decides where to cut; this tool only measures and draws.
//
//   anonymise detect IN                  JSON: upright width/height, face boxes, body-pose head/neck/shoulder points
//   anonymise render IN OUT none         re-encode upright, no metadata
//   anonymise render IN OUT crop TOP     keep rows TOP..bottom (drop everything above TOP)
//   anonymise render IN OUT cover X0 Y0 X1 Y1   paint that box solid grey
//
// Coordinates are pixels of the upright image (EXIF orientation applied), origin top-left. OUT is always a JPEG
// written with no EXIF, GPS, XMP or other properties. Exit 1 = error (message on stderr).
import CoreGraphics
import Foundation
import ImageIO
import UniformTypeIdentifiers
import Vision

func fail(_ msg: String) -> Never {
    FileHandle.standardError.write((msg + "\n").data(using: .utf8)!)
    exit(1)
}

/// The image drawn upright: ImageIO applies the EXIF orientation, at full size.
func upright(_ path: String) -> CGImage {
    guard let src = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil),
          let props = CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [CFString: Any],
          let w = props[kCGImagePropertyPixelWidth] as? Int, let h = props[kCGImagePropertyPixelHeight] as? Int
    else { fail("cannot read image: \(path)") }
    let opts: [CFString: Any] = [
        kCGImageSourceCreateThumbnailFromImageAlways: true,
        kCGImageSourceCreateThumbnailWithTransform: true,
        kCGImageSourceThumbnailMaxPixelSize: max(w, h),
        kCGImageSourceShouldCacheImmediately: true,
    ]
    guard let img = CGImageSourceCreateThumbnailAtIndex(src, 0, opts as CFDictionary) else { fail("cannot decode image: \(path)") }
    return img
}

func detect(_ img: CGImage) -> [String: Any] {
    let w = Double(img.width), h = Double(img.height)
    let faces = VNDetectFaceRectanglesRequest()
    let body = VNDetectHumanBodyPoseRequest()
    do { try VNImageRequestHandler(cgImage: img, orientation: .up).perform([faces, body]) } catch { fail("Vision failed: \(error)") }
    // Vision boxes are normalised with the origin bottom-left; flip to top-left pixels.
    let boxes = (faces.results ?? []).map { f -> [Int] in
        let b = f.boundingBox
        return [Int((b.minX * w).rounded()), Int(((1 - b.maxY) * h).rounded()),
                Int((b.width * w).rounded()), Int((b.height * h).rounded())]
    }
    let joints: [(String, VNHumanBodyPoseObservation.JointName)] = [
        ("nose", .nose), ("left_eye", .leftEye), ("right_eye", .rightEye), ("left_ear", .leftEar),
        ("right_ear", .rightEar), ("neck", .neck), ("left_shoulder", .leftShoulder), ("right_shoulder", .rightShoulder),
    ]
    var points: [String: [Int]] = [:]
    for person in body.results ?? [] {
        for (name, joint) in joints {
            guard let p = try? person.recognizedPoint(joint), p.confidence >= 0.3 else { continue }
            let xy = [Int((p.location.x * w).rounded()), Int(((1 - p.location.y) * h).rounded())]
            // Several people: keep the highest head point and the highest shoulder point (the safer cut).
            if let old = points[name], old[1] <= xy[1] { continue }
            points[name] = xy
        }
    }
    return ["width": img.width, "height": img.height, "faces": boxes, "points": points, "people": body.results?.count ?? 0]
}

func write(_ img: CGImage, _ out: String) {
    guard let dst = CGImageDestinationCreateWithURL(URL(fileURLWithPath: out) as CFURL, UTType.jpeg.identifier as CFString, 1, nil)
    else { fail("cannot write \(out)") }
    // Only the compression setting: no source properties are carried over, so no EXIF, GPS, XMP or TIFF tags.
    CGImageDestinationAddImage(dst, img, [kCGImageDestinationLossyCompressionQuality: 0.92] as CFDictionary)
    if !CGImageDestinationFinalize(dst) { fail("cannot write \(out)") }
}

func int(_ s: String) -> Int {
    guard let v = Int(s) else { fail("not a whole number: \(s)") }
    return v
}

let args = CommandLine.arguments
switch (args.count > 1 ? args[1] : "", args.count) {
case ("detect", 3):
    let json = try! JSONSerialization.data(withJSONObject: detect(upright(args[2])), options: [.sortedKeys])
    print(String(data: json, encoding: .utf8)!)
case ("render", 5...):
    let img = upright(args[2])
    switch (args[4], args.count) {
    case ("none", 5):
        write(img, args[3])
    case ("crop", 6):
        let top = int(args[5])
        guard top > 0, top < img.height, let c = img.cropping(to: CGRect(x: 0, y: top, width: img.width, height: img.height - top))
        else { fail("crop line \(top) is outside the image") }
        write(c, args[3])
    case ("cover", 9):
        let (x0, y0, x1, y1) = (int(args[5]), int(args[6]), int(args[7]), int(args[8]))
        guard 0 <= x0, x0 < x1, x1 <= img.width, 0 <= y0, y0 < y1, y1 <= img.height else { fail("cover box is outside the image") }
        guard let ctx = CGContext(data: nil, width: img.width, height: img.height, bitsPerComponent: 8, bytesPerRow: 0,
                                  space: CGColorSpace(name: CGColorSpace.sRGB)!, bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)
        else { fail("cannot draw") }
        ctx.draw(img, in: CGRect(x: 0, y: 0, width: img.width, height: img.height))
        ctx.setFillColor(CGColor(gray: 0.5, alpha: 1))
        ctx.fill(CGRect(x: x0, y: img.height - y1, width: x1 - x0, height: y1 - y0))  // CGContext origin is bottom-left
        write(ctx.makeImage()!, args[3])
    default:
        fail("render IN OUT none | crop TOP | cover X0 Y0 X1 Y1")
    }
default:
    fail("usage: anonymise detect IN | anonymise render IN OUT none|crop TOP|cover X0 Y0 X1 Y1")
}
