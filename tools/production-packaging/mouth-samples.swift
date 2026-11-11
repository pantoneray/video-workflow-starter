import AVFoundation
import Foundation
import Vision

struct MouthSample: Encodable {
    let time: Double
    let aperture: Double?
}

let arguments = CommandLine.arguments
guard arguments.count >= 4, arguments.count.isMultiple(of: 2) else {
    throw CocoaError(.fileReadInvalidFileName)
}
let asset = AVURLAsset(url: URL(fileURLWithPath: arguments[1]))
let generator = AVAssetImageGenerator(asset: asset)
generator.appliesPreferredTrackTransform = true
generator.maximumSize = CGSize(width: 960, height: 960)
generator.requestedTimeToleranceBefore = .zero
generator.requestedTimeToleranceAfter = CMTime(value: 1, timescale: 30)

func aperture(_ results: [VNFaceObservation]) -> Double? {
    guard results.count == 1, let landmarks = results[0].landmarks,
          let inner = landmarks.innerLips, let outer = landmarks.outerLips,
          let low = inner.normalizedPoints.map(\.y).min(),
          let high = inner.normalizedPoints.map(\.y).max(),
          let left = outer.normalizedPoints.map(\.x).min(),
          let right = outer.normalizedPoints.map(\.x).max(), right > left else { return nil }
    let face = results[0].boundingBox
    return (high - low) * face.height / ((right - left) * face.width)
}

var windows: [[MouthSample]] = []
for index in stride(from: 2, to: arguments.count, by: 2) {
    guard let start = Double(arguments[index]), let end = Double(arguments[index + 1]),
          start.isFinite, end.isFinite, 0 <= start, start < end else { throw CocoaError(.fileReadCorruptFile) }
    var samples: [MouthSample] = []
    for time in stride(from: start, to: end, by: 1.0 / 15) {
        let frame = try await generator.image(at: CMTime(seconds: time, preferredTimescale: 600))
        let request = VNDetectFaceLandmarksRequest()
        try VNImageRequestHandler(cgImage: frame.image).perform([request])
        let aspect = Double(frame.image.height) / Double(frame.image.width)
        samples.append(MouthSample(time: frame.actualTime.seconds,
                                   aperture: aperture(request.results ?? []).map { $0 * aspect }))
    }
    windows.append(samples)
}
FileHandle.standardOutput.write(try JSONEncoder().encode(windows))
