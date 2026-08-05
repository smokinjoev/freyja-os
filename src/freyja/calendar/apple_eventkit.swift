import EventKit
import Foundation

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(2)
}

func emit(_ value: Any) -> Never {
    do {
        let data = try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
        FileHandle.standardOutput.write(data)
        exit(0)
    } catch { fail("EventKit serialization failed") }
}

func string(_ input: [String: Any], _ key: String, required: Bool = false) -> String? {
    guard let value = input[key] as? String, !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
        if required { fail("Missing required field: \(key)") }
        return nil
    }
    return value
}

let arguments = Array(CommandLine.arguments.dropFirst())
guard let operation = arguments.first else { fail("Missing operation") }
let mayRequestAccess = arguments.contains("--request-access")
let inputData = FileHandle.standardInput.readDataToEndOfFile()
let input = (try? JSONSerialization.jsonObject(with: inputData)) as? [String: Any] ?? [:]
let store = EKEventStore()
let status = EKEventStore.authorizationStatus(for: .event)

if operation == "status" {
    let available: Bool
    if #available(macOS 14.0, *) { available = status == .fullAccess }
    else { available = status == .authorized }
    emit(["authorization": String(describing: status), "available": available])
}
if status == .denied || status == .restricted { fail("Calendar permission is unavailable") }
if status == .notDetermined {
    if !mayRequestAccess { fail("Calendar permission has not been requested") }
    let semaphore = DispatchSemaphore(value: 0)
    var granted = false
    if #available(macOS 14.0, *) {
        store.requestFullAccessToEvents { allowed, _ in granted = allowed; semaphore.signal() }
    } else {
        store.requestAccess(to: .event) { allowed, _ in granted = allowed; semaphore.signal() }
    }
    semaphore.wait()
    if !granted { fail("Calendar permission was not granted") }
}

let formatter = ISO8601DateFormatter()
formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
func parseDate(_ value: String) -> Date {
    if let date = formatter.date(from: value) { return date }
    formatter.formatOptions = [.withInternetDateTime]
    guard let date = formatter.date(from: value) else { fail("Invalid ISO-8601 date") }
    return date
}
func eventObject(_ event: EKEvent) -> [String: Any] {
    var result: [String: Any] = [
        "event_id": event.eventIdentifier ?? "",
        "calendar_id": event.calendar.calendarIdentifier,
        "calendar_title": event.calendar.title,
        "title": event.title ?? "",
        "start": formatter.string(from: event.startDate),
        "end": formatter.string(from: event.endDate),
        "all_day": event.isAllDay,
    ]
    if let location = event.location { result["location"] = location }
    if let notes = event.notes { result["description"] = notes }
    return result
}
func calendar(_ identifier: String?) -> EKCalendar {
    if let identifier = identifier {
        guard let found = store.calendar(withIdentifier: identifier) ?? store.calendars(for: .event).first(where: { $0.title == identifier }) else {
            fail("Calendar not found")
        }
        return found
    }
    guard let found = store.defaultCalendarForNewEvents else { fail("No writable default calendar") }
    return found
}

switch operation {
case "request-access":
    emit(["granted": true])
case "calendars":
    emit(["calendars": store.calendars(for: .event).map { ["calendar_id": $0.calendarIdentifier, "title": $0.title, "writable": $0.allowsContentModifications] }])
case "list":
    let start = parseDate(string(input, "start", required: true)!)
    let end = parseDate(string(input, "end", required: true)!)
    let requested = input["calendar_ids"] as? [String] ?? []
    let calendars = requested.isEmpty ? store.calendars(for: .event) : requested.map { calendar($0) }
    let events = store.events(matching: store.predicateForEvents(withStart: start, end: end, calendars: calendars))
    emit(["events": events.map(eventObject)])
case "create":
    let event = EKEvent(eventStore: store)
    event.title = string(input, "title", required: true)!
    event.startDate = parseDate(string(input, "start", required: true)!)
    event.endDate = parseDate(string(input, "end", required: true)!)
    if event.endDate <= event.startDate { fail("Event end must be after start") }
    event.calendar = calendar(string(input, "calendar_id"))
    event.location = string(input, "location")
    event.notes = string(input, "description")
    try? store.save(event, span: .thisEvent, commit: true)
    guard let identifier = event.eventIdentifier, !identifier.isEmpty,
          let confirmed = store.event(withIdentifier: identifier) else { fail("Calendar did not confirm the created event") }
    emit(["event": eventObject(confirmed)])
case "modify":
    guard let event = store.event(withIdentifier: string(input, "event_id", required: true)!) else { fail("Event not found") }
    if let value = string(input, "title") { event.title = value }
    if let value = string(input, "start") { event.startDate = parseDate(value) }
    if let value = string(input, "end") { event.endDate = parseDate(value) }
    if event.endDate <= event.startDate { fail("Event end must be after start") }
    if input.keys.contains("location") { event.location = input["location"] as? String }
    if input.keys.contains("description") { event.notes = input["description"] as? String }
    do { try store.save(event, span: .thisEvent, commit: true) } catch { fail("Calendar modification failed") }
    guard let confirmed = store.event(withIdentifier: event.eventIdentifier) else { fail("Calendar did not confirm the modified event") }
    emit(["event": eventObject(confirmed)])
case "delete":
    guard let event = store.event(withIdentifier: string(input, "event_id", required: true)!) else { emit(["deleted": false]) }
    do { try store.remove(event, span: .thisEvent, commit: true) } catch { fail("Calendar deletion failed") }
    emit(["deleted": store.event(withIdentifier: event.eventIdentifier) == nil])
default:
    fail("Unsupported operation")
}
