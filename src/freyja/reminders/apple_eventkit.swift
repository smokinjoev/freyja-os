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
let status = EKEventStore.authorizationStatus(for: .reminder)

if operation == "status" {
    let available: Bool
    if #available(macOS 14.0, *) { available = status == .fullAccess }
    else { available = status == .authorized }
    emit(["authorization": String(describing: status), "available": available])
}
if status == .denied || status == .restricted { fail("Reminders permission is unavailable") }
if status == .notDetermined {
    if !mayRequestAccess { fail("Reminders permission has not been requested") }
    let semaphore = DispatchSemaphore(value: 0)
    var granted = false
    if #available(macOS 14.0, *) {
        store.requestFullAccessToReminders { allowed, _ in granted = allowed; semaphore.signal() }
    } else {
        store.requestAccess(to: .reminder) { allowed, _ in granted = allowed; semaphore.signal() }
    }
    semaphore.wait()
    if !granted { fail("Reminders permission was not granted") }
}

let formatter = ISO8601DateFormatter()
formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
func parseDate(_ value: String) -> Date {
    if let date = formatter.date(from: value) { return date }
    formatter.formatOptions = [.withInternetDateTime]
    guard let date = formatter.date(from: value) else { fail("Invalid ISO-8601 date") }
    return date
}
func dateComponents(_ value: String) -> DateComponents {
    Calendar.current.dateComponents([.year, .month, .day, .hour, .minute, .second], from: parseDate(value))
}
func isoString(_ components: DateComponents?) -> String? {
    guard let components = components, let date = Calendar.current.date(from: components) else { return nil }
    return formatter.string(from: date)
}
func calendar(_ identifier: String?) -> EKCalendar {
    if let identifier = identifier {
        guard let found = store.calendar(withIdentifier: identifier) ?? store.calendars(for: .reminder).first(where: { $0.title == identifier }) else {
            fail("Reminder list not found")
        }
        return found
    }
    guard let found = store.defaultCalendarForNewReminders() else { fail("No writable default reminder list") }
    return found
}
func listObject(_ calendar: EKCalendar) -> [String: Any] {
    ["list_id": calendar.calendarIdentifier, "title": calendar.title, "writable": calendar.allowsContentModifications]
}
func reminderObject(_ reminder: EKReminder) -> [String: Any] {
    var result: [String: Any] = [
        "reminder_id": reminder.calendarItemIdentifier,
        "list_id": reminder.calendar.calendarIdentifier,
        "list_title": reminder.calendar.title,
        "title": reminder.title ?? "",
        "completed": reminder.isCompleted,
    ]
    if let due = isoString(reminder.dueDateComponents) { result["due"] = due }
    if let notes = reminder.notes { result["notes"] = notes }
    return result
}
func fetchReminder(_ identifier: String) -> EKReminder? {
    store.calendarItem(withIdentifier: identifier) as? EKReminder
}

switch operation {
case "request-access":
    emit(["granted": true])
case "lists":
    emit(["lists": store.calendars(for: .reminder).map(listObject)])
case "list":
    let requested = input["list_ids"] as? [String] ?? []
    let includeCompleted = input["include_completed"] as? Bool ?? false
    let calendars = requested.isEmpty ? store.calendars(for: .reminder) : requested.map { calendar($0) }
    let semaphore = DispatchSemaphore(value: 0)
    var reminders: [EKReminder] = []
    let predicate = store.predicateForReminders(in: calendars)
    store.fetchReminders(matching: predicate) { found in
        reminders = found ?? []
        semaphore.signal()
    }
    semaphore.wait()
    if !includeCompleted { reminders = reminders.filter { !$0.isCompleted } }
    emit(["reminders": reminders.map(reminderObject)])
case "create":
    let reminder = EKReminder(eventStore: store)
    reminder.title = string(input, "title", required: true)!
    reminder.calendar = calendar(string(input, "list_id"))
    if let due = string(input, "due") { reminder.dueDateComponents = dateComponents(due) }
    reminder.notes = string(input, "notes")
    do { try store.save(reminder, commit: true) } catch { fail("Reminder creation failed") }
    guard let confirmed = fetchReminder(reminder.calendarItemIdentifier) else { fail("Reminders did not confirm the created reminder") }
    emit(["reminder": reminderObject(confirmed)])
case "complete":
    guard let reminder = fetchReminder(string(input, "reminder_id", required: true)!) else { fail("Reminder not found") }
    reminder.isCompleted = true
    do { try store.save(reminder, commit: true) } catch { fail("Reminder completion failed") }
    guard let confirmed = fetchReminder(reminder.calendarItemIdentifier) else { fail("Reminders did not confirm the completed reminder") }
    emit(["reminder": reminderObject(confirmed)])
case "delete":
    guard let reminder = fetchReminder(string(input, "reminder_id", required: true)!) else { emit(["deleted": false]) }
    do { try store.remove(reminder, commit: true) } catch { fail("Reminder deletion failed") }
    emit(["deleted": fetchReminder(reminder.calendarItemIdentifier) == nil])
default:
    fail("Unsupported operation")
}
