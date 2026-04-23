import AppKit
import Foundation
import Vision

struct ObservationLine {
    let text: String
    let minY: CGFloat
    let minX: CGFloat
    let maxY: CGFloat
    let maxX: CGFloat
}

func collectObservations(at imagePath: String) throws -> [ObservationLine] {
    let url = URL(fileURLWithPath: imagePath)
    guard let image = NSImage(contentsOf: url) else {
        throw NSError(domain: "VisionOCR", code: 1, userInfo: [NSLocalizedDescriptionKey: "Unable to open image at \(imagePath)"])
    }

    guard
        let tiff = image.tiffRepresentation,
        let bitmap = NSBitmapImageRep(data: tiff),
        let cgImage = bitmap.cgImage
    else {
        throw NSError(domain: "VisionOCR", code: 2, userInfo: [NSLocalizedDescriptionKey: "Unable to create CGImage for \(imagePath)"])
    }

    var collected: [ObservationLine] = []
    let request = VNRecognizeTextRequest { request, error in
        if error != nil {
            return
        }
        guard let observations = request.results as? [VNRecognizedTextObservation] else {
            return
        }
        for observation in observations {
            guard let candidate = observation.topCandidates(1).first else {
                continue
            }
            let text = candidate.string.trimmingCharacters(in: .whitespacesAndNewlines)
            if text.isEmpty {
                continue
            }
            collected.append(
                ObservationLine(
                    text: text,
                    minY: observation.boundingBox.minY,
                    minX: observation.boundingBox.minX,
                    maxY: observation.boundingBox.maxY,
                    maxX: observation.boundingBox.maxX
                )
            )
        }
    }

    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = false
    request.recognitionLanguages = ["en-US"]
    request.minimumTextHeight = 0.01

    let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
    try handler.perform([request])

    return collected.sorted {
        if abs($0.minY - $1.minY) > 0.015 {
            return $0.minY > $1.minY
        }
        return $0.minX < $1.minX
    }
}

func recognizeText(at imagePath: String) throws -> String {
    let ordered = try collectObservations(at: imagePath)

    return ordered.map(\.text).joined(separator: "\n")
}

do {
    guard CommandLine.arguments.count >= 2 else {
        throw NSError(domain: "VisionOCR", code: 3, userInfo: [NSLocalizedDescriptionKey: "Usage: swift vision_ocr.swift [--json] <image-path>"])
    }
    let wantsJSON = CommandLine.arguments.contains("--json")
    let imageArgument = CommandLine.arguments.last ?? ""
    if wantsJSON {
        let observations = try collectObservations(at: imageArgument)
        let payload = observations.map {
            [
                "text": $0.text,
                "minY": Double($0.minY),
                "minX": Double($0.minX),
                "maxY": Double($0.maxY),
                "maxX": Double($0.maxX),
            ]
        }
        let data = try JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted])
        if let text = String(data: data, encoding: .utf8) {
            print(text)
        }
    } else {
        let result = try recognizeText(at: imageArgument)
        print(result)
    }
} catch {
    fputs("\(error.localizedDescription)\n", stderr)
    exit(1)
}
