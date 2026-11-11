import AVFoundation
import Foundation
import Vision

struct Face: Encodable {
    let x: Double
    let y: Double
    let width: Double
    let height: Double
}

struct Sample: Encodable {
    let time: Double
    let aspect: Double
    let faces: [Face]
}

guard (2...3).contains(CommandLine.arguments.count) else {
    throw CocoaError(.fileReadInvalidFileName)
}
let interval = CommandLine.arguments.count == 3 ? Double(CommandLine.arguments[2]) ?? 0 : 1
guard interval.isFinite, interval > 0 else { throw CocoaError(.fileReadCorruptFile) }
let asset = AVURLAsset(url: URL(fileURLWithPath: CommandLine.arguments[1]))
let duration = try await asset.load(.duration).seconds
guard duration.isFinite, duration > 0 else {
    throw CocoaError(.fileReadCorruptFile)
}
let generator = AVAssetImageGenerator(asset: asset)
generator.appliesPreferredTrackTransform = true
generator.maximumSize = CGSize(width: 960, height: 960)
generator.requestedTimeToleranceBefore = .zero
generator.requestedTimeToleranceAfter = CMTime(value: 1, timescale: 30)

var samples: [Sample] = []
for time in stride(from: 0.0, to: duration - min(interval / 2, 1.0 / 30), by: interval) {
    let frame = try await generator.image(at: CMTime(seconds: time, preferredTimescale: 600))
    let request = VNDetectFaceRectanglesRequest()
    try VNImageRequestHandler(cgImage: frame.image).perform([request])
    let faces = (request.results ?? []).map { observation in
        let box = observation.boundingBox
        return Face(x: box.minX, y: 1 - box.maxY, width: box.width, height: box.height)
    }
    samples.append(Sample(time: frame.actualTime.seconds,
                          aspect: Double(frame.image.width) / Double(frame.image.height), faces: faces))
}
FileHandle.standardOutput.write(try JSONEncoder().encode(samples))
